"""Generate pointer sheets for every script, from the interpreter's own opcode table.

Only 14 scripts have a hand-made pointer sheet, because the byte-pattern finder needed
one written and checked per file. `script_decode` does not: it walks a script the way the
engine does and reports the addresses instruction by instruction, so a sheet can be
produced for all 205 files that hold text.

That is what a mapping build needs - every file gets reinserted, so every file needs its
pointers relocated - and it is also the eventual replacement for find_pointers on .SCN
files.

    python tools/gen_pointers.py                      # -> KuroNoKen_pointer_dump_mapping.xlsx
    python tools/gen_pointers.py --out other.xlsx --keep 02OLB01.SCN 03YSK01B.SCN

`--keep` copies those sheets from the curated workbook instead of generating them, for
files where the hand-checked list is known good.
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)
import script_decode as sd                       # noqa: E402


def text_spans():
    """filename -> byte ranges of the dumped Japanese, so a pointer is never placed
    inside text. Editing one there rewrites the string itself, and reinsert then reports
    that the Japanese is no longer where the dump says."""
    import collections
    import openpyxl
    from rominfo import DUMP_XLS_PATH
    spans = collections.defaultdict(list)
    wb = openpyxl.load_workbook(DUMP_XLS_PATH, read_only=True)
    for sheet in wb.sheetnames:
        for r in wb[sheet].iter_rows(min_row=2, values_only=True):
            fn, off, jp = r[0], r[1], r[2]
            if not (fn and isinstance(off, str) and isinstance(jp, str)):
                continue
            try:
                a = int(off, 16)
            except ValueError:
                continue
            spans[fn].append((a, a + len(jp.encode('cp932', 'replace'))))
    return spans


def sheets_for(names):
    """filename -> [(text_location, pointer_location)] from the decoder."""
    out = {}
    spans = text_spans()
    dropped = 0
    for fn in names:
        try:
            r = sd.analyse(fn)
        except Exception as ex:
            print('  %-16s decode failed: %s' % (fn, str(ex)[:50]))
            continue
        if not r or not r['pointers']:
            continue
        if r.get('guessed_base'):
            # No `09 <addr>` entry table, so the slot base is a guess and the block
            # finder has nothing to work from - 01FLD.SCN decodes to three instructions.
            # Its "pointers" are small numbers that go negative the moment reinsert
            # shifts them. Map scripts need their zone tables located first (see
            # docs/engine_notes.md); until then they stay out.
            print('  %-16s skipped: no entry table, decode unreliable' % fn)
            continue
        mine = spans.get(fn, [])
        keep = []
        for loc, t in r['pointers']:
            if any(a <= loc < b or a <= loc + 1 < b for a, b in mine):
                dropped += 1
                continue
            keep.append((t, loc))
        out[fn] = sorted(set(keep))
    if dropped:
        print('  dropped %d pointer(s) that fell inside a dumped string' % dropped)
    return out


_ENTRY_SLOTS = {}


def skipped(fn, loc, target):
    """rominfo.POINTERS_TO_SKIP: each entry was found the hard way (a crash or a soft
    lock in game), so decoded pointers honour it as well as find_pointers' ones - except
    that a target-form entry never removes an entry-table slot, which the engine enters
    through (see fix_pointers.skipped)."""
    import fix_pointers
    if fn not in _ENTRY_SLOTS:
        data = open(os.path.join(HERE, 'original', 'decompressed', fn), 'rb').read()
        _ENTRY_SLOTS[fn] = {1 + 3 * k for k in range(len(sd.slot_base(data)[1]))}
    return fix_pointers.skipped(fn, loc, target, loc in _ENTRY_SLOTS[fn])


def reconcile(fn, curated_rows, decoded_rows):
    """Merge a hand-made sheet with the decoder's pointers.

    The curated rows were checked in game, so none is ever dropped automatically (only
    POINTERS_TO_SKIP removes one). The decoder adds what the sheet lacks - the entry table
    and the stage checks' jumps (opcodes 10-1b) were missing from every curated sheet,
    and with a file fully translated each one would go stale.

    The decoder's instruction boundaries can be wrong, though: right after a string it
    falls through `5c 66 00 09 09 3e` as a jump at 0xb4 in 02OLB02A, while the engine's own
    operand fetch reads 0xb6 (np2core watchpoints). So a decoded pointer one byte from a
    curated one is a *conflict*: nothing is added, it is reported, and it is resolved by
    hand with evidence (see the 0xcb4 entry in rominfo.POINTERS_TO_SKIP).
    """
    kept = [(t, loc) for t, loc in curated_rows if not skipped(fn, loc, t)]
    have = {loc for _t, loc in kept}
    added, conflicts = [], []
    for t, loc in decoded_rows:
        if loc in have or skipped(fn, loc, t):
            continue
        if loc - 1 in have or loc + 1 in have:
            conflicts.append(loc)
            continue
        added.append((t, loc))
    for loc in conflicts:
        print('  %-16s CONFLICT: decoded pointer %#x is one byte from a curated one - '
              'not added; resolve by hand' % (fn, loc))
    return sorted(set(kept + added)), len(curated_rows) - len(kept), len(added)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='KuroNoKen_pointer_dump_mapping.xlsx')
    ap.add_argument('--keep', nargs='*', default=[],
                    help='copy these sheets from the curated workbook instead')
    ap.add_argument('--only', nargs='*')
    args = ap.parse_args()

    import openpyxl
    names = args.only or sorted(os.path.basename(p) for p in
                                glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN')))
    print('decoding %d script(s)' % len(names))
    generated = sheets_for(names)      # kept sheets are reconciled against these too

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    curated = None
    if args.keep:
        from rominfo import CURATED_POINTER_XLS_PATH
        curated = openpyxl.load_workbook(CURATED_POINTER_XLS_PATH, read_only=True)

    total = 0
    for fn in names:
        rows = None
        if fn in args.keep and curated is not None and fn in curated.sheetnames:
            rows = [(r[0], r[1]) for r in curated[fn].iter_rows(min_row=2, values_only=True)
                    if r and r[0] and r[1]]
            rows = [(int(str(a), 16), int(str(b), 16)) for a, b in rows]
            rows, dropped, added = reconcile(fn, rows, generated.get(fn, []))
            if dropped or added:
                print('  %-16s curated sheet: %d skipped, %d decoded added'
                      % (fn, dropped, added))
        elif fn in generated:
            rows = [(t, loc) for t, loc in generated[fn] if not skipped(fn, loc, t)]
        if not rows:
            continue
        ws = wb.create_sheet(fn[:31])
        ws.append(['Text Loc', 'Ptr Loc', 'Bytes', 'Points To', 'Comments'])
        base = sd.slot_base(open(os.path.join(HERE, 'original', 'decompressed', fn), 'rb').read())[0] or 0
        for target, loc in rows:
            ws.append([hex(target), hex(loc), (base + target).to_bytes(2, 'little').hex(' '),
                       'decoded', ''])
        total += len(rows)
    wb.save(args.out)
    print('%d sheet(s), %d pointer(s) -> %s' % (len(wb.sheetnames), total, args.out))


if __name__ == '__main__':
    main()
