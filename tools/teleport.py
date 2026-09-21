"""Teleport by running the same block a world-map exit runs.

Every exit on the world map is one instruction:

    20 <var 3> <N>   83        (opcode 0x20 writes a global word variable; the array is
                                at 16d8:06d2, and variable 3 is the destination)

so a synthetic block with any N sends the player there. That is the teleport this
project wanted for a long time, and it means a playtest can start anywhere rather than
walking the story in order.

    python tools/teleport.py STATE 2 3 5 ...    # try these destinations
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from bench import RenderBench, SEG              # noqa: E402

state = sys.argv[1]
dests = [int(a, 0) for a in sys.argv[2:]] or [2, 3]
b = RenderBench(state)
e = b.e
print('from %s (%s)' % (e.map_name(), e.state()))
for n in dests:
    b.reset()
    at = b.free_at(8)
    # n = -1 is the control: a block that does nothing, to see whether the map change
    # comes from this block at all or from the zone that triggered it.
    block = (bytes([0x83]) if n < 0 else
             bytes([0x20]) + int.to_bytes(3, 2, 'little') + int.to_bytes(n, 2, 'little')
             + bytes([0x83]))
    e.write(SEG + at, block)
    e.write(b.table() + 2 * 3, int.to_bytes(at, 2, 'little'))
    b.arm(3)
    for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
        e.tap(k, 0.25)
        e.wait(0.6)
        if e.state() != 'field':
            break
    for _ in range(6):
        e.wait(1.5)
        if e.state() == 'dos':
            break
    print('  destination %2d -> %-12s %-8s pos %s zones %d'
          % (n, e.map_name(), e.state(), e.pos(), len(e.zones())))
