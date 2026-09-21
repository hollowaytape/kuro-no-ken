"""
    Kuro no Ken reinserter.
"""

import os
import sys
from shutil import copyfile

# bsd_tool, fix_pointers and script_map live in tools/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))

from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel
from rominfo import SRC_DISK, DEST_DISK, FILES, FILES_TO_REINSERT, COMPRESSED_FILES_TO_EDIT, ARCHIVES_TO_REINSERT
from rominfo import FILE_BLOCKS, LENGTH_SENSITIVE_BLOCKS, DECOMPRESSED_SIZE_LIMITS, NAMES
from rominfo import  DUMP_XLS_PATH, POINTER_XLS_PATH, POINTERS_TO_REASSIGN, CONTROL_CODES
from rominfo import MAPPING_BUILD
from rominfo import BSD_FILES_WITH_TEXT, BSD_DECOMPRESSED_SIZE_LIMIT

from asm import BYTE_EDITS
from fa1 import repack, unpack
from bsd_tool import parse_bsd, reinsert_bsd
from decompress import decompress
import fix_pointers

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_XLS_PATH)

# Area hub scripts whose only text is the centered location name. Their pointer
# tables can't be trusted (the regex finder misreads the hub's fixed-size script
# units), so their strings must keep the exact Japanese byte length: they skip
# typeset() (which collapses the centering spaces) and get space-padded.
FIXED_LENGTH_SCN = {'02OLB.SCN', '03YSK.SCN'}

# Map scripts with no `09 <addr>` entry table (12MRS.SCN, 01FLD.SCN...) can't be decoded
# reliably, so gen_pointers gives them no pointer sheet - but they end in a zone table of
# block addresses, and any length change strands it (the crash #4 class). Until their
# zone tables are located, their strings keep the exact Japanese length too; an English
# line that doesn't fit stops the build with a message instead of crashing the game.
def _no_entry_table(fn):
    from script_map import slot_base
    path = os.path.join('original', 'decompressed', fn)
    return os.path.exists(path) and slot_base(open(path, 'rb').read())[0] is None

# 00IPL.SCN and 02OLB00A.SCN have no entry table either, but they are hand-listed scripts
# whose pointers were curated and verified in game, so the rule is only for the rest.
# (07CSLI0x, 09HIKI01, 25TOU00A/C are stranger still: they start mid-structure and end in
# x86 code, and no pointer in them decodes.) If one of these has a line that doesn't fit,
# the file is left in Japanese with a warning rather than stopping the whole build.
from rominfo import CURATED_FILES
UNKNOWN_FORMAT_SCN = {f for f in FILES_TO_REINSERT if f.endswith('.SCN') and _no_entry_table(f)
                      and f not in CURATED_FILES}
FIXED_LENGTH_SCN |= UNKNOWN_FORMAT_SCN
SKIPPED_TOO_LONG = []


def too_long_for_fixed(gf):
    """-> [(offset, english, jp_len)] for lines that can't keep the Japanese length."""
    probe = Block(gf, (0, len(gf.original_filestring)))
    return [(t.location, t.en_bytestring, len(t.jp_bytestring))
            for t in Dump.get_translations(probe, include_blank=True, sheet_name='SCNs')
            if t.en_bytestring and len(t.en_bytestring) > len(t.jp_bytestring)]

LINE_MAX = 48
INDENT = b'  '
NEWLINE_SEQ = b'\\n\x00\x40\x02'   # \n + rendering sync (5C 6E 00 40 02)
SPLIT_SEQ = b'\\f\x00;@\x02'       # \f page break (5C 66 00 3B 40 02)

def wrap_line(text, max_width=LINE_MAX, indent=INDENT):
    """Word-wrap a single line of text, returning a list of wrapped lines."""
    if not text:
        return [indent]

    words = text.split(b' ')
    lines = []
    current = indent

    for word in words:
        if not word:
            continue
        needed = len(current) + len(word) + (1 if current != indent else 0)
        if needed > max_width and current != indent:
            lines.append(current.rstrip())
            current = indent
        if current == indent:
            current += word
        else:
            current += b' ' + word

    if current and current != indent:
        lines.append(current.rstrip())
    elif not lines:
        lines = [indent]

    return lines

