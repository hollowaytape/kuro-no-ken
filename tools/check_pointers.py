"""Catch the "shifted text, stale pointer" crash class without running the game.

Reinserted English changes a script's length, so every address inside that file has to
move with it. `find_pointers` only knows the pointers its regexes match; the rest stay
stale and the interpreter jumps into the middle of a string, which ends as an exit to
DOS (03YSK01B.SCN, found by the autoplayer on 2026-09-20).

The check needs no emulator: a script's entry table at the top is `09 <addr>` per entry,
and every block begins right after the file's own end-of-block jump. So in a correctly
patched file, every entry address still lands on a block start. One that lands in the
middle of a block is a pointer that was not updated.

    python tools/check_pointers.py [--patched patched] [--original original/decompressed]
"""
import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)
from script_map import slot_base, block_starts        # noqa: E402


def as_script(data):
    """The patched file as the game sees it: some are stored compressed, some plain.

    A script always starts with its `09 <addr>` entry table, so anything else is a
    compression header.
    """
    if data[:1] == b'\x09':
        return data
    try:
        from decompress import decompress
        return decompress(data)
    except Exception:
        return None


def entry_addrs(data):
    out = []
    i = 0
    while i + 3 <= len(data) and data[i] == 0x09:
        out.append(int.from_bytes(data[i + 1:i + 3], 'little'))
        i += 3
    return out


def check(path_o, path_p):
    """Does every entry still point at the same block it pointed at before?

    Asking "is this a block start" on its own is too weak - the block finder misses
    some starts, so good files look broken. Comparing the two files does not need it
    to be complete: translation never adds or removes blocks, so entry i must point at
    the same *position in the list* of block starts as it did in the original.
    """
    o, p = open(path_o, 'rb').read(), open(path_p, 'rb').read()
    p = as_script(p)
    if p is None:
        return None                                    # could not be decompressed
    if o == p:
        return None                                    # not translated
    base, entries = slot_base(o)
    if base is None or not entries:
        return None                                    # no entry table to check
    starts_o, starts_p = block_starts(o, base, []), block_starts(p, base, [])
    if len(starts_o) != len(starts_p):
        return {'file': os.path.basename(path_o), 'grew': len(p) - len(o),
                'entries': len(entries),
                'bad': [(-1, 0, 'block count changed: %d -> %d'
                         % (len(starts_o), len(starts_p)))]}
    bad = []
    for i, (a_o, a_p) in enumerate(zip(entry_addrs(o), entry_addrs(p))):
        off_o, off_p = a_o - base, a_p - base
        if off_o not in starts_o:
            continue                                   # not a block we can track
        want = starts_p[starts_o.index(off_o)]
        if off_p != want:
            bad.append((i, off_p, 'should be %#06x (block %d)'
                        % (want, starts_o.index(off_o))))
    return {'file': os.path.basename(path_o), 'grew': len(p) - len(o),
            'entries': len(entries), 'bad': bad}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--patched', default='patched')
    ap.add_argument('--original', default=os.path.join('original', 'decompressed'))
    args = ap.parse_args()
    rows = []
    for path_o in sorted(glob.glob(os.path.join(HERE, args.original, '*.SCN'))):
        path_p = os.path.join(HERE, args.patched, os.path.basename(path_o))
        if not os.path.exists(path_p):
            continue
        r = check(path_o, path_p)
        if r:
            rows.append(r)
    broken = [r for r in rows if r['bad']]
    for r in rows:
        flag = 'BROKEN' if r['bad'] else 'ok    '
        print('%s %-16s %+6d bytes, %2d entries, %d bad'
              % (flag, r['file'], r['grew'], r['entries'], len(r['bad'])))
        for i, off, why in r['bad'][:6]:
            print('        entry %2d -> %#06x  %s' % (i, off, why))
    print('\n%d translated scripts checked, %d with stale entry pointers'
          % (len(rows), len(broken)))
    return 1 if broken else 0


if __name__ == '__main__':
    sys.exit(main())
