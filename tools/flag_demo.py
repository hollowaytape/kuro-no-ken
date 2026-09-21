"""Set a progression flag and show a gated block take the other branch."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
from bench import RenderBench
BD = 0x16d80
FLAGS = 0x08d2
state, block, flag = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
b = RenderBench(state)
e = b.e

def show(label):
    pages = b.run_block(block)
    text = ' / '.join(l[:40] for p in (pages or []) for l in p[:2])
    print('%-18s %d page(s): %s' % (label, len(pages or []), text[:100]))

def set_flag(on):
    byte = BD + FLAGS + (flag >> 3)
    v = e.read(byte, 1)[0]
    v = (v | (1 << (flag & 7))) if on else (v & ~(1 << (flag & 7)))
    e.write(byte, bytes([v]))

base = e.m.save_state()
show('flag %#x as-is:' % flag)
e.m.load_state(base)
set_flag(True)
b.base = e.m.save_state()
show('flag %#x set:' % flag)
e.m.load_state(base)
set_flag(False)
b.base = e.m.save_state()
show('flag %#x cleared:' % flag)
