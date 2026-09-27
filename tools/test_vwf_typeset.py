"""Check pixel-width typesetting against the VWF: does any typeset line overflow?

For workbook cells that print in a box frame (tools/dialogue_modes.py says 'g'), this
typesets the English exactly as `reinsert.py --gfx-dialogue` does (control codes, then
typeset(vwf=True)), shows it in the game's dialogue box with the VWF and the 99CMN switch
applied, and counts MB3N's own line breaks - it calls 0x938 when a glyph starts with no
column left (0xa0b half-width, 0xa5c full-width). A correctly set line never gets there.

    python tools/test_vwf_typeset.py [--limit N] [--shard i/n]
"""
import argparse
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PROJECT)
from bench import RenderBench, FF, CALL_OPEN, CALL_END, SEG   # noqa: E402
from kuro_core import SCANCODES                              # noqa: E402
from romtools.np2core import HOOK_LOG                        # noqa: E402
import mb3_gfx                                               # noqa: E402
import dialogue_gfx                                          # noqa: E402
import dialogue_modes                                        # noqa: E402

MB = 0x12d70
AUTO_BREAKS = (0xa0b, 0xa5c)


def reinsert_typesetting():
    """reinsert.py's typesetting functions, without running its workbook-loading top level."""
    src = open(os.path.join(PROJECT, 'reinsert.py'), encoding='utf-8').read()
    mod = types.ModuleType('reinsert_typeset')
    from rominfo import NAMES
    mod.__dict__.update(sys=sys, NAMES=NAMES)
    exec(src[src.index('LINE_MAX = 48'):src.index('_ORIGINAL_SCRIPTS = {}')], mod.__dict__)
    return mod


def cells():
    import openpyxl
    from rominfo import DUMP_XLS_PATH, CONTROL_CODES
    ws = openpyxl.load_workbook(os.path.join(PROJECT, DUMP_XLS_PATH), read_only=True)['SCNs']
    for row in ws.iter_rows(min_row=2, values_only=True):
        fn, off, _jp, _jl, en = row[:5]
        if not (fn and en and isinstance(en, str)) or en.startswith('='):
            continue
        loc = int(off, 16)
        if dialogue_modes.mode_of(fn, loc) != 'g':
            continue
        b = en.encode('cp932', errors='replace')
        for cc, rep in CONTROL_CODES.items():
            b = b.replace(cc, rep)
        yield fn, loc, b


def show(b, text):
    e, m = b.e, b.e.m
    b.reset()
    at = b.free_at(len(text) + 16)
    e.write(SEG + at, CALL_OPEN + b'\x40\x02' + text + b'\x00' + CALL_END)
    e.write(b.table() + 2 * 3, at.to_bytes(2, 'little'))
    b.arm(3)
    st = {'prints': 0, 'breaks': 0}

    def cb(ev):
        if ev.addr - MB == 0x82c:
            st['prints'] += 1
        else:
            st['breaks'] += 1
        return False
    m.set_callback(cb)
    for a in (0x82c,) + AUTO_BREAKS:
        m.hook(MB + a, HOOK_LOG)
    for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
        m.key(SCANCODES[k], True)
        for _ in range(40):
            m.run(1)
            if st['prints']:
                break
        m.key(SCANCODES[k], False); m.run(2)
        if st['prints']:
            break
        m.run(20)
    for _ in range(12):                       # page through
        m.run(60)
        e.tap('SPACE', 0.1)
        if e.state() == 'field':
            break
    m.clear_hooks(); m.set_callback(None)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int)
    ap.add_argument('--shard')
    args = ap.parse_args()
    ts = reinsert_typesetting()
    todo = list(cells())
    if args.shard:
        i, n = map(int, args.shard.split('/'))
        todo = todo[i::n]
    if args.limit:
        todo = todo[:args.limit]
    b = RenderBench('r03_manor_inside')
    mb3_gfx.apply_to_ram(b.e.m)
    dialogue_gfx.apply_to_ram(b.e.m)
    b.base = b.e.m.save_state()
    bad = 0
    for fn, loc, en in todo:
        text, _rows = ts.typeset(en, 0, vwf=True)
        try:
            st = show(b, text + FF)
        except AssertionError as x:
            print('%s %#x: skipped (%s)' % (fn, loc, x))
            continue
        if not st['prints']:
            print('%s %#x: never printed' % (fn, loc))
            continue
        if st['breaks']:
            bad += 1
            print('%s %#x: %d automatic line break(s): %r' % (fn, loc, st['breaks'], text[:80]))
    print('%d cells, %d with automatic line breaks' % (len(todo), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
