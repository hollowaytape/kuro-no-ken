"""Run real script blocks with the dialogue graphics-mode patches, and look for misuse.

tools/test_mb3_gfx.py proves that a dialogue box drawn in graphics mode looks exactly like
text mode. This checks the other half: that *only* dialogue boxes get graphics mode, in
the blocks the game actually runs. With tools/mb3_gfx.py and tools/dialogue_gfx.py applied
in RAM, every printing block of the scripts a save state has loaded (the same set
tools/verify_blocks.py runs) is played through, and two things are flagged:

  leak      MB3N is still in graphics mode once the game is back in the field, so the
            next print (a location title, say) would paint a grey box over the map
  window    a graphics-mode print into a window that is not one of the dialogue boxes
            (13,17 / 21,17 / 13,20, 50x5)

    python tools/sweep_dialogue_gfx.py STATE [--limit N]
    python tools/sweep_dialogue_gfx.py r03_manor_inside --inject [02OLB02A.SCN ...]
    python tools/sweep_dialogue_gfx.py r03_manor_inside --inject --original --shard 0/8
"""
import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import RenderBench, CALL_OPEN, CALL_END, SEG    # noqa: E402
from kuro_core import SCANCODES                             # noqa: E402
from romtools.np2core import HOOK_LOG                       # noqa: E402
import mb3_gfx                                              # noqa: E402
import dialogue_gfx                                         # noqa: E402
import verify_blocks                                        # noqa: E402

MB = 0x12d70
BOX_WINDOWS = {(13, 17, 50, 5), (21, 17, 50, 5), (13, 20, 50, 5)}
PROMPT = (0x56, 0x26)                  # the press-a-key icon on the text layer
CLOSE_STR = b'\\f \\n'                  # 99CMN's close routines print this
CONTROL_STRS = (b'\\o', b'\\c7\\b0')    # ...and the opens these (window, attributes)


def w16(m, a):
    return int.from_bytes(m.read(a, 2), 'little')


ORIGINAL = False          # --original: inject the untranslated scripts instead


def script_slot(fn):
    """(slot base, bytes) of a patched (or, with --original, original) script. Scene
    scripts belong in slot 2 (0x3d00), hub scripts in slot 1 (0x1800); their block
    addresses only work at their own base."""
    import script_decode as sd
    from check_pointers import as_script
    from rominfo import SCN_SLOT_SIZES
    if ORIGINAL:
        data = open(os.path.join(verify_blocks.HERE, 'original', 'decompressed', fn), 'rb').read()
    else:
        data = as_script(open(os.path.join(verify_blocks.HERE, 'patched', fn), 'rb').read())
    base, _ = sd.slot_base(data)
    assert base in (0x1800, 0x3d00), '%s is not a slot 1/2 script' % fn
    if len(data) > SCN_SLOT_SIZES[base] and fn not in _warned:
        _warned.add(fn)
        print('  note: %s is %#x bytes, over rominfo.SCN_SLOT_SIZES[%#x] = %#x' % (
            fn, len(data), base, SCN_SLOT_SIZES[base]))
    return base, data


_warned = set()


def original_blocks(fn, base):
    """Block entries of an original script that reach a print (verify_blocks.blocks_of,
    without the map to a patched copy)."""
    import script_decode as sd
    orig = open(os.path.join(verify_blocks.HERE, 'original', 'decompressed', fn), 'rb').read()
    r = sd.analyse(fn)
    if not r:
        return []
    layouts = sd.opcode_layouts()
    out = []
    for target in sorted({t for _loc, t in r['pointers']}):
        insns, _ = sd.decode(orig, base, layouts, [target])
        if 0x40 in [op for at, op, _v in insns if at >= target]:
            out.append(target)
    return out


