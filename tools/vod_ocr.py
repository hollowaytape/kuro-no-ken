"""Read the dialogue text out of a recorded playthrough, frame by frame, with the game's font.

The dialogue box is drawn on the PC-98 text layer (docs/engine_notes.md, "Text VRAM"),
so every character on screen is a 16x16 glyph from the kanji ROM on the 8x16 text grid.
A video frame that shows the game at a known scale can therefore be read exactly: crop
the game screen, resample it back to 640 x 400, and at each text cell pick the glyph
from FONT.ROM (romtools/np2debug/FONT.ROM, the ROM np2core loads) that correlates best
with the pixels. No OCR model, and no ambiguity between similar kanji beyond what the
video's compression leaves. Only characters that occur in the dump are candidates.

    python tools/vod_ocr.py frame.png                      # print what the frame says
    python tools/vod_ocr.py --series werdna --part 1 part1.mp4 --out readings.json

The second form samples the video at its keyframes (a few seconds apart), keeps the
frames that show a text box, reads them, and writes the readings that vod_read.py
turns into anchors (see docs/engine_notes.md, "Ordering from a recorded playthrough").

Per-series layout (where the game screen sits in the frame, and its scale) is in
SERIES. Calibrate a new series by scanning origin and scale for the best glyph
correlation on a frame with dialogue (docs/engine_notes.md, "A second playthrough").
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

FONT_ROM = os.path.join(HERE, '..', 'romtools', 'np2debug', 'FONT.ROM')

#  where the 640x400 game screen is in the video frame: (x, y) of its top-left corner
#  and the scale (one number, or (x, y) when the capture stretched it), plus the frame
#  size the numbers are for
SERIES = {
    'twitch': {'frame': (1280, 720), 'origin': (274, 47), 'scale': 1.5625,
               'videos': {1: '349237766', 2: '349237819', 3: '349237909', 4: '349237884'},
               'length': {1: 6858, 2: 24319, 3: 29698, 4: 32371},
               'about': "sqpat's 4-part Twitch stream of the PC-98 version (collection i9PxK6i5nRamtQ)"},
    'werdna': {'frame': (1280, 720), 'origin': (-2, 60), 'scale': 1.5,
               'videos': {1: 'g2wng1XNxsk', 2: 'gPpYHBBKXm4', 3: 'bJq1wCJ6Qqg', 4: 'MLnXexuEITM'},
               'length': {1: 16732, 2: 9404, 3: 13674, 4: 9908},
               'about': "WERDNAちゃんねる's 4-part YouTube stream of the PC-98 version (2020)"},
}
GAME_W, GAME_H = 640, 400
CELL_W, CELL_H = 8, 16


def sjis_to_jis(ch):
    b = ch.encode('cp932')
    if len(b) != 2:
        return None
    s1, s2 = b[0], b[1]
    s1 -= 0x81 if s1 <= 0x9F else 0xC1
    j1 = s1 * 2 + 0x21
    if s2 >= 0x9F:
        j1 += 1
        j2 = s2 - 0x7E
    else:
        j2 = s2 - (0x1F if s2 <= 0x7E else 0x20)
    return j1, j2


def glyph(rom, ch):
    """16x16 float array (1 = ink) of a full-width character, or None."""
    jis = sjis_to_jis(ch)
    if not jis:
        return None
    j1, j2 = jis
    off = 0x1800 + ((j1 - 0x21) * 0x60 + (j2 - 0x20)) * 32
    if off + 32 > len(rom):
        return None
    g = np.zeros((16, 16), dtype=np.float32)
    for y in range(16):
        for half, base in ((0, off), (1, off + 16)):
            row = rom[base + y]
            for x in range(8):
                g[y, half * 8 + x] = (row >> (7 - x)) & 1
    return g


class Reader:
    """Glyph templates for every character the game's text can contain."""

    def __init__(self, alphabet=None):
        rom = open(FONT_ROM, 'rb').read()
        if alphabet is None:
            alphabet = dump_alphabet()
        self.chars, tiles = [], []
        for ch in sorted(set(alphabet)):
            g = glyph(rom, ch)
            if g is not None and g.any():
                self.chars.append(ch)
                tiles.append(g)
        #  the video is soft (an upscale, then the stream's encoder), so the templates are
        #  softened the same way: a 3x3 mean, which lifts a right match from ~0.6 to ~0.8
        t = np.stack(tiles)
        pad = np.pad(t, ((0, 0), (1, 1), (1, 1)))
        t = sum(pad[:, dy:dy + 16, dx:dx + 16] for dy in range(3) for dx in range(3)) / 9
        t = t.reshape(len(tiles), -1)
        t = t - t.mean(axis=1, keepdims=True)
        self.templates = t / np.linalg.norm(t, axis=1, keepdims=True)

    def best(self, windows):
        """windows: (n, 256) grey patches -> (index, score) per patch, score = correlation."""
        w = windows - windows.mean(axis=1, keepdims=True)
        n = np.linalg.norm(w, axis=1, keepdims=True)
        n[n == 0] = 1
        s = (w / n) @ self.templates.T
        i = s.argmax(axis=1)
        return i, s[np.arange(len(i)), i]

    def read_row(self, bands, min_score=0.5):
        """bands: (16, 640) grey (0..1, ink bright), one per sub-pixel shift of the same
        text row. -> the text on it.

        The video's scale is not exactly the nominal one, so a glyph far along the line
        drifts by a pixel: each cell takes its best match over the shifts."""
        if isinstance(bands, np.ndarray) and bands.ndim == 2:
            bands = [bands]
        inkcols = np.max([b.max(axis=0) for b in bands], axis=0) > 0.5
        #  the speaker's name is drawn half a cell (4 px) to the left of the text grid,
        #  so both phases are scored and the one the ink agrees with more is read
        best = None
        for phase in (0, 4):
            xs = list(range(phase, GAME_W - 16 + 1, CELL_W))
            idx, score = None, None
            for band in bands:
                wins = np.stack([band[:, x:x + 16].reshape(-1) for x in xs])
                i, sc = self.best(wins)
                if idx is None:
                    idx, score = i, sc
                else:
                    better = sc > score
                    idx = np.where(better, i, idx)
                    score = np.where(better, sc, score)
            total = sum(float(score[k]) for k, x in enumerate(xs) if inkcols[x:x + 16].any())
            if best is None or total > best[0]:
                best = (total, xs, idx, score)
        _total, xs, idx, score = best
        out, x = [], 0
        while x < len(xs):
            x0 = xs[x]
            if not inkcols[x0:x0 + 8].any():          # an empty cell: a space, or nothing
                if out and out[-1] != ' ':
                    out.append(' ')
                x += 1
                continue
            if score[x] >= min_score:
                out.append(self.chars[idx[x]])
                x += 2
            else:                                     # ink that is not a known glyph
                out.append('?')
                x += 1
        return ''.join(out).strip()