BOX_ROWS = 5   # a text box shows a speaker name + 4 lines (02OLB00A 0x3bb's 6th row never showed)


def typeset(s, rows_before=0):
    """Format English text for the game's text box.

    Word-wraps to LINE_MAX characters per line with INDENT prefix, honours
    [SPLIT] page breaks and existing newlines, and starts a new page ([SPLIT])
    whenever the box would run past BOX_ROWS rows. `rows_before` is how many
    rows of the current page earlier cells already used (tracked in the reinsert loop).
    Character names from NAMES are returned unchanged.

    Returns (bytes, rows used on the page the text ends on).
    """
    if s in NAMES:
        return s, rows_before + 1

    out_pages = []
    rows = rows_before
    for page_no, page in enumerate(s.split(SPLIT_SEQ)):
        if page_no:
            rows = 0
        lines = []
        for raw_line in page.split(NEWLINE_SEQ):
            lines.extend(wrap_line(raw_line))
        current = []
        for line in lines:
            if rows >= BOX_ROWS:
                # Box full: this line goes on a fresh page. (If this is the cell's
                # first line, the page break comes right after the previous cell's
                # \n, which only moves the cursor below the box - nothing is drawn.)
                out_pages.append(current)
                current, rows = [], 0
            current.append(line)
            rows += 1
        out_pages.append(current)
    return SPLIT_SEQ.join(NEWLINE_SEQ.join(p) for p in out_pages), rows


_ORIGINAL_SCRIPTS = {}


def cell_ends_page(filename, offset):
    """Does the original script end the text box's page after the text at
    `offset`? A \\n (5C 6E) continues the page; \\f (5C 66) or any script
    opcode ends it."""
    if filename not in _ORIGINAL_SCRIPTS:
        path = os.path.join('original', 'decompressed', filename)
        if not os.path.exists(path):
            path = os.path.join('original', filename)
        _ORIGINAL_SCRIPTS[filename] = open(path, 'rb').read()
    data = _ORIGINAL_SCRIPTS[filename]
    i = offset
    while i < len(data):
        b = data[i]
        if 0x81 <= b <= 0x9f or b >= 0xe0:
            i += 2
            continue
        if b == 0x5c and i + 1 < len(data) and data[i + 1] == 0x6e:
            return False
        if b < 0x20 or b == 0x5c:
            return True
        i += 1
    return True


