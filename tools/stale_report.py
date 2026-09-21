"""How many of a script's real pointers did reinsert leave behind?

Combines the two halves that were missing from each other:

* `script_decode` says which words are addresses (from the interpreter's own opcode
  handlers, so no guessing),
* the original/patched alignment says which of those targets moved.

A pointer that is an address *and* whose target moved *and* whose stored value did not
change is stale - the game will jump into whatever now sits at the old offset.

    python tools/stale_report.py            # every translated script
    python tools/stale_report.py 02OLB01.SCN
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import script_decode as sd                                   # noqa: E402
from check_pointers import as_script                         # noqa: E402
from deep_pointer_audit import offset_map                    # noqa: E402

ORIG = os.path.join(HERE, '..', 'original', 'decompressed')
PATCHED = os.path.join(HERE, '..', 'patched')


def stale(fn):
    o = open(os.path.join(ORIG, fn), 'rb').read()
    pp = os.path.join(PATCHED, fn)
    if not os.path.exists(pp):
        return None
    p = as_script(open(pp, 'rb').read())
    if p is None or p == o:
        return None
    r = sd.analyse(fn)
    if not r:
        return None
    amap = offset_map(o, p)
    base = r['base']
    # difflib happily slides a repetitive run (an entry table is 31 copies of
    # `09 xx 18`), and then the "patched" word read back is a neighbour's, which looks
    # stale when it is not. Only trust a mapping that lands on the same opcode byte.
    starts = {}
    for at, _op, vals in r['insns']:
        for _k, vloc, _v in vals:
            starts[vloc] = at
    out = []
    for loc, target in r['pointers']:
        at = starts.get(loc)
        if at is not None:
            ja = amap.get(at)
            if ja is None or ja >= len(p) or p[ja] != o[at]:
                continue
        want = amap.get(target)
        # The entry table is at the very top of the file and never moves, so read its
        # slots where they are rather than through the alignment.
        entry_slots = {1 + 3 * k for k in range(len(r['entries']))}
        j = loc if loc in entry_slots else amap.get(loc)
        if want is None or j is None or want == target:
            continue                                   # target did not move
        if j + 2 > len(p):
            continue
        here = int.from_bytes(p[j:j + 2], 'little') - base
        if here == target:                             # value unchanged: left behind
            out.append((loc, target, want))
    return {'file': fn, 'pointers': len(r['pointers']), 'stale': out,
            'grew': len(p) - len(o)}


def main():
    names = sys.argv[1:] or sorted(os.path.basename(x) for x in glob.glob(os.path.join(ORIG, '*.SCN')))
    total = 0
    for fn in names:
        try:
            r = stale(fn)
        except Exception as ex:
            print('%-16s decode failed: %s' % (fn, str(ex)[:40]))
            continue
        if not r:
            continue
        n = len(r['stale'])
        total += n
        print('%-16s %+6d bytes, %3d pointers, %3d STALE' % (r['file'], r['grew'], r['pointers'], n))
        for loc, old, new in r['stale'][:6]:
            print('      %#06x: %#06x should now be %#06x' % (loc, old, new))
    print('\n%d stale pointer(s) across the translated scripts' % total)


if __name__ == '__main__':
    main()
