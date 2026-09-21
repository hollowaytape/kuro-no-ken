"""Reproduce a crash found by the autoplayer, on the patched disk and the original.

    python tools/repro_crash.py STATE KIND INDEX [--orig]

If it crashes on the patched disk but not the original, it is ours: something in the
reinserted text. Then tools/ptr_audit.py on the script that map loads says which
pointer the interpreter actually follows.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from kuro_core import CoreEmu            # noqa: E402
from kuro_test import Tester             # noqa: E402

state, kind, index = sys.argv[1], sys.argv[2], int(sys.argv[3])
# --then=kind:index hops again once the first zone has been taken (the manor interior
# is two zones in from the world map).
then = next((a.split('=', 1)[1] for a in sys.argv[2:] if a.startswith('--then=')), None)
orig = '--orig' in sys.argv
variant = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--disk=')), None)
e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
if variant:
    print('variant disk:', variant)
    e.reload_disk(os.path.abspath(os.path.join(HERE, variant)))
elif orig:
    from rominfo import SRC_DISK
    disk = os.path.join(HERE, '..', SRC_DISK)
    print('original disk:', disk)
    if disk:
        e.reload_disk(os.path.abspath(disk))
e.load_state(state)
e.set_noclip(True)
e.heal()
print('from', e.map_name(), e.state(), 'pos', e.pos())
try:
    t.goto_zone(index, kind=kind, timeout=30)
except Exception as ex:
    print('goto_zone:', type(ex).__name__, str(ex)[:70])
if then and e.state() != 'dos':
    t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 60})
    k2, i2 = then.split(':')
    print('now on', e.map_name(), '- hopping to', then)
    try:
        t.goto_zone(int(i2), kind=k2, timeout=30)
    except Exception as ex:
        print('second goto_zone:', type(ex).__name__, str(ex)[:60])
for _ in range(6):
    try:
        t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 60})
    except Exception as ex:
        print('settle:', type(ex).__name__, str(ex)[:70])
    print('  ->', e.state(), e.map_name(), e.pos())
    if e.state() == 'dos':
        print('CRASHED to DOS')
        break
d = e.dialogue() or {}
for l in (d.get('lines') or [])[:4]:
    print('   |' + l.strip()[:70])
