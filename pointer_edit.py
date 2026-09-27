"""Gamefile whose pointer edits land where the pointer word currently is.

romtools' `Gamefile.edit_pointers_in_range(rng, diff)` is called by the reinserter once
per dump row, right after that row's text has been replaced, for the gap between the
previous row and this one. For every pointer whose *target* is in the gap it adds `diff`
(the growth *before* this row), via `BorlandPointer.edit`, which writes at
`ptr.location - block.start`. A pointer word's `location` is only moved when the walk
reaches the word itself.

So for a **backward pointer** - the word sits *after* the text it points at - the value
is written while the word still has its original location, although everything replaced
so far lies before it and has already shifted it. The new value lands early, on top of
whatever is there:

* text that is replaced later: harmless (how it went unnoticed);
* Japanese not yet replaced: the reinserter's "the Japanese is no longer where the dump
  says" assertion (02OLB02A.SCN @0xc24, once the Sept 2026 merge translated enough of
  the file before it);
* script bytecode: silent corruption, which no check catches.

And the real word keeps its old value (what tools/fix_pointers.py repairs after the fact).

The word's current position is its original offset plus the block's *actual* growth so
far - not `diff`, which leaves out the row just replaced (off by that row's own length
change) - because every replacement so far precedes the word and pointer writes never
change length. Before writing, the word's original bytes are checked to be there; if they
are not, the write is skipped and reported instead of landing somewhere unknown.

Kept here rather than in romtools because romtools is shared by every project in ../.
"""
from romtools.disk import Gamefile

SKIPPED = []     # (file, pointer location) whose word could not be found; see main loop


class KuroGamefile(Gamefile):
    def edit_pointers_in_range(self, rng, diff, allow_double_edits=False):
        start, stop = rng
        adjusted, withheld = [], {}
        if diff and self.blocks and self.pointers:
            here = next((b for b in self.blocks if b.start <= stop <= b.stop), None)
            if here is not None:
                grown = len(here.blockstring) - len(here.original_blockstring)
                for target in range(start + 1, stop + 1):
                    plist = self.pointers.get(target, [])
                    for p in list(plist):
                        # Only words past this gap, not yet moved by the base class, and in
                        # the block being walked (words in other blocks have not shifted).
                        if not (p.original_location > stop and p.location == p.original_location
                                and here.start <= p.original_location <= here.stop):
                            continue
                        L = p.original_location
                        at = L + grown - here.start
                        if here.blockstring[at:at + 2] == self.original_filestring[L:L + 2]:
                            p.location = L + grown
                            adjusted.append(p)
                        else:
                            withheld.setdefault(target, []).append(p)
                            plist.remove(p)
                            SKIPPED.append((self.filename, L))
                            print('WARNING: %s pointer at %#x not found where it should be; '
                                  'left for fix_pointers to check' % (self.filename, L))
        try:
            return super().edit_pointers_in_range(rng, diff, allow_double_edits)
        finally:
            # Put the word back at its original location: the base class moves it when
            # the walk reaches it, and matches it by that location.
            for p in adjusted:
                p.location = p.original_location
            for target, ps in withheld.items():
                self.pointers[target].extend(ps)
