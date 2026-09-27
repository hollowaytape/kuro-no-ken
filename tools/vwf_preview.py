"""Show dialogue with the variable-width font, next to the same text in text mode.

Patches MB3N (tools/mb3_gfx.py, with the VWF) and 99CMN (tools/dialogue_gfx.py) in RAM,
runs a dialogue block through the real box routines, and saves the box of each page -
text mode above, VWF below - to scratch_emu/vwf/<name>.png.

    python tools/vwf_preview.py [STATE] [--text "Line one\\nLine two"]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import RenderBench, NL, FF                     # noqa: E402
from PIL import Image                                     # noqa: E402
import test_mb3_gfx as t                                  # noqa: E402
import mb3_gfx                                            # noqa: E402
import dialogue_gfx                                       # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scratch_emu', 'vwf')
PAGE = FF + bytes([0x00, 0x3b, 0x40, 0x02])

SAMPLE = (b'Karin' + NL + b'\\i2The quick brown fox jumps over the lazy dog,' + NL +
          b'then wanders off to find something better to do.' + NL +
          b'Digits and marks: 0123456789 !?,.\'"()-:;' + NL +
          b'MINIMUM WAVES, illicit jiggly wombats; Mm Ww Ii ll.' + PAGE +
          b'A second page, long enough that the old fifty-column limit would have made the '
          b'engine wrap it, to see where it wraps now.' + FF)


def run(b, text, how):
    t.TEXT = text
    orig = mb3_gfx.apply_to_ram
    if how == 'vwf':
        how = 'script'
        mb3_gfx.apply_to_ram = lambda m, vwf=True: orig(m, vwf=True)
    try:
        shots, _areas, mode_after = t.render(b, [], how)
    finally:
        mb3_gfx.apply_to_ram = orig
    return shots, mode_after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state', nargs='?', default='r03_manor_inside')
    ap.add_argument('--text', help='raw text; \\n = new line, \\f = new page')
    ap.add_argument('--name', default='sample')
    args = ap.parse_args()
    text = SAMPLE
    if args.text:
        pages = args.text.encode('cp932').split(b'\\f')
        text = PAGE.join(p.replace(b'\\n', NL) for p in pages) + FF
    os.makedirs(OUT, exist_ok=True)
    b = RenderBench(args.state)
    plain, _ = run(b, text, 'text')
    vwf, mode_after = run(b, text, 'vwf')
    box = (80, 250, 560, 372)
    h = box[3] - box[1]
    sheet = Image.new('RGB', (box[2] - box[0], 2 * h * (len(vwf) - 1)))
    for i, (p, v) in enumerate(zip(plain[:-1], vwf[:-1])):
        sheet.paste(p.crop(box), (0, 2 * h * i))
        sheet.paste(v.crop(box), (0, 2 * h * i + h))
    path = os.path.join(OUT, args.name + '.png')
    sheet.save(path)
    print('%s: %d page(s), text mode after the block: %s' % (path, len(vwf) - 1, mode_after == 1))


if __name__ == '__main__':
    main()
