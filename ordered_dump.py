"""The dump workbook, read so that row order in the sheet does not matter.

romtools' `DumpExcel.get_translations` returns a file's rows in *sheet* order, and the
reinserter assumes that is ascending offset: pointer ranges run from one row to the next,
typeset tracks how full the text box is from the previous cell, and a length-sensitive
block is padded after its last string. Rows out of order do not fail loudly - pointer
ranges come out empty and pointers are silently skipped.

That used to be safe only because nobody reordered the sheet. The translator now builds
on her own, and the workbook carries a Story order column to sort by, so every row lookup
goes through this instead: the same rows, sorted by offset.

It also collapses exact duplicates. The translator's Google Sheet holds every row of
02OLB03A.SCN twice (two dumps pasted one after the other), and merging her sheet into the
repo brings them back each time. Replacing a string twice fails - the second copy's
Japanese is already gone - so each (offset, Japanese) keeps one row: the one with English.
If two copies carry *different* English the build stops and names the offset, rather than
silently dropping one of her edits.
"""
from romtools.dump import DumpExcel


class DuplicateRowConflict(ValueError):
    pass


class OrderedDumpExcel(DumpExcel):
    def get_translations(self, target, *args, **kwargs):
        rows = super().get_translations(target, *args, **kwargs)
        kept = {}
        for t in rows:
            key = (t.location, t.jp_bytestring)
            if key not in kept:
                kept[key] = t
                continue
            have, new = kept[key].en_bytestring, t.en_bytestring
            if new and not have:
                kept[key] = t
            elif new and have and new != have:
                raise DuplicateRowConflict(
                    '%s @%#x appears twice in the workbook with different English:\n'
                    '    %r\n    %r\nKeep one and clear the other.' % (
                        getattr(getattr(target, 'gamefile', target), 'filename', target), t.location,
                        have.decode('cp932', 'replace'), new.decode('cp932', 'replace')))
        return sorted(kept.values(), key=lambda t: t.location)
