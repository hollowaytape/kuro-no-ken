"""Walk onto a zone from a few units away and report what the castle's state machine did
(var 0x34, the castle flags, the stage handlers fetched, the pages read).

    python tools/poke_zone.py STATE kind:index:KEY [...]   KEY = the direction walked
"""
import sys, glob
sys.path.insert(0, 'tools')
from kuro_core import CoreEmu
from kuro_test import Tester
from kuro_emu import BD_SEG, OBJ_ANCHOR
from autoplay import STORY_VARS, current_area, current_region, map_id
import npc_photos as np_
e = CoreEmu(hdd=glob.glob('original/*.hdi')[0])
t = Tester(e, log=lambda *a: None, god=True)
st = sys.argv[1]
FETCH = (BD_SEG << 4) + 0x33bb
FLAGS = (BD_SEG << 4) + 0x8d2
def var(n): return e.word(STORY_VARS + 2 * n)
def flag(i): return (e.read(FLAGS + (i >> 3), 1)[0] >> (i & 7)) & 1
def flags(): return ''.join('%02x=%d ' % (i, flag(i)) for i in (0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xc8, 0xc9))
e.load_state(st); e.wait(0.3)
base = e.m.save_state()
for spec in sys.argv[2:]:
    kind, idx, key = spec.split(':'); idx = int(idx)
    e.m.load_state(base); e._last_lines = None
    z = next(z for z in e.zones() if z['kind'] == kind and z['index'] == idx)
    cx, cy = (z['x1'] + z['x2']) // 2, (z['y1'] + z['y2']) // 2
    sx, sy = {'UP': (cx, z['y2'] + 8), 'DOWN': (cx, z['y1'] - 8), 'LEFT': (z['x2'] + 8, cy), 'RIGHT': (z['x1'] - 8, cy)}[key]
    np_.put_player(e, sx + OBJ_ANCHOR[0], sy + OBJ_ANCHOR[1]); e.wait(0.3)
    print('== %s %s %d script %d rect (%d,%d)-(%d,%d): stand at %s walk %s | var34=%d var4=%d %s' % (
        st, kind, idx, z['script'], z['x1'], z['y1'], z['x2'], z['y2'], (sx, sy), key, var(0x34), var(4), flags()), flush=True)
    e.m.hook(FETCH); e.m.events()
    pages = []
    for _ in range(14):
        e.tap(key, 0.12); e.wait(0.15)
        if e.state() != 'field':
            break
    end = e.clock() + 60
    while e.clock() < end:
        stt = e.state()
        if stt == 'dialogue':
            t.pages = []
            t.read_dialogue()
            pages += t.pages
        elif stt == 'field' and len(e.zones()) < 80:
            e.wait(2.0)
            if e.state() == 'field':
                break
        else:
            e.press('SPACE', gap=0.4)
        e.wait(0.5)
    evs = e.m.events(); e.m.unhook(FETCH)
    fetched = sorted({ev.regs.si for ev in evs if ev.kind == 0 and 0x2d4d <= ev.regs.si < 0x2ec3})
    print('   -> %s pos %s var34=%d %s handlers %s pages %d' % (
        map_id(current_area(e), current_region(e), e.map_sig()) if e.state() == 'field' else e.state(), e.pos(), var(0x34), flags(),
        ['%04x' % f for f in fetched][:10], len(pages)), flush=True)
    for m, src, lines in pages[:6]:
        print('      ', src, ' / '.join(l.strip() for l in lines)[:60])
