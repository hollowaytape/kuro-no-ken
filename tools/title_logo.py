"""Kuro no Ken's flaming title logo: asset extraction and re-authoring.

The opening's title card is a *stencil* effect, not a picture of burning
letters (see docs/title_logo_findings.md for how this was established):

  * planes B/R/G (0xA8000/0xB0000/0xB8000) hold a 3-bit fire image, blitted
    from a static 192x376 texture as three 192px-wide sprites, one per kanji;
  * plane I (0xE0000) holds the *inverted* calligraphy stencil: 1 = hide;
  * palette entries 8..15 are all set to the background maroon (68,0,0), so
    every stencilled-out pixel is invisible no matter what the fire says;
  * palette entries 0..7 are the fire ramp. The flames animate by a 3-frame
    texture flipbook, a vertical wobble of the sprites' source rows, and a
    palette pulse on entries 2 and 3 (see docs/title_logo_findings.md).

So "add English text with the flames showing through" means: punch more holes
in the stencil, and make sure fire has been blitted behind them.

Usage:
    python tools/title_logo.py extract          # pull mask + fire texture out of RAM
    python tools/title_logo.py compose          # write img/title/title_new.png
    python tools/title_logo.py preview          # inject into the emulator, screenshot

`extract` drives the headless emulator (romtools/np2core) to the title card on
the ORIGINAL disk -- the patched build's opening is broken, see the findings
doc -- and reads the planes straight out of VRAM.
"""
import os
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
OUT = os.path.join(HERE, 'img', 'title')
STATE = os.path.join(OUT, 'title_card.state')
ORIGINAL_DISK = os.path.join(HERE, 'original', 'Blade of Darkness (Kuro no Ken).hdi')

# Read back from the running game (see docs/title_logo_findings.md).
FIRE_RAMP = [(68, 0, 0), (0, 0, 0), (119, 0, 0), (238, 0, 0),
             (255, 119, 0), (255, 221, 68), (255, 160, 0), (255, 255, 255)]
BACKGROUND = (68, 0, 0)

PLANES_RGB = (0xA8000, 0xB0000, 0xB8000)   # the 3 fire bits
PLANE_I = 0xE0000                          # the inverted stencil

TEX_SEG = 0x38a8        # segment the flame texture lives in, at the title card
TEX_PLANE = 0x2340      # bytes per plane: 24 bytes/row * 376 rows
TEX_BYTES_PER_ROW = 24  # 192 px

# The English subtitle. A 192px-wide sprite is the engine's unit, so three of
# them (x=48,240,432) cover the width of the Japanese logo.
SUBTITLE = 'BLADE OF DARKNESS'
SUBTITLE_FONT = ('GOUDOSB.TTF', 50, 0)   # Goudy Old Style Bold, no extra tracking
SUBTITLE_TOP = 330
SUBTITLE_SRC_ROW = 230   # which rows of the flame texture light the letters
SPRITE_XS = (48, 240, 432)
SPRITE_W = 192


# --------------------------------------------------------------------------
# extraction

def _boot_to_title_card():
    """Boot the original disk and sit on the finished title card."""
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.dirname(HERE))
    from kuro_core import CoreEmu

    emu = CoreEmu(hdd=ORIGINAL_DISK)
    emu.m.run(1800)
    for _ in range(40):                       # cold-boot launcher
        row = emu.launcher_cursor()
        if row is None:
            break
        if row == 1:
            emu.press('SPACE', gap=2.0)
        else:
            emu.press('UP' if row > 1 else 'DOWN', gap=0.5)
    for _ in range(10):                       # title menu -> "Watch Opening"
        if emu.title_cursor() == 0:
            break
        emu.press('UP', gap=0.6)
    emu.wait(0.5)
    emu.press('SPACE')
    emu.m.run(56 * 80)                        # through the burn-in
    return emu


def _planes_to_index(emu, base, count):
    idx = np.zeros((400, 640), np.uint8)
    for p in range(count):
        raw = np.frombuffer(emu.m.read(base[p], 80 * 400), np.uint8).reshape(400, 80)
        idx |= (np.unpackbits(raw, axis=1) << p).astype(np.uint8)
    return idx


def extract():
    os.makedirs(OUT, exist_ok=True)
    emu = _boot_to_title_card()
    with open(STATE, 'wb') as f:
        f.write(zlib.compress(emu.m.save_state()))
    emu.m.run(1)

    fire = _planes_to_index(emu, PLANES_RGB, 3)
    stencil = np.unpackbits(
        np.frombuffer(emu.m.read(PLANE_I, 80 * 400), np.uint8).reshape(400, 80), axis=1)
    mask = (1 - stencil).astype(np.uint8)     # 1 = show the fire

    rows = TEX_PLANE // TEX_BYTES_PER_ROW
    tex = np.zeros((rows, TEX_BYTES_PER_ROW * 8), np.uint8)
    for p in range(3):
        raw = np.frombuffer(emu.m.read((TEX_SEG << 4) + p * TEX_PLANE, TEX_PLANE),
                            np.uint8).reshape(rows, TEX_BYTES_PER_ROW)
        tex |= (np.unpackbits(raw, axis=1) << p).astype(np.uint8)

    np.save(os.path.join(OUT, 'screen_fire.npy'), fire)
    np.save(os.path.join(OUT, 'mask_original.npy'), mask)
    np.save(os.path.join(OUT, 'fire_texture.npy'), tex)
    Image.fromarray(mask * 255).save(os.path.join(OUT, 'mask_original.png'))
    _save_fire(tex, os.path.join(OUT, 'fire_texture.png'))
    print('mask pixels %d, texture %s' % (mask.sum(), tex.shape))


