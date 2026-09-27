"""How fast does the title card's frame loop run on a given disk?

The opening's loop at cs:0x0e28 increments the word at cs:0x0c34 once per pass
(it paces itself on vsync). If extra sprites make a pass overrun a frame, the
count per emulated second drops. Compare a built disk against the original:

    python tools/title_timing.py                 # original disk
    python tools/title_timing.py patched/test_title.hdi
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from kuro_core import CoreEmu                  # noqa: E402
from romtools.np2core import FRAMES_PER_SECOND  # noqa: E402

COUNTER = (0x26d8 << 4) + 0x0c34


def rate(hdd, seconds=10):
    e = CoreEmu(hdd=hdd)
    e.m.run(1800)
    for _ in range(40):
        row = e.launcher_cursor()
        if row is None:
            break
        e.press('SPACE' if row == 1 else ('UP' if row > 1 else 'DOWN'),
                gap=2.0 if row == 1 else 0.5)
    for _ in range(10):
        if e.title_cursor() == 0:
            break
        e.press('UP', gap=0.6)
    e.wait(0.5)
    e.press('SPACE')
    e.m.run(56 * 80)                           # past the burn-in
    c0 = e.m.read16(COUNTER)
    frames = int(seconds * FRAMES_PER_SECOND)
    e.m.run(frames)
    c1 = e.m.read16(COUNTER)
    return ((c1 - c0) & 0xffff) / frames


if __name__ == '__main__':
    hdd = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, 'original', 'Blade of Darkness (Kuro no Ken).hdi')
    print('%s: %.3f loop passes per frame' % (os.path.basename(hdd), rate(hdd)))
