"""Map every line of the dump to the script block - and so the trigger - that shows it.

Playing the game only reaches the text the autoplayer can walk to. The scripts know the
rest: each `.SCN` is a list of blocks, the map scripts end with a word table of block
addresses indexed by a trigger zone's script byte (BD.BIN 0x3167 reads it through
`[16d8:0932]`), and each block prints its text with `40 02 <string> 00`.

So for every file this works out, without running anything:

  - the blocks, from the `09 <addr>` entry table at the top and the zone table at the
    end (both hold base+offset addresses, base = the slot: 0, 0x1800 or 0x3d00),
  - the strings each block prints,
  - and which dump rows those strings are, by offset.

    python tools/script_map.py [--out docs/script_map.md]

Written alongside docs/game_map.md, which covers the same ground from the other
direction: what the autoplayer actually reached.
"""
import argparse
import collections
import glob
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
SLOT_BASES = (0x3d00, 0x1800, 0x0000)
PRINT_OP = bytes([0x40, 0x02])


def slot_base(data):
    """Which slot this file is loaded into, from its own entry-table addresses."""
    addrs = []
    i = 0
    while i + 3 <= len(data) and data[i] == 0x09:
        addrs.append(int.from_bytes(data[i + 1:i + 3], 'little'))
        i += 3
    if not addrs:
        return None, []
    for base in SLOT_BASES:
        if all(base <= a < base + len(data) for a in addrs):
            return base, [a - base for a in addrs]
    return None, []


def block_starts(data, base, entries):
    """Where each script block begins.

    A block ends by jumping into the common script - `09 <addr>` with an address
    outside this file (02OLB02A ends every block with `09 15 30`). The most common
    such jump is the file's own end-of-block idiom, so the byte after each one starts
    the next block. Confirmed against the files' own entry tables.
    """
    n = len(data)
    jumps = collections.Counter()
    for i in range(n - 3):
        if data[i] == 0x09:
            w = int.from_bytes(data[i + 1:i + 3], 'little')
            if not (base <= w < base + n):          # not a jump inside this file
                jumps[data[i:i + 3]] += 1
    starts = set(entries) | {0}
    if jumps:
        end, count = jumps.most_common(1)[0]
        if count >= 3:
            i = data.find(end)
            while i >= 0:
                starts.add(i + 3)
                i = data.find(end, i + 3)
    return sorted(a for a in starts if a < n)


def strings(data):
    """Every `40 02 <string> 00` in the file, as (start, end) of the string itself."""
    out = []
    i = 0
    while True:
        i = data.find(PRINT_OP, i)
        if i < 0:
            return out
        j = data.find(b'\x00', i + 2)
        if j < 0:
            return out
        if j > i + 2:
            out.append((i + 2, j))
        i = j + 1


def dump_rows():
    """filename -> [(offset, japanese, english)], offsets as ints."""
    import openpyxl
    from rominfo import DUMP_XLS_PATH
    out = collections.defaultdict(list)
    wb = openpyxl.load_workbook(DUMP_XLS_PATH, read_only=True)
    for sheet in wb.sheetnames:
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            fn, off, jp, jl, en = (list(row) + [None] * 5)[:5]
            if not fn or off is None:
                continue
            try:
                o = int(str(off), 16)
            except ValueError:
                continue
            out[fn].append((o, jp, en if isinstance(en, str) else None))
    for fn in out:
        out[fn].sort()
    return out


def analyse(path, rows):
    data = open(path, 'rb').read()
    fn = os.path.basename(path)
    base, entries = slot_base(data)
    if base is None:
        return None
    starts = block_starts(data, base, entries)
    spans = list(zip(starts, starts[1:] + [len(data)]))
    texts = strings(data)
    mine = rows.get(fn, [])
    blocks = []
    for lo, hi in spans:
        said = [(s, e) for s, e in texts if lo <= s < hi]
        offs = [o for o, jp, en in mine if any(s - 4 <= o <= e for s, e in said)]
        blocks.append({'at': lo, 'strings': len(said), 'rows': offs,
                       'entries': [i for i, a in enumerate(entries) if a == lo]})
    placed = {o for b in blocks for o in b['rows']}
    return {'file': fn, 'base': base, 'entries': len(entries), 'blocks_found': len(spans),
            'blocks': blocks, 'rows': len(mine), 'placed': len(placed),
            'translated': sum(1 for o, jp, en in mine if en and en.strip())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join('docs', 'script_map.md'))
    args = ap.parse_args()
    rows = dump_rows()
    results = []
    for path in sorted(glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN'))):
        r = analyse(path, rows)
        if r:
            results.append(r)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        def out(*t, **kw):
            print(*t, file=f, **kw)

        out('# Where every line of the dump lives in the scripts', end='\n\n')
        out('Generated by `script_map.py`. For each script file: every script block, which')
        out('entry-table index reaches it, and the dump rows it prints. Which trigger zone')
        out('runs which block is a runtime table, so that lives in docs/game_map.md.',
            end='\n\n')
        total_rows = sum(r['rows'] for r in results)
        total_placed = sum(r['placed'] for r in results)
        out('%d files, %d dump rows, %d placed in a block (%.0f%%).'
            % (len(results), total_rows, total_placed, 100.0 * total_placed / max(1, total_rows)),
            end='\n\n')
        out('## Translation progress by area', end='\n\n')
        out('Script filenames group by area (`02OLB*` is the port town Albein, `03YSK*`')
        out('the manor, and so on), which makes them a rough chapter order.', end='\n\n')
        out('| area | files | rows | translated |')
        out('|---|---|---|---|')
        areas = collections.defaultdict(lambda: [0, 0, 0])
        for r in results:
            a = re.match(r'[0-9]*[A-Z]+', r['file'])
            key = a.group(0) if a else r['file']
            areas[key][0] += 1
            areas[key][1] += r['rows']
            areas[key][2] += r['translated']
        for key in sorted(areas):
            n, rows_n, tr = areas[key]
            out('| %s | %d | %d | %d (%.0f%%) |'
                % (key, n, rows_n, tr, 100.0 * tr / max(1, rows_n)))
        out()

        for r in results:
            if not r['rows']:
                continue
            out('## %s (slot base 0x%04x, %d blocks, %d/%d rows placed, %d translated)'
                % (r['file'], r['base'], r['blocks_found'], r['placed'], r['rows'],
                   r['translated']), end='\n\n')
            for b in r['blocks']:
                if not b['rows']:
                    continue
                who = ['entry %d' % i for i in b['entries']]
                out('- 0x%04x %s: %s' % (b['at'], '(%s)' % ', '.join(who) if who else '',
                                         ', '.join('0x%x' % o for o in b['rows'][:14])
                                         + ('...' if len(b['rows']) > 14 else '')))
            out()
    print('%d files, %d/%d dump rows placed -> %s'
          % (len(results), total_placed, total_rows, args.out))


if __name__ == '__main__':
    main()
