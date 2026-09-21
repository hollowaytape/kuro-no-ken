"""Cold-boot a staged disk, teleport to the world map and save a field state.

A save state carries the game's cached archive directory, so a state taken on the normal
build desyncs the moment a staged disk moves a member. States for a staged disk have to
be made on that disk.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from bench import RenderBench, SEG                 # noqa: E402
from kuro_core import CoreEmu                      # noqa: E402
from kuro_test import Tester                       # noqa: E402

disk = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'scratch_emu/bsd_test.hdi')
dest = int(sys.argv[2]) if len(sys.argv) > 2 else 11        # 11 = stg, the world map
name = sys.argv[3] if len(sys.argv) > 3 else 'bsd_test_field'

t0 = time.time()
e = CoreEmu(hdd=disk)
t = Tester(emu=e, log=lambda *a: None)
t.start({'new_game': True})
print('new game started after %.0fs wall, map %s' % (time.time() - t0, e.map_name()))
# the new game opens on a cutscene; skip it until the player is standing on a map
for _ in range(400):
    if (e.map_name() or '').endswith('.mpc') and e.state() == 'field':
        break
    e.tap('SPACE', 0.1)
    e.wait(0.5)
print('reached %s (%s) after %.0fs wall' % (e.map_name(), e.state(), time.time() - t0))
e.set_noclip(True)
e.heal()

b = RenderBench.__new__(RenderBench)
b.e, b.t = e, t
b.base = e.m.save_state()
at = b.free_at(8)
e.write(SEG + at, bytes([0x20]) + int.to_bytes(3, 2, 'little')
        + int.to_bytes(dest, 2, 'little') + bytes([0x83]))
e.write(b.table() + 2 * 3, int.to_bytes(at, 2, 'little'))
b.arm(3)
for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
    e.tap(k, 0.25)
    e.wait(0.6)
    if e.map_name() and 'stg' in (e.map_name() or ''):
        break
e.wait(2.0)
print('now on %s (%s) after %.0fs wall' % (e.map_name(), e.state(), time.time() - t0))
e.save_state(name)
print('saved state %s' % name)
