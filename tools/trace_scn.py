"""Which script offsets the interpreter executes from a state over N seconds (hub, stage, scene).

    python tools/trace_scn.py STATE SECONDS [KEY,KEY]
"""
import sys, glob, collections
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_emu import BD_SEG
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0])
state, secs = sys.argv[1], float(sys.argv[2])
keys = sys.argv[3].split(',') if len(sys.argv) > 3 and sys.argv[3] else []
e.load_state(state); e.wait(0.3)
FETCH = (BD_SEG << 4) + 0x33bb
e.m.hook(FETCH)
e.m.events()
for k in keys:
    e.tap(k, 0.15); e.wait(0.2)
e.wait(secs)
evs = e.m.events()
e.m.unhook(FETCH)
seen = collections.Counter(); order = []
for ev in evs:
    si = ev.regs.si
    if not order or order[-1] != si:
        order.append(si)
    seen[si] += 1
print('events', len(evs), 'dropped', e.m.events_dropped, 'distinct', len(seen))
def rng(lo, hi, label):
    offs = sorted(k for k in seen if lo <= k < hi)
    print('%s: %d offsets' % (label, len(offs)))
    # group into runs of consecutive-ish offsets
    runs = []
    for o in offs:
        if runs and o - runs[-1][1] <= 8: runs[-1][1] = o
        else: runs.append([o, o])
    print('   ' + ' '.join('%04x-%04x(%d)' % (a, b, sum(seen[k] for k in offs if a <= k <= b)) for a, b in runs)[:1500])
rng(0, 0x1800, 'hub'); rng(0x1800, 0x3d00, 'stage'); rng(0x3d00, 0x10000, 'scene')
