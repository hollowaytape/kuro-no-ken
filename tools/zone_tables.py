"""The live zone-handler tables of a saved state: which script address each bump/step
script index runs (BD [0x932]/[0x934], read from the state), with the zones using it.

    set KURO_HDD=original\...hdi & python tools/zone_tables.py STATE [STATE...]
"""
import sys, glob
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_emu import BD_SEG
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0])
BD = BD_SEG << 4
for st in sys.argv[1:]:
    e.load_state(st); e.wait(0.3)
    seg = e.word(BD + 0x9fe); bump_t = e.word(BD + 0x932); step_t = e.word(BD + 0x934)
    print('== %s  script seg %04x  bump table %04x  step table %04x  last zone idx %d' % (st, seg, bump_t, step_t, e.word(BD + 0x6fc)))
    zones = e.zones()
    for kind, tbl in (('bump', bump_t), ('step', step_t)):
        idxs = sorted({z['script'] for z in zones if z['kind'] == kind})
        for k in range(max(idxs) + 1 if idxs else 0):
            addr = e.word((seg << 4) + tbl + 2 * k)
            zs = [z['index'] for z in zones if z['kind'] == kind and z['script'] == k]
            print('   %s script %2d -> handler %04x   zones %s' % (kind, k, addr, zs))
