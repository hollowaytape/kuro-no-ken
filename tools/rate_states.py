"""Which saved states are actually usable as an autoplay start?

A state is usable when the game is on a real map (a scene or battle has hundreds of
"zones"), the player can move, and nothing kills us while we stand still.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from kuro_core import CoreEmu            # noqa: E402
from kuro_test import Tester, GameOver   # noqa: E402

e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
for name in sys.argv[1:]:
    try:
        e.load_state(name)
    except Exception as ex:
        print('%-18s load failed: %s' % (name, ex))
        continue
    e._last_lines = None
    e.set_noclip(True)
    e.heal()
    st, zones = e.state(), len(e.zones())
    if st != 'field' or zones > 80:
        print('%-18s %-9s %3d zones - not a map' % (name, st, zones))
        continue
    p0 = e.pos()
    try:
        for k in ('LEFT', 'LEFT', 'UP', 'UP'):
            e.tap(k, 0.3)
            e.wait(0.4)
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
        note = 'ok' if e.state() == 'field' else 'became ' + e.state()
    except GameOver:
        note = 'GAME OVER'
    except Exception as ex:
        note = type(ex).__name__
    print('%-18s field %-12s %3d zones  %s -> %s  %s'
          % (name, e.map_name(), zones, p0, e.pos(), note))
