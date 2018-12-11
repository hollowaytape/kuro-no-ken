from shutil import copyfile

memory_path = '../romtools/np2debug/memory.bin'

copyfile(memory_path, './memory.bin')