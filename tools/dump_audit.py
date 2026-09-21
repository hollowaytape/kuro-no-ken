"""Check that every dump row's Japanese really is where the workbook says it is.

Only 15 scripts have ever been reinserted, and reinsert is what checks this: it asserts
the Japanese is still at the recorded offset before replacing it. For the other ~190
files nothing has ever verified the offsets, and a wrong one means reinsert will refuse
the file (or, worse, replace the wrong bytes) the day it gets translated.

02OLB03A.SCN 0x0e2 is the case that prompted this: the line is really at 0x62.

    python tools/dump_audit.py                       # report
    python tools/dump_audit.py --fix-offsets out.xlsx  # write a copy with offsets corrected
                                                 # where the string occurs exactly once
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

ORIG = os.path.join(HERE, 'original', 'decompressed')


def find_spaced(data, jp, max_spaces=5):
    """Look for `jp` with some of its ASCII spaces put back as full-width ones.

    Returns (offset, the text that matched once respaced) or (-1, '').
    """
    import itertools
    positions = [i for i, ch in enumerate(jp) if ch == ' ']
    if not positions or len(positions) > max_spaces:
        return -1, b''
    for bits in itertools.product((False, True), repeat=len(positions)):
        if not any(bits):
            continue
        chars = list(jp)
        for pos, wide in zip(positions, bits):
            if wide:
                chars[pos] = '　'
        text = ''.join(chars)
        at = data.find(text.encode('cp932', 'replace'))
        if at >= 0:
            # Return the *text* with its spaces swapped, not bytes decoded back out of
            # the file: a round trip through cp932 turns 0x8160 into U+FF5E, which the
            # shift-jis codec romtools uses cannot encode at all.
            return at, text
    return -1, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fix-offsets', metavar='OUT')
    ap.add_argument('--limit', type=int, default=25)
    args = ap.parse_args()

    import openpyxl
    from rominfo import DUMP_XLS_PATH
    wb = openpyxl.load_workbook(DUMP_XLS_PATH)
    files = {}
    checked = wrong = fixable = missing = 0
    report, ambiguous, order = [], [], {}
    respaced = 0
    for sheet in wb.sheetnames:
        for row in wb[sheet].iter_rows(min_row=2):
            fn = row[0].value
            off = row[1].value
            jp = row[2].value if len(row) > 2 else None
            if not fn or not isinstance(off, str) or not isinstance(jp, str) or not jp.strip():
                continue
            if not str(fn).endswith('.SCN'):
                continue
            path = os.path.join(ORIG, str(fn))
            if str(fn) not in files:
                files[str(fn)] = open(path, 'rb').read() if os.path.exists(path) else None
            data = files[str(fn)]
            if data is None:
                continue
            try:
                at = int(off, 16)
            except ValueError:
                continue
            want = jp.encode('cp932', 'replace')
            checked += 1
            order.setdefault(str(fn), []).append(row)
            if data[at:at + len(want)] == want:
                continue
            wrong += 1
            first = data.find(want)
            if first < 0:
                # The Japanese column has been normalised somewhere along the way -
                # full-width spaces turned into ASCII ones - so it no longer matches the
                # game's bytes and reinsert would refuse the row whatever its offset.
                # Try putting the full-width spaces back.
                first, want = find_spaced(data, jp)
                if first < 0:
                    missing += 1
                    report.append((str(fn), at, None, jp))
                    continue
                respaced += 1
                if args.fix_offsets and len(row) > 2:
                    row[2].value = want
                want = want.encode('cp932', 'replace')
            hits = []
            i = first
            while i >= 0:
                hits.append(i)
                i = data.find(want, i + 1)
            pick = hits[0] if len(hits) == 1 else None
            if pick is None:
                # The line occurs more than once. Rows are stored in offset order, so
                # the right occurrence is the one that still sits between its
                # neighbours - resolved in a second pass once they are known.
                ambiguous.append((str(fn), row, hits))
            else:
                fixable += 1
                if args.fix_offsets:
                    row[1].value = '0x%05x' % pick
            report.append((str(fn), at, pick if pick is not None else hits[0], jp))

    # Second pass: an ambiguous row takes the occurrence that keeps the file's rows in
    # ascending order, which is how the dump stores them.
    resolved = 0
    for fn, row, hits in ambiguous:
        rows_in_file = order.get(fn, [])
        idx = rows_in_file.index(row)
        prev_off = None
        for r in reversed(rows_in_file[:idx]):
            try:
                prev_off = int(str(r[1].value), 16)
                break
            except (ValueError, TypeError):
                continue
        fits = [h for h in hits if prev_off is None or h > prev_off]
        if len(fits) >= 1:
            resolved += 1
            fixable += 1
            if args.fix_offsets:
                row[1].value = '0x%05x' % fits[0]

    print('%d ambiguous row(s) resolved by keeping the file in offset order' % resolved)
    print('%d row(s) whose Japanese needed its full-width spaces restored' % respaced)
    print('%d rows checked, %d at the wrong offset (%d fixable - the string occurs once, '
          '%d not found at all)' % (checked, wrong, fixable, missing))
    for fn, at, first, jp in report[:args.limit]:
        print('   %-14s says %#07x, %s   %r'
              % (fn, at, ('really %#07x' % first) if first is not None else 'NOT FOUND', jp[:28]))
    if args.fix_offsets:
        wb.save(args.fix_offsets)
        print('corrected copy -> %s' % args.fix_offsets)


if __name__ == '__main__':
    main()
