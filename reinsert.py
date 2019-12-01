"""
    Kuro no Ken reinserter.
"""

import os
from shutil import copyfile
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel
from rominfo import SRC_DISK, DEST_DISK, FILES, FILES_TO_REINSERT, ARCHIVES_TO_REINSERT
from rominfo import FILE_BLOCKS, LENGTH_SENSITIVE_BLOCKS
from rominfo import  DUMP_XLS_PATH, POINTER_XLS_PATH, POINTERS_TO_REASSIGN, CONTROL_CODES
from cheats import BYTE_EDITS
from fa1 import repack

Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_XLS_PATH)

if __name__ == '__main__':
    # Fresh start each reinsertion
    copyfile(SRC_DISK, DEST_DISK)

    OriginalBOD = Disk(SRC_DISK, dump_excel=Dump, pointer_excel=PtrDump)
    TargetBOD = Disk(DEST_DISK)

    # Because the archives get re-inserted with all files, need to copy all the original files into the
    # patched directory to ensure a fresh start.
    for f in FILES:
        if f.source.decode("ASCII") in ARCHIVES_TO_REINSERT:
            filename = f.name.decode("ASCII")
            
            original_path = os.path.join('original', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

    for filename in FILES_TO_REINSERT:
        print(filename)
        try:
            original_path = os.path.join('original', 'decompressed', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

        except FileNotFoundError:
            original_path = os.path.join('original', filename)
            patched_path = os.path.join('patched', filename)
            copyfile(original_path, patched_path)

        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)

        # TEMP: Let's see if we can get the pointers to be aware of block structure this way
        if filename in FILE_BLOCKS:
            blocks = [Block(gf, (start, stop)) for start, stop in FILE_BLOCKS[filename]]
            gf.blocks = blocks
        else:
            gf.blocks = []

        if filename in POINTERS_TO_REASSIGN:
            print("Time to reassign some pointers")
            reassignments = POINTERS_TO_REASSIGN[filename]
            for src, dest in reassignments:
                print("Reassigning", hex(src), hex(dest))
                if src not in gf.pointers:
                    print("Skipping this one: %s, %s" % (hex(src), hex(dest)))
                    continue
                if dest not in gf.pointers:
                    print("No pointer for that dest. We'll just move the src pointer to the dest")
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
            print(BYTE_EDITS[filename])
            for (loc, value) in BYTE_EDITS[filename]:
                gf.edit(loc, value)

        for block in gf.blocks:
            print(block)
            previous_text_offset = block.start
            diff = 0
            #print(repr(block.blockstring))
            if filename.endswith('SCN'):
                #print(filename)
                translations = Dump.get_translations(block, include_blank=True, sheet_name="SCNs")
                #print(translations)
            else:
                translations = Dump.get_translations(block, include_blank=True)
            for t in translations:
                if t.en_bytestring == b'':
                    t.en_bytestring = t.jp_bytestring
                    
                for cc in CONTROL_CODES:
                    if cc in t.en_bytestring:
                        t.en_bytestring = t.en_bytestring.replace(cc, CONTROL_CODES[cc])

                if t.en_bytestring != t.jp_bytestring:
                    print(t.en_bytestring)
                        # Prepend 85, add 1f if it's a num, sub 2 if it's a char
                    if 0xb0 <= t.jp_bytestring[0] <= 0xdf:
                        print("This is a halfwidth kana string")
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


                    #print(t)
                    loc_in_block = t.location - block.start + diff

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

                    block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)

                if gf.pointers:
                    gf.edit_pointers_in_range((previous_text_offset, t.location), diff)

                previous_text_offset = t.location

                this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                diff += this_diff

            # 03YSK01A has some pointers pointing to near the end of the file. Need a way to edit those
            print("Still these pointers: " + hex(previous_text_offset), hex(block.stop))
            if gf.pointers:
                gf.edit_pointers_in_range((previous_text_offset, block.stop), diff)

            block_diff = len(block.blockstring) - len(block.original_blockstring)

            # Ignore size differences in .SCN files
            if filename in LENGTH_SENSITIVE_BLOCKS:
                print(filename, "is length sensitive")
                if block_diff < 0:
                    print("block_diff of", block, "is", block_diff)
                    if filename.endswith('SCN'):
                        PADDING_CHARACTER = b' '
                    else:
                        PADDING_CHARACTER = b'\x00'

                    block.blockstring += (-1)*block_diff*PADDING_CHARACTER
                block_diff = len(block.blockstring) - len(block.original_blockstring)
                assert block_diff == 0, (block_diff, block)

            block.incorporate()

        gf.write(skip_disk=True)

    for filename in ARCHIVES_TO_REINSERT:
        gamefile_path = os.path.join('patched', filename)

        repack(gamefile_path)
        # Gotta repack it first, then initialize the gamefile
        gf = Gamefile(gamefile_path, disk=OriginalBOD, dest_disk=TargetBOD)

        gf.write(path_in_disk='B-DRKNS')