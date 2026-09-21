"""Build a disk image whose title card carries an English subtitle.

The whole chain, end to end:

    stencil artwork -> AS2 bitstream -> DS_T1.AS2 -> A.FA1 -> .hdi

Nothing here is a mock-up: the image goes through `as2.py`'s encoder, the
archive through `fa1_patch.py`, and the archive is written into the disk with
NDC, the same tool `romtools/disk.py` uses. `title_logo.py` covers how the
title card composes the result; `docs/as2_format_findings.md` covers the codec.

The file is authored from scratch rather than patched: `as2_author` fits a new
main tree *and* a new literal alphabet to the artwork, so the letters can use
the whole fire ramp instead of the seven byte values DS_T1 originally carried.
The result is parsed back with the ordinary reader and decoded before it is
allowed anywhere near a disk image.

`A.FA1` is rebuilt around the new member. It pads its entry table to a 0x400
boundary, so a member can grow by 904 bytes without the archive changing size
at all; this subtitle costs more than that, so the archive does grow, which is
fine because NDC writes it through the filesystem. (A byte-patch in the image
would not be: `A.FA1` is stored **non-contiguously**.)

Usage:
    python tools/make_title_disk.py                       # build patched/test_title.hdi
    python tools/make_title_disk.py --template            # write the artist's canvas
    python tools/make_title_disk.py --subtitle art.png    # build from the artist's file
    python tools/make_title_disk.py ... --shot            # ...and screenshot it in-game
"""
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import as2                                    # noqa: E402
import as2table                                # noqa: E402
import as2_author                              # noqa: E402
import fa1_patch                               # noqa: E402
import ipl_sprites                             # noqa: E402
from compress import compress                  # noqa: E402
from decompress import decompress              # noqa: E402

NDC = os.path.join(os.path.dirname(HERE), 'romtools', 'bin', 'NDC.EXE')
SRC_DISK = os.path.join(HERE, 'original', 'Blade of Darkness (Kuro no Ken).hdi')
OUT_DISK = os.path.join(HERE, 'patched', 'test_title.hdi')
ARCHIVE_DIR_IN_DISK = 'B-DRKNS'

ASSETS = os.path.join(HERE, 'img', 'title')
SUBTITLE = 'BLADE OF DARKNESS'
FONT = (r'C:\Windows\Fonts\GOUDOSB.TTF', 50)
TOP = 330          # first row of the subtitle
PAD = 8            # rows of ground-glow cleared above and below it
FIRE_ROW = 230     # which rows of the flame texture light the letters

# Where the subtitle may go. Fire only exists inside the three 192px sprite
# columns (x 48..623), and the zone starts below the lowest kanji stroke
# (剣's sprite ends at row 314). 84 rows keeps the texture sampling in range.
ZONE_X = (48, 624)
ZONE_Y = (316, 400)
ARTIST = os.path.join(ASSETS, 'artist')


# ---------------------------------------------------------------- artwork
def subtitle_mask(text=SUBTITLE, font=FONT, top=TOP):
    f = ImageFont.truetype(font[0], font[1])
    img = Image.new('L', (640, 140), 0)
    d = ImageDraw.Draw(img)
    widths = [d.textlength(c, font=f) for c in text]
    x = (640 - sum(widths)) / 2
    for c, w in zip(text, widths):
        d.text((x, 20), c, font=f, fill=255)
        x += w
    a = np.array(img) > 110
    ys, _ = np.where(a)
    crop = a[ys.min():ys.max() + 1]
    out = np.zeros((400, 640), bool)
    out[top:top + crop.shape[0]] = crop
    return out, (top, top + crop.shape[0] - 1)


