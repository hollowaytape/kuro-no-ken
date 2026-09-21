"""Addresses in one script that point into another script - and moved.

Scripts share the segment: slot 0 at 0x0000, slot 1 at 0x1800, slot 2 at 0x3d00. A map
script can therefore hold addresses into the file loaded beside it, and when *that*
file's text shifts, these stay behind. deep_pointer_audit.py cannot see this: the file
holding the pointer is unchanged, so aligning it with itself finds nothing.

03YSK.SCN is such a holder - it is fixed-length, so reinsert never relocates anything in
it, yet it names blocks inside 03YSK01B.SCN, which did shift.

    python tools/cross_pointer_audit.py HOLDER.SCN TARGET.SCN STATE TARGET_SPEC

Candidates are confirmed the same way as before: run the action, watch the holder's slot,
and keep only the words the interpreter fetched as an address operand.
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
from check_pointers import as_script                 # noqa: E402
from deep_pointer_audit import offset_map            # noqa: E402

FETCHERS = (0x18a6e, 0x18b33, 0x18aa9)
SEG = 0x26d80
SLOTS = {0: 0x0000, 1: 0x1800, 2: 0x3d00}

holder, target_fn, state, spec = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
holder_slot = int(next((a.split('=', 1)[1] for a in sys.argv[5:]
                        if a.startswith('--holder-slot=')), '0'))
target_base = int(next((a.split('=', 1)[1] for a in sys.argv[5:]
                        if a.startswith('--target-base=')), '0x1800'), 16)

ORIG = os.path.join(HERE, '..', 'original', 'decompressed')
PATCHED = os.path.join(HERE, '..', 'patched')
h = open(os.path.join(ORIG, holder), 'rb').read()
to = open(os.path.join(ORIG, target_fn), 'rb').read()
tp = as_script(open(os.path.join(PATCHED, target_fn), 'rb').read())
amap = offset_map(to, tp)

cands = {}
for i in range(len(h) - 1):
    w = int.from_bytes(h[i:i + 2], 'little')
    off = w - target_base
    if 0x20 <= off < len(to) and off in amap and amap[off] != off:
        cands[i] = (off, amap[off], h[max(0, i - 4):i].hex(' '))
print('%s -> %s: %d words that point into the other file and moved'
      % (holder, target_fn, len(cands)))

e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
e.load_state(state)
e.set_noclip(True)
e.heal()
slot_addr = SEG + SLOTS[holder_slot]
e.m.watch(slot_addr, 0x1800, WATCH_READ)
e.m.events()
read_at = set()


def drain():
    for ev in e.m.events():
        # Not only the three known operand fetchers: the interpreter reads addresses
        # from several routines, and filtering on those three hid the cross-file ones.
        if ev.kind == EV_READ and ev.size == 2:
            read_at.add(ev.addr - slot_addr)


kind, idx = spec.split(':')
try:
    if kind == 'npc':
        t.talk_to(int(idx))
    else:
        t.goto_zone(int(idx), kind=kind, timeout=30)
except Exception as ex:
    print('%s: %s %s' % (spec, type(ex).__name__, str(ex)[:50]))
for _ in range(3):
    try:
        t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
    except Exception as ex:
        print('settle:', type(ex).__name__, str(ex)[:40])
    drain()
    if e.state() == 'dos':
        break
drain()
print('ended %s on %s; %d address operands fetched from slot %d'
      % (e.state(), e.map_name(), len(read_at), holder_slot))
hp = as_script(open(os.path.join(PATCHED, holder), 'rb').read())
print('operands fetched from this slot, and what they hold:')
for off in sorted(read_at):
    wo = int.from_bytes(h[off:off + 2], 'little') if off + 2 <= len(h) else None
    wp = int.from_bytes(hp[off:off + 2], 'little') if hp and off + 2 <= len(hp) else None
    print('   %#06x: original %s patched %s' % (off, hex(wo) if wo else '-', hex(wp) if wp else '-'))
hits = sorted(i for i in cands if i in read_at)
print('%d confirmed:' % len(hits))
for i in hits:
    old, new, before = cands[i]
    print("    ('%s', %#0x, %#0x),   # -> %s, was %#06x, preceded by %s"
          % (holder, i, new, target_fn, old, before))
