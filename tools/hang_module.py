"""The D.FA1 reads a zone triggers and the module pointer the loader then calls (0c17:0368).

    python tools/hang_module.py STATE kind index
"""
import sys, glob
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_test import Tester
from kuro_emu import Blocked
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0]); t = Tester(e, log=lambda *a: None, god=True)
e.load_state(sys.argv[1]); e.wait(0.3); e.set_noclip(True)
e.m.int_hook(0x21); e.m.events()
try: t.goto_zone(int(sys.argv[3]), kind=sys.argv[2], timeout=15)
except Blocked as ex: print('goto:', str(ex)[:60])
e.wait(0.5); evs = e.m.events(); e.m.int_hook(0x21, 0)
for ev in evs:
    r = ev.regs; ah = r.ax >> 8
    if ah in (0x3d, 0x42, 0x3f, 0x3e):
        extra = ''
        if ah == 0x42: extra = 'seek to %d (whence %d)' % ((r.cx << 16) | r.dx, r.ax & 0xff)
        if ah == 0x3f: extra = 'read %d bytes to %04x:%04x' % (r.cx, r.ds, r.dx)
        if ah == 0x3d: extra = bytes(e.read((r.ds << 4) + r.dx, 20)).split(b'\0')[0].decode('ascii','replace')
        print('  int21 ah=%02x %s' % (ah, extra))
ptr_lin = 0x0c170 + 0x368
off, seg = e.word(ptr_lin), e.word(ptr_lin + 2)
print('far pointer at 0c17:0368 = %04x:%04x (linear %05x)' % (seg, off, (seg << 4) + off))
mod = bytes(e.read((seg << 4) + off, 32)); print('module head:', mod.hex(' '))
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
md = Cs(CS_ARCH_X86, CS_MODE_16)
for ins in list(md.disasm(bytes(e.read((seg << 4) + off, 48)), (seg << 4) + off))[:10]:
    print('   %05x  %-6s %s' % (ins.address, ins.mnemonic, ins.op_str))
