"""
    Kuro no Ken reinserter.
"""

import os
from shutil import copyfile
from romtools.disk import Disk, Gamefile
from rominfo import SRC_DISK, DEST_DISK, FILES
from extract import repack

FILES_TO_REINSERT = ['B.FA1']

if __name__ == '__main__':
    # Fresh start each reinsertion
    copyfile(SRC_DISK, DEST_DISK)

    OriginalBOD = Disk(SRC_DISK)
    TargetBOD = Disk(DEST_DISK)

    for filename in FILES_TO_REINSERT:
        gamefile_path = os.path.join('patched', filename)
        gf = Gamefile(gamefile_path, disk=OriginalBOD, dest_disk=TargetBOD)

        for bodfile in FILES:
            if bodfile.name == b'02OLB00A.SCN':
                print(bodfile)


        repack(gamefile_path)
        gf.write(path_in_disk='B-DRKNS')