"""
    Dumps a file from a memory dump with the given name and start location.
"""

from rominfo import FILES

source = '../romtools/np2debug/memory.bin'

if __name__ == "__main__":
    # Change these
    name = b'06BLK03O.SCN'
    start = 0x26d00

    for bodfile in FILES:
        if bodfile.name == name:
            print(bodfile.name)
            file_length = bodfile.decompressed_length

    stop = start + file_length

    name = name.decode('ascii')

    with open(source, 'rb') as f:
        f.seek(start)
        with open('original/decompressed/%s' % name, 'wb+') as g:
            g.write(f.read(stop - start))