def dump_alphabet():
    """Every character in the dump's Japanese, plus the brackets norm() strips."""
    import vod_read
    chars = set('「」『』（）')
    for _s, rows in vod_read.rows_by_script().items():
        for _off, jp in rows:
            chars.update(jp)
    return chars


def game_screen(frame, series, shift=(0, 0)):
    """frame: HxWx3 uint8 -> the 640x400 game screen (float 0..1 RGB), taken from the
    frame `shift` video pixels away from the series' nominal origin."""
    from PIL import Image
    cfg = SERIES[series]
    ox, oy = cfg['origin'][0] + shift[0], cfg['origin'][1] + shift[1]
    sx, sy = scales(series)
    im = Image.fromarray(frame).crop((ox, oy, ox + int(round(GAME_W * sx)), oy + int(round(GAME_H * sy))))
    return np.asarray(im.resize((GAME_W, GAME_H), Image.LANCZOS)).astype(np.float32) / 255


def scales(series):
    s = SERIES[series]['scale']
    return (s, s) if isinstance(s, (int, float)) else tuple(s)


SHIFTS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-2, -1, 0, 1)]     # video pixels


def text_box(screen):
    """The dialogue box's rows and columns on the game screen, or None.

    The box is one flat dark navy; the text on it is white. Returns (y0, y1, x0, x1)
    of the navy area when it covers a good part of the lower screen."""
    r, g, b = screen[..., 0], screen[..., 1], screen[..., 2]
    navy = (r < 0.36) & (g < 0.36) & (b > 0.21) & (b < 0.52) & (b > r + 0.04)
    #  the dialogue box is always the same panel over the bottom of the screen (text
    #  rows 16-22); the item, spell and status menus are the same navy elsewhere, and
    #  their item names are in the dump too, so a box anywhere else is not read
    band = navy[240:376]
    rows = np.where(band.mean(axis=1) > 0.35)[0] + 240
    if len(rows) < 80 or rows.min() > 270 or rows.max() < 340:
        return None
    if navy[180:236].mean(axis=1).max() > 0.35:      # navy above the box too: a menu
        return None
    y0, y1 = rows.min(), rows.max()
    cols = np.where(navy[y0:y1 + 1].mean(axis=0) > 0.5)[0]
    if len(cols) < 200:
        return None
    return int(y0), int(y1), int(cols.min()), int(cols.max())


