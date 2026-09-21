"""Disassemble live RAM around an address (for code that isn't BD.BIN)."""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import capstone                       # noqa: E402
from bench import Bench               # noqa: E402

state = sys.argv[1]
addr = int(sys.argv[2], 16)
back = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x40
span = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0xc0
b = Bench(state)
data = b.e.read(addr - back, span)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
for i in md.disasm(data, addr - back):
    mark = ' <<<' if i.address == addr else ''
    print('%05x %-8s %s%s' % (i.address, i.mnemonic, i.op_str, mark))
