"""The progression flags: a bitfield at 16d8:08d2.

Found by reading the interpreter: opcode 0x0d ("branch if flag set") calls BD.BIN
0x17dd, which takes a 16-bit flag index and computes

    byte 0x8d2 + index / 8,  bit  index % 8

so the flags the scripts test live in one bit array. Comparing two save states shows
which flags an event set.

    python tools/flags.py STATE              # list the set flags
    python tools/flags.py STATE_A STATE_B    # what changed between them
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from kuro_core import CoreEmu                  # noqa: E402

BD = 0x16d80
FLAGS = 0x08d2
NBYTES = 0x40


def read(e, state):
    e.load_state(state)
    return bytes(e.read(BD + FLAGS, NBYTES))


def set_flags(raw):
    return {i for i in range(NBYTES * 8) if raw[i >> 3] & (1 << (i & 7))}


e = CoreEmu()
a = read(e, sys.argv[1])
if len(sys.argv) > 2:
    b = read(e, sys.argv[2])
    sa, sb = set_flags(a), set_flags(b)
    print('%s: %d flags set' % (sys.argv[1], len(sa)))
    print('%s: %d flags set' % (sys.argv[2], len(sb)))
    print('set in the second but not the first: %s'
          % ' '.join('%#x' % f for f in sorted(sb - sa)[:40]))
    print('cleared in the second: %s'
          % ' '.join('%#x' % f for f in sorted(sa - sb)[:40]))
else:
    s = set_flags(a)
    print('%s: %d flags set: %s' % (sys.argv[1], len(s),
                                    ' '.join('%#x' % f for f in sorted(s)[:60])))