if __name__ == '__main__':
    OriginalBOD = Disk(SRC_DISK, dump_excel=Dump, pointer_excel=PtrDump)
    TargetBOD = Disk(DEST_DISK)

    # First, extract the current save file from the patched game so I don't lose progress
    # tools/reinsert_without.py resets the patched disk first, so it copies the
    # saves out beforehand and sets this; otherwise we'd copy the blank originals.
    if not os.environ.get('KURO_SAVES_ALREADY_COPIED'):
        TargetBOD.extract('A.FA1', path_in_disk="B-DRKNS", dest_path="patched")
        unpack(b'A.FA1', file_dir=b'patched')

        copyfile(os.path.join('patched', 'BD_FLAG0.DAT'), os.path.join('original', 'BD_FLAG0.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG1.DAT'), os.path.join('original', 'BD_FLAG1.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG2.DAT'), os.path.join('original', 'BD_FLAG2.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG3.DAT'), os.path.join('original', 'BD_FLAG3.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG4.DAT'), os.path.join('original', 'BD_FLAG4.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG5.DAT'), os.path.join('original', 'BD_FLAG5.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG6.DAT'), os.path.join('original', 'BD_FLAG6.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAG7.DAT'), os.path.join('original', 'BD_FLAG7.DAT'))
        copyfile(os.path.join('patched', 'BD_FLAGH.DAT'), os.path.join('original', 'BD_FLAGH.DAT'))

    #input()

    # (otherwise) Fresh start each reinsertion
    #copyfile(SRC_DISK, DEST_DISK)

    # Because the archives get re-inserted with all files, need to copy all the original files into the
    # patched directory to ensure a fresh start.
    for f in FILES:
        if f.source.decode("ASCII") in ARCHIVES_TO_REINSERT:
            filename = f.name.decode("ASCII")
            
            original_path = os.path.join('original', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

    for filename in FILES_TO_REINSERT:
        #print(filename)
        try:
            original_path = os.path.join('original', 'decompressed', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

        except FileNotFoundError:
            original_path = os.path.join('original', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

        # original/decompressed/ holds RAM dumps, and a dump can run past the end of its
        # file into whatever was loaded next: 27KKII01.SCN and 10TNII01.SCN end in ~25
        # bytes of a neighbour's script (10TNII01's tail is someone else's Japanese and
        # print opcodes) where the real file has its trailing table. Building from the
        # dump bakes that in. Start from the real compressed stream instead - the same
        # fix the BSD path below already has. For every other script the two are
        # byte-identical, so this changes nothing there.
        if filename.endswith('.SCN') and os.path.exists(os.path.join('original', filename)):
            dumped = open(patched_path, 'rb').read()
            real = decompress(open(os.path.join('original', filename), 'rb').read())
            if real != dumped and len(real) == len(dumped):
                open(patched_path, 'wb').write(real)
                print('  %s: using the decompressed stream, not the RAM dump (%d bytes differ)'
                      % (filename, sum(a != b for a, b in zip(real, dumped))))

        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)

        if filename in UNKNOWN_FORMAT_SCN:
            over = too_long_for_fixed(gf)
            if over:
                # patched/ holds the decompressed original now, which repack recognises
                # as unchanged and stores as the original compressed bytes.
                SKIPPED_TOO_LONG.append((filename, over))
                print('WARNING: %s left in Japanese - %d line(s) longer than the Japanese, '
                      'which this script cannot take yet: %s' % (
                          filename, len(over), ', '.join('%#x %r (max %d)' % (o, e.decode('cp932', 'replace'), n)
                                                         for o, e, n in over[:4])))
                continue

        # TEMP: Let's see if we can get the pointers to be aware of block structure this way
        if filename in FILE_BLOCKS:
            blocks = [Block(gf, (start, stop)) for start, stop in FILE_BLOCKS[filename]]
            gf.blocks = blocks
        else:
            gf.blocks = []

        if filename in POINTERS_TO_REASSIGN:
            #print("Time to reassign some pointers")
            reassignments = POINTERS_TO_REASSIGN[filename]
            for src, dest in reassignments:
                #print("Reassigning", hex(src), hex(dest))
                if src not in gf.pointers:
                    #print("Skipping this one: %s, %s" % (hex(src), hex(dest)))
                    continue
                if dest not in gf.pointers:
                    #print("No pointer for that dest. We'll just move the src pointer to the dest")
                    gf.pointers[dest] = []
                #assert src in gf.pointers
                #assert dest in gf.pointers
                diff = dest - src
                assert dest == src + diff
                for p in gf.pointers[src]:
                    p.edit(diff)
                gf.pointers[dest] += gf.pointers[src]
                gf.pointers.pop(src)

        if filename in BYTE_EDITS:
            #print(BYTE_EDITS[filename])
            for (loc, value) in BYTE_EDITS[filename]:
                gf.edit(loc, value)

        for block in gf.blocks:
            #print(block)
            previous_text_offset = block.start
            diff = 0
            last_text_end = None
            #print(repr(block.blockstring))
            if filename.endswith('SCN'):
                #print(filename)
                translations = Dump.get_translations(block, include_blank=True, sheet_name="SCNs")
                #print(translations)
            elif filename.endswith('BSD'):
                #print("Using the BSDs sheet")
                translations = Dump.get_translations(block, include_blank=True, sheet_name="BSDs")

            else:
                translations = Dump.get_translations(block, include_blank=True)
            page_rows = 0      # rows used on the current text-box page (SCN typesetting)
            prev_t = None
            for t in translations:
                #print(t)
                if filename.endswith('.SCN') and prev_t is not None and cell_ends_page(filename, prev_t.location):
                    page_rows = 0
                prev_t = t
                if t.en_bytestring == b'':
                    t.en_bytestring = t.jp_bytestring
                # A mapping build writes FILE-INDEX placeholders that already fit the
                # line and carry the original's own control codes, so typesetting them
                # only re-encodes each newline from 2 bytes to 5 and makes the file grow
                # when it is meant to stay exactly the same size.
                typeset_scn = (filename.endswith('.SCN') and filename not in FIXED_LENGTH_SCN
                               and not MAPPING_BUILD)
                if typeset_scn and t.en_bytestring == t.jp_bytestring:
                    # untranslated: its Japanese rows still take up the box
                    page_rows += 1 + t.jp_bytestring.count(b'\\n')
                    typeset_scn = False
                    
                for cc in CONTROL_CODES:
                    if cc in t.en_bytestring:
                        t.en_bytestring = t.en_bytestring.replace(cc, CONTROL_CODES[cc])

                if t.en_bytestring != t.jp_bytestring:
                    #print(t.en_bytestring)
                        # Prepend 85, add 1f if it's a num, sub 2 if it's a char
                    if 0xb0 <= t.jp_bytestring[0] <= 0xdf:
                        #print("This is a halfwidth kana string")
                        new_bytestring = b''
                        for b in t.jp_bytestring:
                            if 0xb0 <= b <= 0xdf:
                                new_bytestring += b'\x85' + (b - 2).to_bytes(1, 'little')
                            elif b == 0x20:
                                new_bytestring += b'\x20'
                            else:
                                new_bytestring += b'\x85' + (b + 0x1f).to_bytes(1, 'little')
                        #print(t.jp_bytestring)
                        #print(new_bytestring)
                        t.jp_bytestring = new_bytestring

                    # Auto-indent lines that begin with a quote in SCN files
                    #if t.en_bytestring:
                    #    if t.en_bytestring.startswith(b'"') and filename.endswith('SCN'):
                    #        print(t.en_bytestring[0], t.en_bytestring[0] == 0x20)
                    #        t.en_bytestring = b' ' + t.en_bytestring

                    if filename in FIXED_LENGTH_SCN:
                        if len(t.en_bytestring) > len(t.jp_bytestring):
                            raise ValueError('%s @%s: %r is %d bytes, over the %d-byte Japanese length' % (
                                filename, hex(t.location), t.en_bytestring,
                                len(t.en_bytestring), len(t.jp_bytestring)))
                        t.en_bytestring = t.en_bytestring.ljust(len(t.jp_bytestring), b' ')
                    elif typeset_scn and t.en_bytestring:
                        # Typeset SCN files (word-wrap for text box, new page when full)
                        t.en_bytestring, page_rows = typeset(t.en_bytestring, page_rows)
                        typeset_scn = False      # rows already counted


                    #print(t)
                    loc_in_block = t.location - block.start + diff

                    # New style of reinsertion - prevents the issue where you'd need to start
                    # at the first repetition of a string
                    this_original_segment = block.blockstring[loc_in_block:]
                    this_segment = block.blockstring[loc_in_block:]
                    #print([hex(i) for i in t.jp_bytestring])
                    #print([hex(i) for i in this_segment])
                    assert t.jp_bytestring in this_segment, (
                        f'{filename} @{t.location:#x}: the Japanese is no longer where the dump says; '
                        'an earlier pointer edit probably wrote into this text (a false-positive pointer)')
                    idx_in_segment = this_segment.index(t.jp_bytestring)
                    this_segment = this_segment.replace(t.jp_bytestring, t.en_bytestring, 1)
                    block.blockstring = block.blockstring.replace(this_original_segment, this_segment)
                    last_text_end = loc_in_block + idx_in_segment + len(t.en_bytestring)


                    # Old style. Getting replaced
                    """
                    #print(t.jp_bytestring)
                    i = block.blockstring.index(t.jp_bytestring)
                    j = block.blockstring.count(t.jp_bytestring)

                    index = 0
                    while index < len(block.blockstring):
                        index = block.blockstring.find(t.jp_bytestring, index)
                        if index == -1:
                            break
                        index += len(t.jp_bytestring) # +2 because len('ll') == 2

                    if j > 1:
                        print("%s multiples of this string found" % j)
                    assert loc_in_block == i, (hex(loc_in_block), hex(i))
                    """

                    #block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)

                if gf.pointers:
                    gf.edit_pointers_in_range((previous_text_offset, t.location), diff)

                previous_text_offset = t.location

                this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                diff += this_diff

            block_diff = len(block.blockstring) - len(block.original_blockstring)

            # SCN length-sensitive blocks that shrank get padded right after the last
            # translated string (below), which puts everything after it back in its
            # original position - so pointers past that string must not be shifted.
            pads_after_last_text = (filename.endswith('SCN') and
                                    (block.start, block.stop) in LENGTH_SENSITIVE_BLOCKS.get(filename, []) and
                                    block_diff < 0)

            if pads_after_last_text and gf.pointers:
                # Untranslated rows after the last replaced string were already shifted
                # in the loop above, but the padding puts them back.
                print('WARNING: %s is padded after its last string but has pointers - '
                      'pointers targeting untranslated rows after it will be off' % block)

            # 03YSK01A has some pointers pointing to near the end of the file. Need a way to edit those
            if gf.pointers and not pads_after_last_text:
                gf.edit_pointers_in_range((previous_text_offset, block.stop), diff)

            # Ignore size differences in .SCN files
            if filename in LENGTH_SENSITIVE_BLOCKS:
                if (block.start, block.stop) in LENGTH_SENSITIVE_BLOCKS[filename]:
                    print(block, "is length sensitive")
                    if block_diff < 0:
                        print("block_diff of", block, "is", block_diff)
                        padding_len = (-1)*block_diff
                        if filename.endswith('SCN'):
                            # Pad inside the last translated string, before its terminator.
                            # A block's end can fall in script bytecode, where 0x20 is a
                            # real opcode - trailing spaces there crash the interpreter.
                            assert last_text_end is not None, block
                            block.blockstring = (block.blockstring[:last_text_end] +
                                                 b' '*padding_len +
                                                 block.blockstring[last_text_end:])
                        else:
                            block.blockstring += padding_len*b'\x00'
                    block_diff = len(block.blockstring) - len(block.original_blockstring)
                    assert block_diff == 0, (block_diff, block)

            block.incorporate()

        # Backward pointers (the pointer word sits after the text it points at) are
        # written at a stale index by BorlandPointer.edit and so keep their old value.
        # Now that the file is final, rewrite the ones whose target provably moved.
        if filename.endswith('.SCN'):
            fixed, ptr_fixes = fix_pointers.repair(filename, gf.original_filestring, gf.filestring)
            if ptr_fixes:
                gf.filestring = fixed
                print('  %s: repaired %d backward pointer(s): %s' % (
                    filename, len(ptr_fixes),
                    ', '.join('%#x->%#x' % (old, new) for _loc, old, new in ptr_fixes)))

        gf.write(skip_disk=True)

        # Check decompressed file size against its RAM slot (see rominfo.SCN_SLOT_SIZES)
        if filename in DECOMPRESSED_SIZE_LIMITS:
            file_size = len(gf.filestring)
            limit = DECOMPRESSED_SIZE_LIMITS[filename]
            if file_size > limit:
                print('WARNING: %s is %s bytes, exceeds RAM limit of %s (+%d bytes over)' % (
                    filename, hex(file_size), hex(limit), file_size - limit))
            else:
                slack = limit - file_size
                print('  %s: %s / %s (%d bytes of slack)' % (
                    filename, hex(file_size), hex(limit), slack))

    # BSD battle script reinsertion using structural disassembly/reassembly
    for filename in BSD_FILES_WITH_TEXT:
        # Build from the real compressed stream, not original/decompressed/: those are
        # RAM dumps, and the game relocates BSD data in place (header, event table,
        # handler variables), so several dumps hold runtime values that must not be
        # baked into the reinserted file.
        try:
            original_compressed = open(os.path.join('original', filename), 'rb').read()
        except FileNotFoundError:
            print('WARNING: %s not found in original/, skipping' % filename)
            continue
        data = decompress(original_compressed)
        patched_path = os.path.join('patched', filename)
        open(patched_path, 'wb').write(data)
        parsed = parse_bsd(data)

        if not parsed['text_regions']:
            continue

        # Build a single block spanning all text for DumpExcel lookup
        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)
        first_text = min(r.offset for r in parsed['text_regions'])
        last_text = max(r.end for r in parsed['text_regions'])
        block = Block(gf, (first_text, last_text + 1))

        translations_raw = Dump.get_translations(block, include_blank=True, sheet_name="BSDs")

        # Build translations list for bsd_tool: (offset, jp_bytes, en_bytes)
        translations = []
        for t in translations_raw:
            if t.en_bytestring == b'':
                t.en_bytestring = t.jp_bytestring

            for cc in CONTROL_CODES:
                if cc in t.en_bytestring:
                    t.en_bytestring = t.en_bytestring.replace(cc, CONTROL_CODES[cc])

            # Typeset BSD dialogue text (same word-wrapping as SCN)
            # (no page tracking here yet: BSD pages aren't split automatically)
            if t.en_bytestring and t.en_bytestring != t.jp_bytestring:
                t.en_bytestring, _ = typeset(t.en_bytestring)

            translations.append((t.location, t.jp_bytestring, t.en_bytestring))

        result = reinsert_bsd(data, translations)

        if result != data:
            open(patched_path, 'wb').write(result)
            print('  %s: %d -> %d bytes (%+d)' % (
                filename, len(data), len(result), len(result) - len(data)))
            if len(result) > BSD_DECOMPRESSED_SIZE_LIMIT:
                print('  WARNING: %s is %s bytes, exceeds shared battle-buffer '
                      'limit of %s (+%d bytes over) - see BSD_DECOMPRESSED_SIZE_LIMIT '
                      'in rominfo.py' % (
                          filename, hex(len(result)), hex(BSD_DECOMPRESSED_SIZE_LIMIT),
                          len(result) - BSD_DECOMPRESSED_SIZE_LIMIT))
        else:
            print('  %s: no changes' % filename)

    # Editing compressed files without decompressing them. A truly barbaric practice
    for filename in COMPRESSED_FILES_TO_EDIT:
        print(filename)
        original_path = os.path.join('original', filename)
        patched_path = os.path.join('patched', filename)
        copyfile(original_path, patched_path)

        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)

        if filename in BYTE_EDITS:
            print(BYTE_EDITS[filename])
            for (loc, value) in BYTE_EDITS[filename]:
                gf.edit(loc, value)
                
        gf.write(skip_disk=True)

    for filename in ARCHIVES_TO_REINSERT:
        gamefile_path = os.path.join('patched', filename)

        repack(gamefile_path)
        # Gotta repack it first, then initialize the gamefile
        gf = Gamefile(gamefile_path, disk=OriginalBOD, dest_disk=TargetBOD)

        gf.write(path_in_disk='B-DRKNS')