"""The live zone -> script-block tables, checked against the original file.

A trigger zone's script byte indexes a word table: bump zones through `[16d8:0932]`,
step zones through `[16d8:0934]`, both in the script segment `[16d8:09fe]`. If that
table sits inside a file whose text shifted, every entry in it has to move - and the
tables are not part of the entry table, so nothing registered so far covers them.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
from kuro_core import CoreEmu                  # noqa: E402
from check_pointers import as_script           # noqa: E402
from deep_pointer_audit import offset_map      # noqa: E402

BD = 0x16d80
SEG = 0x26d80
state = sys.argv[1]
fn = sys.argv[2] if len(sys.argv) > 2 else '03YSK01B.SCN'
e = CoreEmu()
e.load_state(state)


def w(phys):
    return int.from_bytes(bytes(e.read(phys, 2)), 'little')


o = open(os.path.join(HERE, '..', 'original', 'decompressed', fn), 'rb').read()
p = as_script(open(os.path.join(HERE, '..', 'patched', fn), 'rb').read())
amap = offset_map(o, p)
base = 0x1800

print('map', e.map_name(), '- script segment %#06x' % w(BD + 0x09fe))
for name, at in (('bump', 0x0932), ('step', 0x0934)):
    off = w(BD + at)
    print('%s table at segment offset %#06x (file offset %#06x if it is in %s)'
          % (name, off, off - base, fn))
    for i in range(12):
        live = w(SEG + off + 2 * i)
        t = live - base
        src = {v: k for k, v in amap.items()}.get(t)
        note = ''
        if 0 <= t < len(p):
            want = amap.get(src) if src is not None else None
            note = 'patched-file offset %#06x' % t
            if src is not None and src != t:
                note += '  (original %#06x)' % src
        print('   %s %2d -> %#06x   %s' % (name, i, live, note))
