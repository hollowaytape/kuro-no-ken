"""Try every NPC and trigger zone on the current map, from one state, and report.

A focused regression test: after a pointer change, walk into everything on the affected
map and check nothing exits to DOS. Unlike autoplay this commits to nothing - it rolls
back to the same state for each target - so it covers the whole map.

    python tools/sweep_map.py STATE [--enter KIND:INDEX]
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from kuro_core import CoreEmu                 # noqa: E402
from kuro_test import Tester, GameOver        # noqa: E402
from kuro_emu import Blocked                  # noqa: E402

state = sys.argv[1]
enter = next((a.split('=', 1)[1] for a in sys.argv[2:] if a.startswith('--enter=')), None)
e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
e.load_state(state)
e.set_noclip(True)
e.heal()
if enter:
    kind, idx = enter.split(':')
    t.goto_zone(int(idx), kind=kind, timeout=30)
    t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 60})
# A state saved the instant a map loads still has the player frozen, and then every
# target reports "no movement" and the sweep proves nothing. Wait for control.
for _ in range(12):
    p0 = e.pos()
    e.tap('LEFT', 0.3)          # one direction only: LEFT then RIGHT nets to zero and
    e.wait(0.4)                 # would look like "cannot move" even when it can
    moved = e.pos() != p0
    e.tap('RIGHT', 0.3)
    e.wait(0.4)
    if moved or e.state() != 'field':
        break
    t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 20})
print('player control:', 'yes' if moved else 'NO - frozen', e.pos())
print('sweeping', e.map_name(), e.state(), '-', len(e.zones()), 'zones')
base = e.m.save_state()
targets = [('npc', o['slot']) for o in e.objects()] + \
          [(z['kind'], z['index']) for z in e.zones() if z['enabled']]
crashes = []
for kind, idx in targets:
    e.m.load_state(base)
    e._last_lines = None
    e.set_noclip(True)
    e.heal()
    t.pages, t.issues = [], []
    try:
        if kind == 'npc':
            t.talk_to(idx)
        else:
            t.goto_zone(idx, kind=kind, timeout=20)
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 60})
        note = 'ok'
    except GameOver:
        note = 'game over'
    except Blocked as ex:
        note = 'blocked: %s' % str(ex)[:40]
    except Exception as ex:
        note = '%s: %s' % (type(ex).__name__, str(ex)[:40])
    st = e.state()
    if st == 'dos':
        note = 'CRASHED TO DOS'
        crashes.append((kind, idx))
    print('  %-4s %2d  %-9s %-12s %2d page(s)  %s'
          % (kind, idx, st, e.map_name(), len(t.pages), note))
print('%d targets, %d crashes' % (len(targets), len(crashes)))
sys.exit(1 if crashes else 0)
