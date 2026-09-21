"""Check a script's pointer sheet against what the interpreter actually reads.

    python tools/ptr_audit.py STATE FILE.SCN SLOT [--disk variant.hdi] [--cross]

Sets an np2core read watchpoint on the script slot, plays every NPC and trigger
zone from STATE (rolling back between each), and records which offsets are read
as 16-bit operands and by which instruction. The instructions that read the
script's entry table (definitely addresses) are the pointer fetchers; bulk
routines (the loader, the text printer) read hundreds of offsets and are
excluded. Then:

  confirmed  - a sheet pointer the interpreter reads as an address
  misaligned - a sheet pointer one byte off from one it reads (the old zero-pointer
               pattern reads "09 <lo>" when the operand is "<lo> <hi>")
  unknown    - never reached on these paths

Run it against a disk where the file is NOT translated (scratch_emu/v_wo_*.hdi),
so the script runs to completion instead of crashing.
"""
import sys, os, collections, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from romtools.np2core import WATCH_READ, EV_READ  # noqa: E402
from kuro_core import CoreEmu  # noqa: E402
from kuro_test import Tester  # noqa: E402
import openpyxl  # noqa: E402

state, fn, slot = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
disk = next((a.split('=', 1)[1] for a in sys.argv[4:] if a.startswith('--disk=')), None)
cross = '--cross' in sys.argv

e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
if disk:
    e.reload_disk(os.path.abspath(os.path.join('scratch_emu', disk)))
e.load_state(state)
e.set_noclip(True)
e.heal()
SLOT = 0x26d80 + slot
pairs = collections.Counter()


def drain():
    for ev in e.m.events():
        if ev.kind == EV_READ and ev.size == 2:
            pairs[(ev.pc, ev.addr - SLOT)] += 1


e.m.watch(SLOT, 0x1400, WATCH_READ)
e.m.events()
if cross:                      # walk into the map first, so the load is watched too
    try:
        t.goto_zone(1, kind='step', timeout=25)
    except Exception:
        pass
    t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 120})
    drain()
print('on', e.map_name(), e.state(), flush=True)
base = e.m.save_state()
targets = [('npc', o['slot']) for o in e.objects()] + \
          [(z['kind'], z['index']) for z in e.zones() if z['enabled']]
for kind, idx in targets:
    e.m.load_state(base)
    e._last_lines = None
    e.set_noclip(True)
    e.heal()
    try:
        if kind == 'npc':
            t.talk_to(idx)
        else:
            t.goto_zone(idx, kind=kind, timeout=15)
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 60})
    except Exception:
        pass
    drain()

by_pc = collections.defaultdict(set)
for (pc, off) in pairs:
    by_pc[pc].add(off)
table = set(range(0x4, 0x4f, 3))
fetchers = {pc for pc, offs in by_pc.items() if (offs & table) and len(offs) <= 50}
addrs = set().union(*(by_pc[pc] for pc in fetchers)) if fetchers else set()
print('operand fetchers:', [hex(p) for p in sorted(fetchers)], '| addresses read:', len(addrs))

wp = openpyxl.load_workbook('KuroNoKen_pointer_dump.xlsx', read_only=True)
rows = sorted((int(r[1], 16), int(r[0], 16)) for r in wp[fn].iter_rows(min_row=2, values_only=True) if r[0] and r[1])
conf = [(l, t_) for l, t_ in rows if l in addrs]
mis = [(l, t_) for l, t_ in rows if l not in addrs and (l + 1 in addrs or l - 1 in addrs)]
unk = [(l, t_) for l, t_ in rows if l not in addrs and l + 1 not in addrs and l - 1 not in addrs]
print(f'confirmed {len(conf)}, misaligned {len(mis)}, unknown {len(unk)} of {len(rows)}')
print('misaligned:', [(hex(l), hex(t_)) for l, t_ in mis])
print('addresses read but missing from the sheet:', sorted(hex(a) for a in addrs - {l for l, _ in rows}))
json.dump({'confirmed': [hex(l) for l, _ in conf], 'misaligned': [hex(l) for l, _ in mis],
           'unknown': [hex(l) for l, _ in unk], 'addrs': sorted(hex(a) for a in addrs)},
          open(f'scratch_emu/ptr_audit_{fn}.json', 'w'), indent=1)