def play(b, addr, inject=None, max_frames=60 * 60):
    """Run the block at `addr` in the frame a real caller gives it (after writing the
    patched script `inject` into its slot); -> (prints, how it ended, mode afterwards)."""
    e, m = b.e, b.e.m
    b.reset()
    if inject:
        base, data = script_slot(inject)
        e.write(SEG + base, data)
    at = b.free_at(12)
    e.write(SEG + at, CALL_OPEN + bytes([0x04]) + addr.to_bytes(2, 'little') + CALL_END)
    e.write(b.table() + 2 * 3, at.to_bytes(2, 'little'))
    b.arm(3)
    prints = []

    def cb(ev):
        win = (w16(m, MB + 0x80e), w16(m, MB + 0x810), w16(m, MB + 0x812), w16(m, MB + 0x814))
        r = ev.regs
        head = m.read((r.ds << 4) + r.si, 6)
        prints.append((m.read(MB + 0x828, 1)[0], win, head))
        play.where.append((r.ds, r.si))
        return False
    play.where = []                      # (ds, si) of each print, for --record
    m.set_callback(cb)
    m.hook(MB + 0x82c, HOOK_LOG)
    for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):   # step into the zone; let go on the print
        m.key(SCANCODES[k], True)
        for _ in range(40):
            m.run(1)
            if prints:
                break
        m.key(SCANCODES[k], False); m.run(2)
        if prints:
            break
        m.run(20)
    end = 'no print'
    if prints:
        quiet, frames = 0, 0
        while frames < max_frames:
            m.run(15); frames += 15
            st = e.state()
            if st in ('dos', 'battle'):
                end = st
                break
            tv = m.read(0xa0000, 4000)
            if any(tv[i] == PROMPT[0] and tv[i + 1] == PROMPT[1] for i in range(0, 4000, 2)):
                e.tap('SPACE', 0.1); quiet = 0
                continue
            if st == 'field':
                quiet += 1
                if quiet > 8:
                    end = 'field'
                    break
            else:
                quiet = 0
                if frames % 120 == 0:        # menus / choices: take the default
                    e.tap('SPACE', 0.1)
        else:
            end = 'timeout'
    mode_after = m.read(MB + 0x828, 1)[0]
    m.clear_hooks(); m.set_callback(None)
    return prints, end, mode_after


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--inject', nargs='*',
                    help='write these patched scripts (default: every translated one) into '
                         'their own slot and run their blocks')
    ap.add_argument('--shard', help='i/n: run only every n-th script, starting at i '
                    '(one np2core Machine per process, so run shards in parallel)')
    ap.add_argument('--plain', action='store_true',
                    help='without the patches: a baseline for how blocks end')
    ap.add_argument('--original', action='store_true',
                    help='inject the original scripts (all of slots 1 and 2), not patched/')
    ap.add_argument('--record', help='append one JSON line per print from the injected '
                    'script - file, string offset in it, mode (g/t) - to this file')
    args = ap.parse_args()
    global ORIGINAL
    ORIGINAL = args.original
    b = RenderBench(args.state)
    if not args.plain:
        mb3_gfx.apply_to_ram(b.e.m)
        dialogue_gfx.apply_to_ram(b.e.m)
    b.base = b.e.m.save_state()          # every reset() starts from the patched game
    todo = []
    if args.inject is not None:
        if args.inject:
            names = args.inject
        elif ORIGINAL:
            import glob
            names = sorted(os.path.basename(p) for p in glob.glob(
                os.path.join(verify_blocks.HERE, 'original', 'decompressed', '*.SCN')))
            names = [n for n in names if n != '99CMN.SCN']
        else:
            names = verify_blocks.translated_scripts()
        if args.shard:
            i, n = map(int, args.shard.split('/'))
            names = names[i::n]
        for fn in names:
            try:
                base, _ = script_slot(fn)
            except AssertionError as x:
                continue                       # map scripts (slot 0) and the like
            if ORIGINAL:
                starts = original_blocks(fn, base)
            else:
                starts, _ = verify_blocks.blocks_of(fn, base)
            todo += [(fn, base, s, True) for s in starts]
    else:
        for fn, base in verify_blocks.loaded_scripts(b.e):
            starts, _ = verify_blocks.blocks_of(fn, base)
            todo += [(fn, base, s, False) for s in starts]
    if args.limit:
        todo = todo[:args.limit]
    print('%s: %d blocks' % (args.state, len(todo)))
    problems, ends, gfx_blocks = collections.Counter(), collections.Counter(), 0
    for fn, base, off, inject in todo:
        try:
            prints, end, mode_after = play(b, base + off, fn if inject else None)
        except AssertionError as x:
            print('  %s %#06x: skipped (%s)' % (fn, base + off, x))
            continue
        ends[end] += 1
        if args.record and inject:
            import json
            size = len(script_slot(fn)[1])
            with open(args.record, 'a') as fh:
                for (mode, _w, _h), (ds, si) in zip(prints, play.where):
                    if (ds << 4) == SEG and base <= si < base + size:
                        fh.write(json.dumps({'file': fn, 'offset': si - base,
                                             'mode': 'g' if mode == 0 else 't'}) + '\n')
        gfx = [w for mode, w, _h in prints if mode == 0]
        gfx_blocks += bool(gfx)
        bad = sorted({w for w in gfx if w not in BOX_WINDOWS})
        issues = []
        if bad:
            issues.append('window %s' % bad)
        if end == 'field' and mode_after == 0:
            issues.append('leak')
        # Dialogue shown in text mode while a graphics box is up means something switched
        # graphics off mid-box. 99CMN's own strings - the window and attribute setup of
        # an open, the `\f \n` of a close - are text by design, and a close ends the box.
        in_box, flips = False, []
        for mode, _w, head in prints:
            if head.startswith(CLOSE_STR):
                in_box = False
            elif head.startswith(CONTROL_STRS):
                pass
            elif mode == 0:
                in_box = True
            elif in_box:
                flips.append(head)
        if flips:
            issues.append('flip %s' % flips[:3])
        if end not in ('field', 'no print'):
            print('  %s %#06x: ended %s' % (fn, base + off, end))
        for i in issues:
            problems[i.split()[0]] += 1
        if issues:
            print('  %s %#06x: %s (end %s, %d prints, %d in graphics)' % (
                fn, base + off, '; '.join(issues), end, len(prints), len(gfx)))
    print('%s: %d blocks, %d with graphics-mode dialogue; ends %s; problems %s' % (
        args.state, len(todo), gfx_blocks, dict(ends), dict(problems) or 'none'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
