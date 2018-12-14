"""
    Kuro no Ken reinserter.
"""

import os
from shutil import copyfile
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel, PointerExcel
from rominfo import SRC_DISK, DEST_DISK, FILES, FILES_TO_DUMP, FILES_WITH_POINTERS, FILE_BLOCKS, REAL_FILE_BLOCKS, DUMP_XLS_PATH, POINTER_XLS_PATH, POINTERS_TO_REASSIGN
from extract import repack

FILES_TO_REINSERT = FILES_TO_DUMP
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
        #print(gf.pointers)

        """
        if filename in POINTERS_TO_REASSIGN:
            print("Time to reassign some pointers")
            reassignments = POINTERS_TO_REASSIGN[filename]
            for src, dest in reassignments:
                print("Reassigning", hex(src), hex(dest))
                if src not in gf.pointers or dest not in gf.pointers:
                    print("Skipping this one: %s, %s" % (hex(src), hex(dest)))
                    continue
                assert src in gf.pointers
                assert dest in gf.pointers
                diff = dest - src
                assert dest == src + diff
                for p in gf.pointers[src]:
                    p.edit(diff)
                gf.pointers[dest] += gf.pointers[src]
                gf.pointers.pop(src)
        """

        for block in FILE_BLOCKS[filename]:
            block = Block(gf, block)
            print(block)
            previous_text_offset = block.start
            diff = 0
            #print(repr(block.blockstring))
            for t in Dump.get_translations(block):
                # TODO: Add support for halfwidth kana.
                    # Prepend 85, add 1f if it's a num, sub 2 if it's a char
                if t.en_bytestring != t.jp_bytestring:
                    print(t)
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

                    if filename in FILES_WITH_POINTERS:
                        gf.edit_pointers_in_range((previous_text_offset, t.location), diff)

                    previous_text_offset = t.location

                    this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                    diff += this_diff

            block_diff = len(block.blockstring) - len(block.original_blockstring)
            
            # Ignore size differences in .SCN files
            if filename in REAL_FILE_BLOCKS:
                print(filename, "is in real file blocks")
                if block_diff < 0:
                    print("block_diff is", block_diff)
                    block.blockstring += (-1)*block_diff*b'\x00'
                block_diff = len(block.blockstring) - len(block.original_blockstring)
                assert block_diff == 0, block_diff

            block.incorporate()

        gf.write(skip_disk=True)

    for filename in ARCHIVES_TO_REINSERT:
        gamefile_path = os.path.join('patched', filename)
        gf = Gamefile(gamefile_path, disk=OriginalBOD, dest_disk=TargetBOD)

        for bodfile in FILES:
            if bodfile.name == b'02OLB00A.SCN':
                print(bodfile)


        repack(gamefile_path)
        #print(gamefile_path)
        gf.write(path_in_disk='B-DRKNS')