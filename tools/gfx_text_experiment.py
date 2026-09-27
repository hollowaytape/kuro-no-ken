"""Graphics-mode dialogue in MB3N, with the missing addressing fix simulated by exec hooks.

usage: python tools/gfx_text_experiment.py text|gfx [fill_colour] [text_colour] [shadow_colour|-] [bold]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import RenderBench, FF, NL, CALL_OPEN, CALL_END, SEG
from kuro_core import SCANCODES
from romtools.np2core import HOOK_LOG
from PIL import Image
SP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scratch_emu')
MB = 0x12d70          # MB3N resident at 12d7
RING = 32000          # graphics VRAM is used as a 400-line ring
tag = sys.argv[1]
gfx = tag != 'text'
fill = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x09
fg = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
shadow = int(sys.argv[4], 16) if len(sys.argv) > 4 and sys.argv[4] != '-' else None
bold = int(sys.argv[5], 16) if len(sys.argv) > 5 else None
PAGE = FF + bytes([0x00, 0x3b, 0x40, 0x02])     # end string, wait for key, print next

b = RenderBench('r03_manor_inside'); e = b.e; m = e.m
text = (b'Karin' + NL + b'\\i2The quick brown fox jumps over the lazy dog,' + NL +
        b'then wanders off to find something better to do.' + NL +
        b'Digits and marks: 0123456789 !?,.\'"()-:;' + NL +
        b'Line four, the last one that fits in the box.' + PAGE +
        b'Second page after a page break. This line is long enough that the engine has to wrap it.' + FF)
b.reset()
at = b.free_at(len(text) + 16)
e.write(SEG + at, CALL_OPEN + b'\x40\x02' + text + b'\x00' + CALL_END)
e.write(b.table() + 2 * 3, at.to_bytes(2, 'little'))
b.arm(3)

w16 = lambda a: int.from_bytes(m.read(a, 2), 'little')
st = {'set': None, 'wraps': 0, 'printed': False}
log = []


def scroll():
    """(ring base byte, byte where display area 0 ends) from MB3N's GDC scroll shadow."""
    q = m.read(MB + 0x68, 4)
    base = (q[0] | q[1] << 8 | (q[2] & 3) << 16) * 2
    return base, base + 80 * ((q[2] >> 4) | (q[3] & 0x3f) << 4)


def wrap(reg):
    r = m.regs(); v = getattr(r, reg)
    if v >= scroll()[1]:
        setattr(r, reg, v - RING); m.set_regs(r); st['wraps'] += 1


def cb(ev):
    a = ev.addr - MB
    if a == 0x82c:
        st['printed'] = True
    if gfx and a in (0x82c, 0xa99):             # the box-open string resets these; override
        m.write(MB + 0x824, bytes([fill]))
        if fg is not None:
            m.write(MB + 0x825, bytes([fg]))
        if shadow is not None:
            m.write(MB + 0x827, bytes([shadow]))
        if bold is not None:
            m.write(MB + 0x82b, bytes([bold]))
    if a == 0x82c and gfx:                      # text-cell window -> pixel row, base-relative
        col, row = w16(MB + 0x80e), w16(MB + 0x810)
        if (col, row) != st['set']:
            base, _ = scroll()
            lin = base + row * 16 * 80
            nr, nc = lin // 80, col + lin % 80
            m.write(MB + 0x80e, nc.to_bytes(2, 'little')); m.write(MB + 0x810, nr.to_bytes(2, 'little'))
            st['set'] = (nc, nr)
            log.append('window (%d,%d) cells -> byte col %d, ring row %d (base %#x)' % (col, row, nc, nr, base))
    elif a in (0x9c8, 0xc79, 0xbc8):            # line start / next scanline (half, full width)
        wrap('di')
    elif a == 0xacd:                            # clear: next row
        wrap('si')
    return False


m.set_callback(cb)
for off in (0x82c, 0x9c8, 0xc79, 0xbc8, 0xacd, 0xa99):
    m.hook(MB + off, HOOK_LOG)
if gfx:
    e.write(MB + 0x828, b'\x00')
for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
    m.key(SCANCODES[k], True)
    for _ in range(40):
        m.run(1)
        if st['printed']:
            break
    m.key(SCANCODES[k], False); m.run(2)
    if st['printed']:
        break
    m.run(20)
shots = []
for i in range(3):
    m.run(300); shots.append(e.image()); e.tap('SPACE', 0.1)
print('\n'.join(dict.fromkeys(log)))
print('wraps', st['wraps'], 'state', e.state(), 'bold [82b]=%d' % m.read(MB + 0x82b, 1)[0])
s = Image.new('RGB', (640, 130 * len(shots)))
for i, im in enumerate(shots):
    s.paste(im.crop((0, 245, 640, 375)), (0, 130 * i))
s.save(os.path.join(SP, tag + '.png'))