def _save_fire(arr, path):
    rgb = np.zeros(arr.shape + (3,), np.uint8)
    for v in range(8):
        rgb[arr == v] = FIRE_RAMP[v]
    Image.fromarray(rgb).save(path)


# --------------------------------------------------------------------------
# composing a new stencil

def _text_stencil(text, fontfile, size, tracking, y_top, width=640):
    font = ImageFont.truetype(os.path.join(r'C:\Windows\Fonts', fontfile), size)
    img = Image.new('L', (width, 160), 0)
    draw = ImageDraw.Draw(img)
    widths = [draw.textlength(c, font=font) for c in text]
    x = (width - (sum(widths) + tracking * (len(text) - 1))) / 2
    for c, w in zip(text, widths):
        draw.text((x, 20), c, font=font, fill=255)
        x += w + tracking
    a = np.array(img) > 110
    ys, _ = np.where(a)
    crop = a[ys.min():ys.max() + 1]
    out = np.zeros((400, width), bool)
    out[y_top:y_top + crop.shape[0]] = crop
    return out, (y_top, y_top + crop.shape[0] - 1)


def compose(tag='new'):
    mask = np.load(os.path.join(OUT, 'mask_original.npy')).astype(bool)
    fire = np.load(os.path.join(OUT, 'screen_fire.npy')).copy()
    tex = np.load(os.path.join(OUT, 'fire_texture.npy'))

    text, (y0, y1) = _text_stencil(SUBTITLE, *SUBTITLE_FONT, SUBTITLE_TOP)
    h = y1 - y0 + 1
    for x0 in SPRITE_XS:                      # engine-style 192px fire sprites
        fire[y0:y0 + h, x0:x0 + SPRITE_W] = tex[SUBTITLE_SRC_ROW:SUBTITLE_SRC_ROW + h,
                                                :SPRITE_W]
    mask[max(0, y0 - 6):min(400, y1 + 7), :] = False   # drop the ground-glow dither
    mask |= text                                       # punch the letters

    rgb = np.zeros((400, 640, 3), np.uint8)
    rgb[:] = BACKGROUND
    for v in range(8):
        rgb[(fire == v) & mask] = FIRE_RAMP[v]

    Image.fromarray(rgb).save(os.path.join(OUT, 'title_%s.png' % tag))
    Image.fromarray((mask * 255).astype(np.uint8)).save(os.path.join(OUT, 'mask_%s.png' % tag))
    np.save(os.path.join(OUT, 'mask_%s.npy' % tag), mask.astype(np.uint8))
    np.save(os.path.join(OUT, 'fire_%s.npy' % tag), fire)
    print('subtitle rows %d-%d -> img/title/title_%s.png' % (y0, y1, tag))


# --------------------------------------------------------------------------
# preview: push the new planes into the live game and screenshot it

def _pack(bits):
    return np.packbits(bits.astype(np.uint8), axis=1).tobytes()


def preview(tag='new', frames=26, gif=True):
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.dirname(HERE))
    from kuro_core import CoreEmu

    emu = CoreEmu(hdd=ORIGINAL_DISK)
    with open(STATE, 'rb') as f:
        emu.m.load_state(zlib.decompress(f.read()))
    mask = np.load(os.path.join(OUT, 'mask_%s.npy' % tag)).astype(bool)
    fire = np.load(os.path.join(OUT, 'fire_%s.npy' % tag)).astype(np.uint8)

    shots = []
    for _ in range(frames):
        emu.m.run(1)
        for p, addr in enumerate(PLANES_RGB):
            emu.m.write(addr, _pack(((fire >> p) & 1).astype(bool)))
        emu.m.write(PLANE_I, _pack(~mask))
        emu.m.run(1)
        shots.append(emu.image().convert('RGB'))

    shots[0].save(os.path.join(OUT, 'title_%s_ingame.png' % tag))
    if gif:
        gs = [s.convert('P', palette=Image.ADAPTIVE, colors=32) for s in shots]
        gs[0].save(os.path.join(OUT, 'title_%s.gif' % tag), save_all=True,
                   append_images=gs[1:], duration=60, loop=0, optimize=True)
    print('wrote img/title/title_%s_ingame.png' % tag)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'compose'
    {'extract': extract, 'compose': compose, 'preview': preview}[cmd]()
