"""
    Kuro no Ken reinserter.
"""

import os
from shutil import copyfile
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel
from rominfo import SRC_DISK, DEST_DISK, FILES, FILES_TO_REINSERT, FILE_BLOCKS, LENGTH_SENSITIVE_BLOCKS, DUMP_XLS_PATH, POINTER_XLS_PATH, POINTERS_TO_REASSIGN
from fa1 import repack

ARCHIVES_TO_REINSERT = ['A.FA1', 'B.FA1']
Dump = DumpExcel(DUMP_XLS_PATH)
PtrDump = PointerExcel(POINTER_XLS_PATH)

if __name__ == '__main__':
    # Fresh start each reinsertion
    copyfile(SRC_DISK, DEST_DISK)

    OriginalBOD = Disk(SRC_DISK, dump_excel=Dump, pointer_excel=PtrDump)
    TargetBOD = Disk(DEST_DISK)

    for filename in FILES_TO_REINSERT:
        original_path = os.path.join('original', 'decompressed', filename)
        patched_path = os.path.join('patched', filename)
        copyfile(original_path, patched_path)
        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD, pointer_constant=0)
        for p in gf.pointers:
            print(hex(p))


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

        for block in FILE_BLOCKS[filename]:
            block = Block(gf, block)
            print(block)
            previous_text_offset = block.start
            diff = 0
            #print(repr(block.blockstring))
            for t in Dump.get_translations(block, include_blank=True):
                if t.en_bytestring == b'':
                    t.en_bytestring = t.jp_bytestring
                elif t.en_bytestring == b'[BLANK]':
                    t.en_bytestring = b''

                if t.en_bytestring != t.jp_bytestring:
                    # TODO: Add support for halfwidth kana.
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

                    #if j > 1:
                    #    print("%s multiples of this string found" % j)
                    assert loc_in_block == i, (hex(loc_in_block), hex(i))

                    block.blockstring = block.blockstring.replace(t.jp_bytestring, t.en_bytestring, 1)

                if gf.pointers:
                    gf.edit_pointers_in_range((previous_text_offset, t.location), diff)

                previous_text_offset = t.location

                this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                diff += this_diff

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
                assert block_diff == 0, block_diff

            block.incorporate()

        gf.write(skip_disk=True)

    for filename in ARCHIVES_TO_REINSERT:
        gamefile_path = os.path.join('patched', filename)

        for bodfile in FILES:
            if bodfile.name == b'02OLB00A.SCN':
                print(bodfile)


        repack(gamefile_path)
        # Gotta repack it first, then initialize the gamefile
        gf = Gamefile(gamefile_path, disk=OriginalBOD, dest_disk=TargetBOD)
        gf.write(path_in_disk='B-DRKNS')