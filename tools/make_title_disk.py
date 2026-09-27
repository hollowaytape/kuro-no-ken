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

The artwork is the whole title stencil: `--template` writes the stock one
(the Japanese in white), the artist adds to it, and `--mask` builds from their
file. White pixels the kanji's own sprites don't cover get new sprites, fitted
automatically by `ipl_sprites.fit` (192/112px wide, on an 8px grid, joins
steered into the gaps between strokes).

Usage:
    python tools/make_title_disk.py                    # default English line
    python tools/make_title_disk.py --template         # write img/title/artist/title_mask.png
    python tools/make_title_disk.py --mask art.png     # build from the artist's file
    python tools/make_title_disk.py --mask art.png --plan   # just show the sprite plan
    python tools/make_title_disk.py ... --shot         # ...and screenshot it in-game
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
ARTIST = os.path.join(ASSETS, 'artist')
TEMPLATE = os.path.join(ARTIST, 'title_mask.png')
SUBTITLE = 'BLADE OF DARKNESS'
FONT = (r'C:\Windows\Fonts\GOUDOSB.TTF', 50)
TOP = 330          # the default subtitle's first row
PAD = 8            # rows of ground glow cleared above and below new artwork
FIRE_ROW = 230     # texture row that lights the top of artwork below the kanji


# ---------------------------------------------------------------- artwork
def subtitle_mask(text=SUBTITLE, font=FONT, top=TOP):
    """The default English line, used when no artwork file is given."""
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
    return out


def stock_layers(base_stream, rects):
    """Split DS_T1's stencil into the Japanese (inside the kanji rectangles)
    and the ground glow (the dithered band along the bottom, everything else)."""
    I = np.unpackbits(as2.stream_to_planes(base_stream)[3], axis=1)
    hole = I == 0
    inside = ipl_sprites.rect_mask(rects)
    return hole & inside, hole & ~inside


