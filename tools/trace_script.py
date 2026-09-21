"""Record the sequence of script offsets an action executes, for comparing two builds.

One Machine per process, so each build has to be traced in its own run:

    python tools/trace_script.py ysk2_after_jumps npc:1 out_bad.json
    python tools/trace_script.py ysk2_plain2 npc:1 out_good.json --disk=v2_wo_03YSK01B.SCN.hdi

then `python tools/trace_script.py --diff out_good.json out_bad.json` maps the
patched offsets back through the file alignment and prints where the two runs first
disagree - which is where a wrong pointer sent the interpreter somewhere else.
"""
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))

if '--diff' in sys.argv:
    from check_pointers import as_script
    from deep_pointer_audit import offset_map
    good = json.load(open(sys.argv[2]))
    bad = json.load(open(sys.argv[3]))
    fn = sys.argv[4] if len(sys.argv) > 4 else '03YSK01B.SCN'
    o = open(os.path.join(HERE, '..', 'original', 'decompressed', fn), 'rb').read()
    p = as_script(open(os.path.join(HERE, '..', 'patched', fn), 'rb').read())
    amap = offset_map(o, p)
    rev = {v: k for k, v in amap.items()}
    SLOT1 = 0x1800

    def norm(seq, patched):
        """Offsets in original-file terms. A read inside an edited string has no
        counterpart, so it is dropped rather than compared raw - comparing raw
        manufactures a divergence wherever the English simply sits elsewhere."""
        out = []
        for pc, off in seq:
            if not patched or off < SLOT1:
                out.append((pc, off))
                continue
            src = rev.get(off - SLOT1)
            if src is not None:
                out.append((pc, SLOT1 + src))
        return out

    g, b = norm(good, False), norm(bad, True)
    print('good run: %d reads, bad run: %d reads' % (len(g), len(b)))
    # Align the two sequences instead of comparing position by position: one build
    # reads a few bytes more or fewer along the way, and a plain index comparison then
    # reports every later read as different.
    import difflib
    gs = [off for _pc, off in g]
    bs = [off for _pc, off in b]
    sm = difflib.SequenceMatcher(None, gs, bs, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        print('first difference after %d matching reads:' % i1)
        print('  good reads %s' % ' '.join('%#06x' % x for x in gs[i1:i2][:8]))
        print('  bad  reads %s' % ' '.join('%#06x' % x for x in bs[j1:j2][:8]))
        print('  context before: %s' % ' '.join('%#06x' % x for x in gs[max(0, i1 - 6):i1]))
        break
    else:
        print('the two runs read the same offsets throughout')
    sys.exit()

from romtools.np2core import WATCH_READ, EV_READ       # noqa: E402
from kuro_core import CoreEmu                          # noqa: E402
from kuro_test import Tester                           # noqa: E402

state, spec, out = sys.argv[1], sys.argv[2], sys.argv[3]
disk = next((a.split('=', 1)[1] for a in sys.argv[4:] if a.startswith('--disk=')), None)
SEG = 0x26d80
e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
if disk:
    e.reload_disk(os.path.abspath(os.path.join(HERE, disk)))
e.load_state(state)
e.set_noclip(True)
e.heal()
e.m.watch(SEG, 0x5000, WATCH_READ)
e.m.events()
seq = []


def drain():
    for ev in e.m.events():
        if ev.kind == EV_READ:
            seq.append((ev.pc, ev.addr - SEG))


# The event buffer holds 8192 events, and one action reads far more than that, so the
# trace has to be emptied as the game runs, not only between steps.
_wait = e.wait


def wait_and_drain(seconds):
    _wait(seconds)
    drain()


e.wait = wait_and_drain


kind, idx = spec.split(':')
try:
    if kind == 'npc':
        t.talk_to(int(idx))
    else:
        t.goto_zone(int(idx), kind=kind, timeout=30)
except Exception as ex:
    print('%s: %s %s' % (spec, type(ex).__name__, str(ex)[:50]))
for _ in range(4):
    try:
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
    except Exception as ex:
        print('settle:', type(ex).__name__, str(ex)[:40])
    drain()
    if e.state() == 'dos':
        break
drain()
json.dump(seq, open(out, 'w'))
print('%s: %d reads, ended in %s -> %s' % (state, len(seq), e.state(), out))