def subtitle_from_png(path):
    """Read an artist's edit of the template: white (>= 50% grey) = letters."""
    img = Image.open(path)
    if img.size != (640, 400):
        raise SystemExit('%s is %dx%d; the template is 640x400 and must stay that size'
                         % (path, img.size[0], img.size[1]))
    a = np.array(img.convert('L')) >= 128
    zone = np.zeros_like(a)
    zone[ZONE_Y[0]:ZONE_Y[1], ZONE_X[0]:ZONE_X[1]] = True
    stray = a & ~zone
    if stray.any():
        ys, xs = np.where(stray)
        raise SystemExit('%d white pixels are outside the subtitle zone (x %d-%d, '
                         'y %d-%d), around x %d-%d y %d-%d; there is no fire there, '
                         'so they would be invisible'
                         % (stray.sum(), ZONE_X[0], ZONE_X[1] - 1, ZONE_Y[0],
                            ZONE_Y[1] - 1, xs.min(), xs.max(), ys.min(), ys.max()))
    if not a.any():
        raise SystemExit('%s has no white pixels in the subtitle zone' % path)
    ys, _ = np.where(a)
    return a, (int(ys.min()), int(ys.max()))


def write_template(base_stream, path):
    """A 640x400 canvas for the artist: the zone, the calligraphy for scale,
    and the current subtitle in white as a starting point."""
    planes = as2.stream_to_planes(base_stream)
    I = np.unpackbits(planes[3], axis=1)
    rgb = np.zeros((400, 640, 3), np.uint8)
    kanji = (I == 0)
    kanji[ZONE_Y[0]:, :] = False
    rgb[kanji] = (70, 70, 70)                               # reference only
    x0, x1 = ZONE_X
    y0, y1 = ZONE_Y
    rgb[y0:y1, x0:x1] = (20, 20, 60)                        # the editable zone
    rgb[y0, x0:x1] = rgb[y1 - 1, x0:x1] = (90, 90, 120)
    rgb[y0:y1, x0] = rgb[y0:y1, x1 - 1] = (90, 90, 120)
    text, _ = subtitle_mask()
    rgb[text] = (255, 255, 255)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(rgb).save(path)


def build_image(base_stream, text=None):
    """Original stencil, plus holes for the English letters.

    The letters' fire is not baked in: ipl_sprites draws it every frame from
    the same animated textures as the kanji.
    """
    planes = as2.stream_to_planes(base_stream)
    B, R, G, I = [np.unpackbits(p, axis=1) for p in planes]
    if text is None:
        text, (y0, y1) = subtitle_mask()
    else:
        text, (y0, y1) = text
    band = slice(max(ZONE_Y[0], y0 - PAD), min(ZONE_Y[1], y1 + PAD + 1))
    R[band, :] = 0                           # drop the ground glow behind the line
    I[band, :] = 1                           # hide that band ...
    B[text] = R[text] = G[text] = 0          # colour 0 = invisible until the
    I[text] = 0                              # sprites fill it, like the kanji
    stream = as2.planes_to_stream([np.packbits(v, axis=1) for v in (B, R, G, I)])
    return stream, I, (y0, y1)


