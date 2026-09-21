"""Which of the audit's stale candidates does the interpreter actually follow?

deep_pointer_audit.py lists every address that stayed behind when its target moved,
but most are data that happens to look like an address. This runs the route that is
broken, records the offsets the interpreter fetches as address operands (BD's operand
fetchers), maps them back to original-file offsets, and keeps only the candidates that
appear in both. Those are pointers, confirmed by the game itself.

    python tools/confirm_pointers.py 03YSK01B.SCN STATE [--then=step:1]
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from romtools.np2core import WATCH_READ, EV_READ         # noqa: E402
from kuro_core import CoreEmu                            # noqa: E402
from kuro_test import Tester                             # noqa: E402
from check_pointers import as_script                     # noqa: E402
from deep_pointer_audit import audit, offset_map         # noqa: E402

FETCHERS = (0x18a6e, 0x18b33, 0x18aa9)

fn, state = sys.argv[1], sys.argv[2]
then = next((a.split('=', 1)[1] for a in sys.argv[3:] if a.startswith('--then=')), None)
# --target=npc:1 runs a single target from the state instead of the two-hop route.
target = next((a.split('=', 1)[1] for a in sys.argv[3:] if a.startswith('--target=')), None)
SLOT_OFF = int(next((a.split('=', 1)[1] for a in sys.argv[3:]
                     if a.startswith('--slot=')), '0x1800'), 16)
SLOT = 0x26d80 + SLOT_OFF

stale = audit(fn)
print('%s: %d stale candidates from the static audit' % (fn, len(stale)))

e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
e.load_state(state)
e.set_noclip(True)
e.heal()
e.m.watch(SLOT, 0x1400, WATCH_READ)
e.m.events()
read_at = set()


def drain():
    for ev in e.m.events():
        if ev.kind == EV_READ and ev.size == 2 and ev.pc in FETCHERS:
            read_at.add(ev.addr - SLOT)


if target:
    kind, idx = target.split(':')
    try:
        if kind == 'npc':
            t.talk_to(int(idx))
        else:
            t.goto_zone(int(idx), kind=kind, timeout=30)
    except Exception as ex:
        print('%s:' % target, type(ex).__name__, str(ex)[:50])
    for _ in range(3):
        try:
            t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
        except Exception as ex:
            print('settle:', type(ex).__name__, str(ex)[:40])
        drain()
        if e.state() == 'dos':
            break
else:
    try:
        t.goto_zone(3, kind='step', timeout=30)
    except Exception as ex:
        print('goto_zone:', type(ex).__name__, str(ex)[:50])
    t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 60})
    drain()
if then:
    kind, idx = then.split(':')
    try:
        t.goto_zone(int(idx), kind=kind, timeout=30)
    except Exception as ex:
        print('%s:' % then, type(ex).__name__, str(ex)[:50])
    for _ in range(3):
        try:
            t.run_step({'op': 'settle', 'quiet': 2, 'timeout': 30})
        except Exception as ex:
            print('settle:', type(ex).__name__, str(ex)[:40])
        drain()
print('ended on %s (%s); %d address operands fetched from this slot'
      % (e.map_name(), e.state(), len(read_at)))

o = open(os.path.join(HERE, '..', 'original', 'decompressed', fn), 'rb').read()
p = as_script(open(os.path.join(HERE, '..', 'patched', fn), 'rb').read())
amap = offset_map(o, p)
print('operands fetched from this slot, and where they point now:')
rev = {v: k for k, v in amap.items()}
for off in sorted(read_at):
    if off + 2 > len(p):
        continue
    w = int.from_bytes(p[off:off + 2], 'little') - SLOT_OFF
    ok = 'inside the file' if 0 <= w < len(p) else 'OUT OF RANGE'
    src = rev.get(off)
    was = int.from_bytes(o[src:src + 2], 'little') - SLOT_OFF if src is not None and src + 2 <= len(o) else None
    print('   at %#06x (original %s): -> %#06x  %s%s'
          % (off, hex(src) if src is not None else '?', w, ok,
             '   [was %#06x]' % was if was is not None else ''))
confirmed = [(i, old, new, before) for i, old, new, before in stale if amap.get(i) in read_at]
print('%d candidate(s) the interpreter actually read as an address:' % len(confirmed))
for i, old, new, before in confirmed:
    print("    ('%s', %#0x, %#0x),   # was %#06x, preceded by %s" % (fn, i, new, old, before))
