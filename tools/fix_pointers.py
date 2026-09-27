"""Find (and, called from reinsert, repair) pointers reinsert leaves behind.

History: this began as the repair for backward pointers, below. That bug is now fixed at
its source (pointer_edit.KuroGamefile), and reinsert records its exact edits, so this is
the safety net for pointers the decoder knows and the pointer sheet does not.


`Gamefile.edit_pointers_in_range` walks the dump rows of a block in ascending order
and, for each gap between two consecutive rows, adds the diff accumulated so far to
every pointer whose *target* falls in that gap. `BorlandPointer.edit` then locates the
pointer word by `self.location - block.start` - the word's **original** offset. That
index is only still right if the word sits *before* all the text that has shifted so
far.

A pointer whose word sits *after* the text it points at - a backward branch, e.g.
`07 0d 02 00 <addr>` jumping back to an earlier block - is therefore written at an
index short by the accumulated diff. The real pointer word keeps its old value, and
the stray write lands in text that the next replacement overwrites, so nothing looks
wrong until the game jumps through the stale address.

351 of the 2872 decoded pointers are backward ones. Most are harmless (nothing shifted
between the target and the word), but in the all-files build three were genuinely
stale: 05SKS04.SCN 0x8ec and 0x928, and 17DRL01B.SCN 0x10d4.

This runs after a file's blocks are incorporated, when the final bytes are known, and
rewrites exactly the pointer words whose target provably moved while their stored value
did not. It is the same test `tools/stale_report.py` reports, applied instead of
printed - so a clean `stale_report` after a build means this pass had nothing left to do.
"""
import difflib
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

_ANALYSED = {}


def offset_map(o, p):
    """old offset -> new offset. Equal runs map 1:1, and so does a same-length
    replacement - which is what a rewritten pointer word looks like."""
    m = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o, p, autojunk=False).get_opcodes():
        if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                m[i1 + k] = j1 + k
    return m


def _analyse(fn):
    if fn not in _ANALYSED:
        import script_decode as sd
        try:
            _ANALYSED[fn] = sd.analyse(fn)
        except Exception:
            _ANALYSED[fn] = None
    return _ANALYSED[fn]


class ExactMap(object):
    """old offset -> new offset from reinsert's own record of what it changed.

    `edits` is [(where, old length, new length)] in original offsets. Bytes inside a
    replaced span have no counterpart (None); everything else moves by the sum of the
    length changes that end at or before it. Unlike difflib this cannot slip.
    """
    def __init__(self, edits):
        self.edits = sorted(edits)

    def get(self, x, default=None):
        shift = 0
        for at, old, new in self.edits:
            if at + old <= x:
                shift += new - old
            elif at <= x:
                return default                  # inside replaced text
            else:
                break
        return x + shift


def edits_path(patched_path):
    return patched_path + '.edits.json'


def save_edits(patched_path, edits):
    import json
    with open(edits_path(patched_path), 'w') as f:
        json.dump(edits, f)


def load_edits(patched_path):
    import json
    try:
        with open(edits_path(patched_path)) as f:
            return [tuple(e) for e in json.load(f)]
    except (OSError, ValueError):
        return None


def skipped(filename, loc, target, entry_slot=False):
    """rominfo.POINTERS_TO_SKIP, found in game. Its target-form entries do not apply to the
    entry table, whose slots the engine enters through and so are always real (02OLB03A's
    slot 0x19 -> 0x33b was being kept out by the `('02OLB03A.SCN', 0x33b)` entry)."""
    from rominfo import POINTERS_TO_SKIP
    if (filename, loc, 'pointer_location') in POINTERS_TO_SKIP:
        return True
    return not entry_slot and (filename, target) in POINTERS_TO_SKIP


def repair(filename, original, patched, edits=None):
    """-> (patched bytes, [(ptr_loc, old_target, new_target)]).

    `original` and `patched` are the decompressed script before and after reinsertion.
    `edits` is reinsert's record of its length changes; without it the offsets are
    re-derived with difflib, which is only an approximation - it slipped 2 bytes in
    05SKS03 and "repaired" two correct pointers into wrong ones.
    """
    if not filename.endswith('.SCN') or patched == original:
        return patched, []
    r = _analyse(filename)
    if not r or r.get('guessed_base'):
        # No entry table: the slot base is a guess and the decode is not trustworthy
        # enough to rewrite bytes from (see gen_pointers).
        return patched, []
    base = r['base']
    exact = edits is not None
    amap = ExactMap(edits) if exact else offset_map(original, patched)

    # difflib will happily slide a repetitive run (an entry table is N copies of
    # `09 xx 18`), and the word read back is then a neighbour's, which looks stale when
    # it is not. Only trust a mapping that lands on the same opcode byte.
    starts = {}
    for at, _op, vals in r['insns']:
        for _k, vloc, _v in vals:
            starts[vloc] = at

    # The entry table sits at the very top and never moves, so read its slots directly.
    entry_slots = {1 + 3 * k for k in range(len(r['entries']))}

    out = bytearray(patched)
    fixes = []
    for loc, target in r['pointers']:
        if skipped(filename, loc, target, loc in entry_slots):
            continue
        at = starts.get(loc)
        if at is not None:
            ja = amap.get(at)
            if ja is None or ja >= len(patched) or patched[ja] != original[at]:
                continue
        want = amap.get(target)
        j = loc if loc in entry_slots else amap.get(loc)
        if want is None or j is None or want == target or j + 2 > len(out):
            continue                                   # target did not move
        if int.from_bytes(out[j:j + 2], 'little') - base != target:
            continue                                   # already updated
        out[j:j + 2] = (want + base).to_bytes(2, 'little')
        fixes.append((loc, target, want))
    return bytes(out), fixes


def main():
    """Report what a repair would change in patched/, without writing anything."""
    import glob
    from check_pointers import as_script
    names = sys.argv[1:] or sorted(os.path.basename(x) for x in
                                   glob.glob(os.path.join(HERE, 'patched', '*.SCN')))
    total = 0
    for fn in names:
        po = os.path.join(HERE, 'patched', fn)
        oo = os.path.join(HERE, 'original', 'decompressed', fn)
        if not (os.path.exists(po) and os.path.exists(oo)):
            continue
        p = as_script(open(po, 'rb').read())
        if p is None:
            continue
        _, fixes = repair(fn, open(oo, 'rb').read(), p, edits=load_edits(po))
        if fixes:
            total += len(fixes)
            print('%-18s %d stale' % (fn, len(fixes)))
            for loc, old, new in fixes:
                print('      %#06x: %#06x should now be %#06x' % (loc, old, new))
    print('%d stale pointer(s)' % total)


if __name__ == '__main__':
    main()
