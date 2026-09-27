"""INT 21h calls and the CPU position after walking into a zone that hangs the game.

    python tools/trace_hang_dos.py STATE kind index        (KURO_HDD = the original disk)
"""
import sys, glob, collections
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_test import Tester
from kuro_emu import Blocked
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0]); t = Tester(e, log=lambda *a: None, god=True)
st, kind, idx = sys.argv[1], sys.argv[2], int(sys.argv[3])
e.load_state(st); e.wait(0.3); e.set_noclip(True)
e.m.int_hook(0x21); e.m.events()
try:
    t.goto_zone(idx, kind=kind, timeout=15)
except Blocked as ex:
    print('goto:', str(ex)[:60])
e.wait(1.0)
evs = e.m.events(); e.m.int_hook(0x21, 0)
def fname(ev):
    r = ev.regs
    if (r.ax >> 8) in (0x3d, 0x4e, 0x3c):
        lin = (r.ds << 4) + r.dx
        b = bytes(e.read(lin, 40)); return b.split(b'\0')[0].decode('ascii', 'replace')
    return ''
calls = [((ev.regs.ax >> 8), fname(ev)) for ev in evs]
c = collections.Counter(calls)
print(len(evs), 'INT 21h calls; last 25:', calls[-25:])
print('opens:', [x for x in calls if x[1]][-12:])
r = e.m.regs(); print('cpu at %04x:%04x' % (r.cs, r.ip), 'ax=%04x' % r.ax)
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
md = Cs(CS_ARCH_X86, CS_MODE_16); lin = (r.cs << 4) + r.ip
for ins in md.disasm(bytes(e.read(lin - 8, 40)), lin - 8):
    print('   %05x %s %s' % (ins.address, ins.mnemonic, ins.op_str))
