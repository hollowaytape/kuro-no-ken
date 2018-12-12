"""
    Kuro no Ken reinserter.
"""

import os
from shutil import copyfile
from romtools.disk import Disk, Gamefile, Block
from romtools.dump import DumpExcel
from rominfo import SRC_DISK, DEST_DISK, FILES, FILES_TO_DUMP, FILE_BLOCKS, DUMP_XLS_PATH
from extract import repack

FILES_TO_REINSERT = FILES_TO_DUMP
ARCHIVES_TO_REINSERT = ['A.FA1', 'B.FA1']
Dump = DumpExcel(DUMP_XLS_PATH)

if __name__ == '__main__':
    # Fresh start each reinsertion
    copyfile(SRC_DISK, DEST_DISK)

    OriginalBOD = Disk(SRC_DISK)
    TargetBOD = Disk(DEST_DISK)

    for filename in FILES_TO_REINSERT:
        original_path = os.path.join('original', 'decompressed', filename)
        patched_path = os.path.join('patched', filename)
        copyfile(original_path, patched_path)
        gf = Gamefile(patched_path, disk=OriginalBOD, dest_disk=TargetBOD)

        for block in FILE_BLOCKS[filename]:
            block = Block(gf, block)
            print(block)
            previous_text_offset = block.start
            diff = 0
            #print(repr(block.blockstring))
            for t in Dump.get_translations(block):
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

                    #gamefile.edit_pointers_in_range((previous_text_offset, t.location), diff)
                    previous_text_offset = t.location

                    this_diff = len(t.en_bytestring) - len(t.jp_bytestring)
                    diff += this_diff

            block_diff = len(block.blockstring) - len(block.original_blockstring)
            
            # Ignore size differences in .SCN files
            if not filename.endswith('.SCN'):
                if block_diff < 0:
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