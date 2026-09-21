"""How exactly does the game reach DOS - a wild jump, or its own exit call?

"Crashes to DOS" can mean two very different things: the CPU ran off into garbage and
DOS regained control, or the game called INT 21h/4C itself because something in its own
code decided to quit. The second case has a caller worth reading.

Hooks INT 21h, runs the failing action, and prints the last calls with registers and
the top of the stack (the return address is in there).

    python tools/how_it_exits.py STATE npc:1
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from romtools.np2core import EV_INT               # noqa: E402
from kuro_core import CoreEmu                     # noqa: E402
from kuro_test import Tester                      # noqa: E402

state, spec = sys.argv[1], sys.argv[2]
e = CoreEmu()
t = Tester(emu=e, log=lambda *a: None)
e.load_state(state)
e.set_noclip(True)
e.heal()
e.m.int_hook(0x21)
e.m.events()
log = []


def drain():
    for ev in e.m.events():
        if ev.kind != EV_INT:
            continue
        msg = None
        if ev.regs.ax >> 8 in (0x3d, 0x4b):   # open / exec: the name is at ds:dx
            at = (ev.regs.ds << 4) + ev.regs.dx
            raw = bytes(e.read(at, 64))
            msg = 'FILE ' + raw.split(bytes(1))[0].decode('cp932', 'replace')
        elif ev.regs.ax >> 8 == 0x09:      # print a $-terminated string at ds:dx
            at = (ev.regs.ds << 4) + ev.regs.dx
            raw = bytes(e.read(at, 120))
            msg = raw.split(b'$')[0].decode('cp932', 'replace')
        deep = None
        if ev.regs.ax >> 8 == 0x4c:
            # Read the stack properly: the 8 words the event carries are not enough to
            # find who decided to quit.
            at = (ev.regs.ss << 4) + ev.regs.sp
            deep = [int.from_bytes(bytes(e.read(at + 2 * i, 2)), 'little') for i in range(40)]
        log.append((ev.regs.ax, ev.pc, ev.regs.cs, ev.regs.ip, deep or list(ev.stack[:4]), msg))


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
print('ended in', e.state(), '-', len(log), 'DOS calls seen')
exits = [x for x in log if x[0] >> 8 == 0x4c]
print('%d program-exit calls (ah=4c)' % len(exits))
for ax, pc, cs, ip, stack, msg in exits:
    print('  EXIT code %02x from %04x:%04x (linear %05x)' % (ax & 0xff, cs, ip, pc))
    print('  stack words, with any that look like a return into the game flagged:')
    for i in range(0, len(stack) - 1):
        seg, off = stack[i + 1], stack[i]
        lin = (seg << 4) + off
        if 0x16d80 <= lin < 0x2c000:
            print('     sp+%02x: %04x:%04x -> linear %05x  <<< into the game'
                  % (2 * i, seg, off, lin))
opens = [x for x in log if x[0] >> 8 == 0x3d]
print('%d file opens during this action:' % len(opens))
for ax, pc, cs, ip, stack, msg in opens:
    print('   %s   (from %04x:%04x)' % (msg, cs, ip))
game = [x for x in log if x[2] < 0x9000]
print('last 12 DOS calls made by the game itself (cs < 9000):')
for ax, pc, cs, ip, stack, msg in game[-12:]:
    note = ''
    if ax >> 8 == 0x4c:
        note = '   <<< program exit'
    elif ax >> 8 == 0x3d:
        note = '   (open file)'
    elif ax >> 8 == 0x3f:
        note = '   (read)'
    print('  ah=%02x al=%02x  from %04x:%04x (linear %05x)%s'
          % (ax >> 8, ax & 0xff, cs, ip, pc, note))
    if msg:
        print('      message: %r' % msg)
