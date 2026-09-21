"""What does the interpreter read just before the manor-grounds crash?

Entering ysk1.mp1 on a disk where 03YSK01B.SCN is translated drops the game to DOS.
This watches reads of that script's slot (0x1800) while walking in, and prints the
last address-sized operands fetched, with the instruction that fetched them. The
known operand fetchers are BD 0x18a6e / 0x18b33 / 0x18aa9; anything they read is an
address the interpreter is about to follow.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from romtools.np2core import WATCH_READ, EV_READ     # noqa: E402
from kuro_core import CoreEmu                        # noqa: E402
from kuro_test import Tester                         # noqa: E402

SLOT = 0x26d80 + 0x1800
FETCHERS = (0x18a6e, 0x18b33, 0x18aa9)
state = sys.argv[1]
disk = sys.argv[2]
e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
e.reload_disk(os.path.abspath(os.path.join(HERE, disk)))
e.load_state(state)
e.set_noclip(True)
e.heal()
e.m.watch(SLOT, 0x1100, WATCH_READ)
e.m.events()
seq = []


def drain():
    for ev in e.m.events():
        if ev.kind == EV_READ and ev.size == 2:
            seq.append((ev.pc, ev.addr - SLOT))


try:
    t.goto_zone(3, kind='step', timeout=30)
except Exception as ex:
    print('goto_zone:', type(ex).__name__, str(ex)[:60])
drain()
if '--then' in ' '.join(sys.argv):
    # The interior is one zone further in; watch that transition instead.
    t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 60})
    drain()
    print('on', e.map_name(), '- taking the door')
    try:
        t.goto_zone(1, kind='step', timeout=30)
    except Exception as ex:
        print('door:', type(ex).__name__, str(ex)[:60])
    drain()
for _ in range(4):
    try:
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
    except Exception as ex:
        print('settle:', type(ex).__name__, str(ex)[:50])
    drain()
    if e.state() == 'dos':
        break
print('state now:', e.state(), e.map_name())
print('%d word reads of the slot' % len(seq))
ops = [(pc, off) for pc, off in seq if pc in FETCHERS]
print('address operands fetched (last 20):')
for pc, off in ops[-20:]:
    print('   pc %05x  offset 0x%04x' % (pc, off))
print('all reads, last 12:')
for pc, off in seq[-12:]:
    print('   pc %05x  offset 0x%04x' % (pc, off))