# ---------------------------------------------------------------- disk
def ndc(*args):
    r = subprocess.run([NDC] + list(args), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError('NDC %s failed: %s'
                           % (args[0], r.stdout.decode('shift-jis', 'replace')))


def write_disk(archive):
    stage = os.path.join(HERE, 'patched', '_stage')
    os.makedirs(stage, exist_ok=True)
    staged = os.path.join(stage, 'A.FA1')
    with open(staged, 'wb') as f:
        f.write(archive)
    shutil.copyfile(SRC_DISK, OUT_DISK)
    ndc('D', OUT_DISK, '0', ARCHIVE_DIR_IN_DISK + r'\A.FA1')
    ndc('P', OUT_DISK, '0', staged, ARCHIVE_DIR_IN_DISK)
    # read it back and prove the disk holds exactly what we built
    back = os.path.join(stage, 'back')
    os.makedirs(back, exist_ok=True)
    got_path = os.path.join(back, 'A.FA1')
    if os.path.exists(got_path):
        os.remove(got_path)
    ndc('G', OUT_DISK, '0', ARCHIVE_DIR_IN_DISK + r'\A.FA1', back)
    with open(got_path, 'rb') as f:
        got = f.read()
    if got != archive:
        raise RuntimeError('archive read back from the disk does not match')
    return len(got)


def shoot(out_dir=os.path.join(ASSETS, 'review')):
    """Boot the built disk, watch the opening to the title card, save a
    screenshot and a short GIF."""
    from kuro_core import CoreEmu
    os.makedirs(out_dir, exist_ok=True)
    e = CoreEmu(hdd=OUT_DISK)
    e.m.run(1800)
    for _ in range(40):                       # cold-boot launcher
        row = e.launcher_cursor()
        if row is None:
            break
        e.press('SPACE' if row == 1 else ('UP' if row > 1 else 'DOWN'),
                gap=2.0 if row == 1 else 0.5)
    for _ in range(10):                       # title menu -> Watch Opening
        if e.title_cursor() == 0:
            break
        e.press('UP', gap=0.6)
    e.wait(0.5)
    e.press('SPACE')
    e.m.run(56 * 80)                          # through the burn-in
    frames = []
    for _ in range(24):
        e.m.run(2)
        frames.append(e.image().convert('RGB'))
    frames[0].save(os.path.join(out_dir, 'title.png'))
    gs = [f.convert('P', palette=Image.ADAPTIVE, colors=32) for f in frames]
    gs[0].save(os.path.join(out_dir, 'title.gif'), save_all=True,
               append_images=gs[1:], duration=60, loop=0, optimize=True)
    print('review images in %s' % out_dir)


def main(shot=False, subtitle=None):
    orig = open(os.path.join(ASSETS, 'DS_T1.AS2'), 'rb').read()
    base = open(os.path.join(ASSETS, 'ds_t1_image.bin'), 'rb').read()
    text = subtitle_from_png(subtitle) if subtitle else None
    stream, I, rows = build_image(base, text)
    np.save(os.path.join(ASSETS, 'stencil_subtitle.npy'), I)

    print('authoring subtitle rows %s ...' % (rows,))
    action_path, lit_leaves, enc = as2_author.author(stream)
    new = as2_author.assemble(orig, action_path, lit_leaves, enc)
    if not as2_author.verify(new, stream):
        raise SystemExit('the authored file does not decode back to the artwork')
    print('DS_T1.AS2 %d -> %d (+%d), self-parse verified'
          % (len(orig), len(new), len(new) - len(orig)))
    with open(os.path.join(ASSETS, 'DS_T1_subtitle.AS2'), 'wb') as f:
        f.write(new)

    raw = open(os.path.join(HERE, 'original', 'A.FA1'), 'rb').read()
    archive = fa1_patch.replace(raw, 'DS_T1.AS2', new)

    # the opening's code: three more flame sprites behind the subtitle
    _, ents, _ = fa1_patch.parse(archive)
    e = next(x for x in ents if x['filename'] == '00IPL.SCN')
    scn = decompress(archive[e['offset']:e['offset'] + e['clen']], e['dlen'])
    entries = ipl_sprites.sprite_entries(rows[0], rows[1] - rows[0] + 1, FIRE_ROW)
    scn2 = ipl_sprites.patch_ipl(scn, entries)
    packed = compress(scn2)
    assert decompress(packed, len(scn2)) == scn2
    print('00IPL.SCN %d -> %d bytes (%d stored), sprite entries %s'
          % (len(scn), len(scn2), len(packed), entries))
    archive = fa1_patch.replace(archive, '00IPL.SCN', packed,
                                compressed=True, dlen=len(scn2))
    grew = len(new) - len(orig)
    print('A.FA1 %d -> %d (member grew %d, table pad was %d)'
          % (len(raw), len(archive), grew, fa1_patch.headroom(raw)))

    n = write_disk(archive)
    print('wrote %s (archive %d bytes, verified by read-back)' % (OUT_DISK, n))

    if shot:
        shoot()


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--template' in args:
        base = open(os.path.join(ASSETS, 'ds_t1_image.bin'), 'rb').read()
        write_template(base, os.path.join(ARTIST, 'subtitle_template.png'))
        print('wrote', os.path.join(ARTIST, 'subtitle_template.png'))
        sys.exit(0)
    png = None
    if '--subtitle' in args:
        png = args[args.index('--subtitle') + 1]
    main(shot='--shot' in args, subtitle=png)
