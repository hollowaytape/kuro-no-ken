"""Run every block of the scripts a map has loaded, and check the text each one shows.

Walking the game only reaches the text the player can get to, which on a first pass is a
small fraction of a script. But a trigger zone names its block through a word table
(`[16d8:0932]`), and that table is writable: point a slot at *any* address in the loaded
script, step into the zone, and the engine runs that block - real window, real wrapping,
real control codes.

So for a given save state this runs every block of whatever scripts are loaded, captures
the pages, and checks them the same way a playtest would. It is the efficient half of
script verification: `verify_text.py` proves a line *renders*, this proves a block *plays*
- in context, with its speaker names, page breaks and conditionals.

    python tools/verify_blocks.py STATE [--file 03YSK01B.SCN] [--limit N]
                            [--out test_reports/blocks_<state>.txt]

Blocks that change the map, start a battle or end the game are rolled back and noted;
the state is restored before each one, so they cannot affect each other.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

SEG = 0x26d80
BD = 0x16d80


def loaded_scripts(emu):
    """(filename, slot base) for each script slot, matched against the patched files."""
    import glob
    from check_pointers import as_script
    heads = {}
    for path in glob.glob(os.path.join(HERE, 'patched', '*.SCN')):
        data = as_script(open(path, 'rb').read())
        if data:
            heads.setdefault(bytes(data[:32]), os.path.basename(path))
    out = []
    for base in (0x0000, 0x1800, 0x3d00):
        name = heads.get(bytes(emu.read(SEG + base, 32)))
        if name:
            out.append((name, base))
    return out


def blocks_of(fn, base):
    """The blocks worth running: decoder-proven block entries that actually print.

    A pointer target is not always a block that shows text - plenty are jumps into the
    middle of a routine, or setup with no dialogue - and running those just costs a
    timeout each. Decoding forward from the entry until the block ends says which ones
    contain a print (opcode 0x40).
    """
    import script_decode as sd
    from deep_pointer_audit import offset_map
    from check_pointers import as_script
    orig = open(os.path.join(HERE, 'original', 'decompressed', fn), 'rb').read()
    patched = as_script(open(os.path.join(HERE, 'patched', fn), 'rb').read())
    r = sd.analyse(fn)
    if not r:
        return [], patched
    amap = offset_map(orig, patched)
    layouts = sd.opcode_layouts()
    printing = []
    for target in sorted({t for _loc, t in r['pointers']}):
        insns, _ = sd.decode(orig, base, layouts, [target])
        reachable = [op for at, op, _v in insns if at >= target]
        if 0x40 in reachable:
            printing.append(amap.get(target, target))
    return printing, patched


def all_scripts():
    """Every script that has a patched copy, translated or not."""
    import glob
    return sorted(os.path.basename(x) for x in glob.glob(os.path.join(HERE, 'patched', '*.SCN')))


def translated_scripts():
    """Scripts whose patched bytes differ from the original: the ones worth checking."""
    import glob
    from check_pointers import as_script
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN'))):
        fn = os.path.basename(path)
        pp = os.path.join(HERE, 'patched', fn)
        if not os.path.exists(pp):
            continue
        patched = as_script(open(pp, 'rb').read())
        if patched and patched != open(path, 'rb').read():
            out.append(fn)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state')
    ap.add_argument('--file', help='only blocks of this script')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--all-scripts', action='store_true',
                    help='with --inject: every script, not only the translated ones '
                         '(maps where each dump row is printed, across the game)')
    ap.add_argument('--inject', nargs='*',
                    help='verify these scripts by loading them into a slot, instead of '
                         'only the ones this state already has (no argument = all '
                         'translated scripts)')
    ap.add_argument('--out')
    args = ap.parse_args()

    from bench import RenderBench
    from kuro_test import Script, check_page
    b = RenderBench(args.state)
    e = b.e
    script = Script()
    scripts = loaded_scripts(e)
    print('%s: on %s with %s' % (args.state, e.map_name(),
                                 ', '.join('%s@%#06x' % s for s in scripts) or 'no known script'))
    todo = []
    if args.inject is not None:
        names = args.inject or (all_scripts() if args.all_scripts else translated_scripts())
        print('injecting %d script(s) into slot 1' % len(names))
        for fn in names:
            try:
                b.load_script(fn)
            except AssertionError as ex:
                print('   skipping %s: %s' % (fn, ex))
                continue
            starts, _data = blocks_of(fn, 0x1800)
            todo += [(fn, 0x1800, s) for s in starts]
    else:
        for fn, base in scripts:
            if args.file and fn != args.file:
                continue
            starts, _data = blocks_of(fn, base)
            todo += [(fn, base, s) for s in starts]
    if args.limit:
        todo = todo[:args.limit]
    print('%d block(s) to run' % len(todo))

    out_path = args.out or os.path.join('test_reports', 'blocks_%s.txt' % args.state)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    # A file that was never reinserted shows Japanese by definition, so reporting it as
    # "has English but shows Japanese" buries the cases where a *translated* file does it.
    from rominfo import FILES_TO_REINSERT
    reinserted = set(FILES_TO_REINSERT)
    t0 = time.time()
    issues, seen_rows, results = {}, {}, []
    current = None
    for n, (fn, base, off) in enumerate(todo, 1):
        if args.inject is not None and fn != current:
            # Re-inject when moving to the next script, and fold it into the rollback
            # point so every block starts from the same place.
            b.reset()
            b.load_script(fn)
            b.base = e.m.save_state()
            current = fn
        pages = b.run_block(base + off)
        note = e.state()
        rows = []
        import re as _re
        flat = _re.sub(r'\s+', ' ', ' '.join(l for pg in (pages or []) for l in pg)).lower()
        for lines in pages or []:
            page = {'lines': lines, 'cols': [(0, len(l)) for l in lines], 'icon_col': None}
            source, problems = check_page(page, script, prefer=(fn, hex(off)))
            if source:
                rows.append('%s %s' % source)
                seen_rows.setdefault(source[0], set()).add(source[1])
            for kind, detail in problems:
                # These carry "FILE 0xOFF: <line>" - the dump row this page came from.
                # Counting them too is what makes the coverage figure mean "rows located
                # in context", rather than "rows whose English we could match".
                if kind in ('untranslated', 'not-inserted') and detail[:1] != '(':
                    bits = detail.split()
                    if len(bits) > 1 and bits[0].endswith('.SCN'):
                        seen_rows.setdefault(bits[0], set()).add(bits[1].rstrip(':'))
                if kind == 'not-inserted' and detail.split()[0] not in reinserted:
                    kind = 'awaiting-reinsert'
                if kind == 'truncated':
                    # check_page sees one page at a time, so a cell that typeset split
                    # across two pages looks cut off. It is only a real loss if the rest
                    # never appears in this block at all.
                    tail = detail.split('"')[1] if '"' in detail else ''
                    if tail and _re.sub(r'\s+', ' ', tail).lower() in flat:
                        continue
                issues.setdefault((kind, detail), '%s %#06x' % (fn, off))
        results.append((fn, off, len(pages or []), note, rows))
        if n % 25 == 0:
            print('  %d/%d  %.0fs' % (n, len(todo), time.time() - t0), flush=True)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('%s: %d blocks run, %d with text, %d distinct issues\n\n'
                % (args.state, len(results), sum(1 for r in results if r[2]), len(issues)))
        by_kind = {}
        for (kind, detail), where in issues.items():
            by_kind.setdefault(kind, []).append((detail, where))
        for kind in sorted(by_kind):
            f.write('== %s (%d)\n' % (kind, len(by_kind[kind])))
            for detail, where in by_kind[kind]:
                f.write('  [%s] %s\n' % (where, detail))
            f.write('\n')
        f.write('--- blocks ---\n')
        for fn, off, npages, note, rows in results:
            f.write('%-14s %#06x  %d page(s)  %-9s %s\n'
                    % (fn, off, npages, note, ', '.join(rows[:6])))
    covered = sum(len(v) for v in seen_rows.values())
    print('%d blocks, %d dump rows identified, %d distinct issues, %.0fs -> %s'
          % (len(results), covered, len(issues), time.time() - t0, out_path))


if __name__ == '__main__':
    main()
