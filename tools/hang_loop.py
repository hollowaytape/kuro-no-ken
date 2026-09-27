"""Sample the program counter while the game hangs after a zone, and disassemble the loop.

    python tools/hang_loop.py STATE kind index
"""
import sys, glob, collections
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_test import Tester
from kuro_emu import Blocked
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0]); t = Tester(e, log=lambda *a: None, god=True)
e.load_state(sys.argv[1]); e.wait(0.3); e.set_noclip(True)
try: t.goto_zone(int(sys.argv[3]), kind=sys.argv[2], timeout=15)
except Blocked as ex: print('goto:', str(ex)[:60])
pcs = collections.Counter(); regs = []
for i in range(60):
    e.wait(0.02); r = e.m.regs(); pcs[(r.cs, r.ip)] += 1; regs.append(r)
print('pc samples:', ['%04x:%04x x%d' % (cs, ip, n) for (cs, ip), n in pcs.most_common(8)])
r = regs[-1]; print('regs', r)
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
md = Cs(CS_ARCH_X86, CS_MODE_16)
lo = min((cs << 4) + ip for (cs, ip) in pcs) - 0x30
code = bytes(e.read(lo, 0x90))
for ins in md.disasm(code, lo):
    mark = '<==' if any((cs << 4) + ip == ins.address for (cs, ip) in pcs) else ''
    print('   %05x  %-6s %-24s %s' % (ins.address, ins.mnemonic, ins.op_str, mark))