def write_template(jp, path=TEMPLATE):
    """The artist's canvas: the Japanese in white, everything else black."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray((jp * 255).astype(np.uint8), 'L').save(path)


def load_mask(path, jp):
    img = Image.open(path)
    if img.size != (640, 400):
        raise SystemExit('%s is %dx%d; the mask must stay 640x400'
                         % (path, img.size[0], img.size[1]))
    m = np.array(img.convert('L')) >= 128
    kept = (m & jp).sum() / jp.sum()
    if kept < 0.5:
        raise SystemExit('%s keeps only %d%% of the Japanese logo. The artwork '
                         'file is the whole title stencil - the Japanese stays in '
                         'it. (Wrong file? Older templates had only the English.)'
                         % (path, round(100 * kept)))
    if kept < 0.98:
        print('  note: %d%% of the original Japanese pixels changed'
              % round(100 * (1 - kept)))
    return m


def build_image(base_stream, mask, plan, glow):
    """DS_T1 with `mask` as the stencil. Fire is not baked in anywhere: the
    kanji sprites and the planned new sprites draw it every frame."""
    planes = as2.stream_to_planes(base_stream)
    B, R, G, I = [np.unpackbits(p, axis=1) for p in planes]
    keep_glow = glow.copy()
    for b in plan:                                  # clear the glow behind new art
        keep_glow[max(0, b['top'] - PAD):b['bottom'] + PAD, :] = False
    I[:] = 1
    I[mask | keep_glow] = 0
    art = mask & ~keep_glow
    B[art] = R[art] = G[art] = 0                    # colour 0 until a sprite fills it
    R[glow & ~keep_glow] = 0
    return as2.planes_to_stream([np.packbits(v, axis=1) for v in (B, R, G, I)]), I


# Measured with tools/title_timing.py: the title card's loop runs once every
# 2 frames, and keeps that pace until the new sprites add roughly this much
# blitting per frame (the kanji themselves draw ~106,000 px). Beyond it the
# flames slow down - 0.39 passes/frame at +165,000 px - but nothing breaks.
SPRITE_BUDGET = 125000


def describe(plan):
    area = sum(w * (b['bottom'] - b['top']) for b in plan for _, w in b['rects'])
    print('  new sprite area %d px of a ~%d px budget%s'
          % (area, SPRITE_BUDGET,
             '' if area <= SPRITE_BUDGET else
             '  <-- OVER: the flames will animate more slowly'))
    for b in plan:
        print('  rows %d-%d: %d sprite(s) at x %s, texture row %d'
              % (b['top'], b['bottom'] - 1, len(b['rects']),
                 ', '.join('%d+%d' % r for r in b['rects']), b['texture_row']))
        for x, n in b['joins']:
            print('    join at x=%d cuts through strokes on %d row(s)' % (x, n))


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


def stock_scn():
    raw = open(os.path.join(HERE, 'original', 'A.FA1'), 'rb').read()
    _, ents, _ = fa1_patch.parse(raw)
    e = next(x for x in ents if x['filename'] == '00IPL.SCN')
    return raw, decompress(raw[e['offset']:e['offset'] + e['clen']], e['dlen'])


def plan_for(mask_path=None):
    """-> (raw A.FA1, stock SCN, mask, plan, glow)"""
    base = open(os.path.join(ASSETS, 'ds_t1_image.bin'), 'rb').read()
    raw, scn = stock_scn()
    rects = ipl_sprites.kanji_rects(scn)
    jp, glow = stock_layers(base, rects)
    mask = load_mask(mask_path, jp) if mask_path else jp | subtitle_mask()
    new = mask & ~ipl_sprites.rect_mask(rects)       # what the kanji don't cover
    plan = ipl_sprites.fit(new, FIRE_ROW)
    print('artwork: %d white pixels, %d need new sprites' % (mask.sum(), new.sum()))
    describe(plan)
    return raw, scn, base, mask, plan, glow


def main(shot=False, mask_path=None):
    orig = open(os.path.join(ASSETS, 'DS_T1.AS2'), 'rb').read()
    raw, scn, base, mask, plan, glow = plan_for(mask_path)

    stream, I = build_image(base, mask, plan, glow)
    np.save(os.path.join(ASSETS, 'stencil_subtitle.npy'), I)
    action_path, lit_leaves, enc = as2_author.author(stream)
    new_as2 = as2_author.assemble(orig, action_path, lit_leaves, enc)
    if not as2_author.verify(new_as2, stream):
        raise SystemExit('the authored file does not decode back to the artwork')
    print('DS_T1.AS2 %d -> %d (+%d), self-parse verified'
          % (len(orig), len(new_as2), len(new_as2) - len(orig)))
    with open(os.path.join(ASSETS, 'DS_T1_subtitle.AS2'), 'wb') as f:
        f.write(new_as2)
    archive = fa1_patch.replace(raw, 'DS_T1.AS2', new_as2)

    entries = ipl_sprites.entries_for(plan)
    scn2 = ipl_sprites.patch_ipl(scn, entries)
    packed = compress(scn2)
    assert decompress(packed, len(scn2)) == scn2
    print('00IPL.SCN %d -> %d bytes (%d stored), %d new sprite(s)'
          % (len(scn), len(scn2), len(packed), len(entries)))
    archive = fa1_patch.replace(archive, '00IPL.SCN', packed,
                                compressed=True, dlen=len(scn2))
    print('A.FA1 %d -> %d' % (len(raw), len(archive)))

    n = write_disk(archive)
    print('wrote %s (archive %d bytes, verified by read-back)' % (OUT_DISK, n))
    if shot:
        shoot()


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--subtitle' in args:
        raise SystemExit('--subtitle is gone: the artwork file is now the whole '
                         'title mask. Use --template, then --mask <file>.')
    if '--template' in args:
        base = open(os.path.join(ASSETS, 'ds_t1_image.bin'), 'rb').read()
        _, scn = stock_scn()
        jp, _ = stock_layers(base, ipl_sprites.kanji_rects(scn))
        write_template(jp)
        print('wrote', TEMPLATE)
        sys.exit(0)
    png = args[args.index('--mask') + 1] if '--mask' in args else None
    if '--plan' in args:                             # fit only, no build
        plan_for(png)
        sys.exit(0)
    main(shot='--shot' in args, mask_path=png)
