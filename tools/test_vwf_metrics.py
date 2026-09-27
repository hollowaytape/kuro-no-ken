"""Check tools/vwf_metrics.py against the renderer: where does each line's ink end?

Renders one page of four lines with the VWF (the box at \\o13,17, so text starts at
x = 104) and compares, per line, the rightmost text pixel on screen with the model.

    python tools/test_vwf_metrics.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import RenderBench, NL, FF      # noqa: E402
import vwf_metrics                          # noqa: E402
import vwf_preview                          # noqa: E402

GFX_WHITE = (238, 238, 238)
X0, Y0 = 13 * 8, 17 * 16

LINES = [
    [b'The quick brown fox jumps over the lazy dog,',
     b'MINIMUM WAVES, illicit jiggly wombats; Mm Ww.',
     b'0123456789 !"#$%&\'()*+,-./:;<=>?@[]^_`{|}~',     # (no \\: it starts an escape)
     b'abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ'],
    [b'iiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiii i',
     b'Well, well. I suppose you think you are clever?',
     b'lllllllllll mmmmmmmmm .......... WWWWWWWW',
     b'Short.'],
]


def measure(img, row):
    y0 = Y0 + 16 * row
    right = -1
    for y in range(y0, y0 + 16):
        for x in range(X0, 560):
            if img.getpixel((x, y)) == GFX_WHITE:
                right = max(right, x)
    return right - X0 + 1 if right >= 0 else 0


def main():
    b = RenderBench('r03_manor_inside')
    bad = 0
    for lines in LINES:
        shots, _ = vwf_preview.run(b, NL.join(lines) + FF, 'vwf')
        for row, line in enumerate(lines):
            got, want = measure(shots[0], row), vwf_metrics.ink_end(line)
            ok = got == want
            bad += not ok
            print('%s  line %d: screen %3d px, model %3d px  %r' % (
                'ok ' if ok else 'BAD', row, got, want, line[:40]))
    print('mismatches:', bad)
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