def ink_of(screen, x0, x1):
    white = screen.min(axis=2)                        # white text: all channels high
    ink = np.clip((white - 0.45) / 0.4, 0, 1)
    ink[:, :x0] = 0
    ink[:, x1 + 1:] = 0
    return ink


def read_frame(frame, series, reader):
    """frame: the video frame (HxWx3 uint8) -> text lines on the dialogue box, [] if none."""
    screen = game_screen(frame, series)
    box = text_box(screen)
    if not box:
        return []
    y0, y1, x0, x1 = box
    inks = [ink_of(game_screen(frame, series, sh), x0, x1) for sh in SHIFTS]
    lines = []
    for row in range(y0 // CELL_H, y1 // CELL_H + 1):
        bands = [ink[row * CELL_H:(row + 1) * CELL_H] for ink in inks]
        if bands[0].shape[0] < CELL_H or max(b.max() for b in bands) < 0.6:
            continue
        text = reader.read_row(bands)
        if text.replace('?', '').strip():
            lines.append(text)
    return lines


def read_screen(screen, reader):
    """A 640x400 screen already at game resolution (no sub-pixel search)."""
    box = text_box(screen)
    if not box:
        return []
    y0, y1, x0, x1 = box
    ink = ink_of(screen, x0, x1)
    lines = []
    for row in range(y0 // CELL_H, y1 // CELL_H + 1):
        band = ink[row * CELL_H:(row + 1) * CELL_H]
        if band.shape[0] < CELL_H or band.max() < 0.6:
            continue
        text = reader.read_row(band)
        if text.replace('?', '').strip():
            lines.append(text)
    return lines


# ---- video sampling ----------------------------------------------------------------

def keyframe_times(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-skip_frame', 'nokey', '-select_streams', 'v:0',
                          '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'csv=p=0', path],
                         capture_output=True, text=True).stdout
    return [float(t) for t in out.split() if t]


def keyframes(path, series):
    """Yield (t, frame HxWx3 uint8) for every keyframe of the video (whole frames: the
    sub-pixel search in read_frame needs the original pixels, not a fixed crop)."""
    fw, fh = SERIES[series]['frame']
    times = keyframe_times(path)
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-skip_frame', 'nokey', '-i', path,
                          '-vf', 'scale=%d:%d' % (fw, fh),
                          '-vsync', '0', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         stdout=subprocess.PIPE, bufsize=fw * fh * 3 * 4)
    n = fw * fh * 3
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        t = times[i] if i < len(times) else None
        i += 1
        yield t, np.frombuffer(buf, dtype=np.uint8).reshape(fh, fw, 3)
    p.wait()


def read_video(path, series, part, reader, log=print):
    """-> readings [{'series', 'part', 't', 'text', 'lines'}] for every keyframe with text."""
    out, last = [], None
    for t, frame in keyframes(path, series):
        lines = read_frame(frame, series, reader)
        if not lines:
            continue
        text = ' '.join(lines)
        if text == last:                              # the same page, still up
            continue
        last = text
        out.append({'series': series, 'part': part, 't': int(round(t or 0)), 'text': text, 'lines': lines})
        log('%6d  %s' % (t or 0, text[:60]))
        sys.stdout.flush()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input', help='a frame image or a video file')
    ap.add_argument('--series', default='werdna')
    ap.add_argument('--part', type=int, default=1)
    ap.add_argument('--out')
    args = ap.parse_args()
    reader = Reader()
    if args.input.lower().endswith(('.png', '.jpg', '.jpeg')):
        from PIL import Image
        frame = np.asarray(Image.open(args.input).convert('RGB'))
        lines = (read_frame(frame, args.series, reader) if frame.shape[1] != GAME_W
                 else read_screen(frame.astype(np.float32) / 255, reader))
        for line in lines:
            print(line)
        return
    readings = read_video(args.input, args.series, args.part, reader)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(readings, fh, ensure_ascii=False, indent=1)
        print('%d readings -> %s' % (len(readings), args.out))


if __name__ == '__main__':
    main()
