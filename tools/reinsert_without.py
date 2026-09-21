"""Run reinsert.py with some files left untranslated (original bytes).

Usage: python tools/reinsert_without.py 02OLB01.SCN [more files...]

Resets patched/ disk image from original/ first, since reinsert.py builds
incrementally on whatever is already in patched/.
"""
import runpy
import shutil
import sys

sys.path.insert(0, '.')
import rominfo

for name in sys.argv[1:]:
    while name in rominfo.FILES_TO_REINSERT:
        rominfo.FILES_TO_REINSERT.remove(name)
    if name in rominfo.BSD_FILES_WITH_TEXT:
        rominfo.BSD_FILES_WITH_TEXT.remove(name)
    print('excluding', name)

# Keep the player's saves: copy them out of the current patched disk before it's
# reset (reinsert.py would otherwise copy them from the fresh, save-less image).
import os
from romtools.disk import Disk
from fa1 import unpack
Disk(rominfo.DEST_DISK).extract('A.FA1', path_in_disk="B-DRKNS", dest_path="patched")
unpack(b'A.FA1', file_dir=b'patched')
for flag in ('0', '1', '2', '3', '4', '5', '6', '7', 'H'):
    shutil.copyfile(os.path.join('patched', f'BD_FLAG{flag}.DAT'), os.path.join('original', f'BD_FLAG{flag}.DAT'))
os.environ['KURO_SAVES_ALREADY_COPIED'] = '1'
shutil.copyfile(rominfo.DEST_DISK, rominfo.DEST_DISK + '.before_rebuild')   # just in case

shutil.copyfile(rominfo.SRC_DISK, rominfo.DEST_DISK)
runpy.run_path('reinsert.py', run_name='__main__')
