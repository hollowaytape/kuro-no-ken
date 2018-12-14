"""
    Dump the files from the FA1 filesystem of BOD.
"""
import os
from rominfo import BODFile, ARCHIVES, FILES


def getSize(filename):
    st = os.stat(filename)
    return st.st_size

def invert(bs):
    result = b''
    for b in bs:
        result += (b ^ 0xFF).to_bytes(1, 'little')
    return result


def unpack(archive):
    #print(archive)
    with open(b'original/%s' % archive, 'rb') as f:
        header = f.read(0xa)
        entries = int.from_bytes(header[0x8:0xa], 'little')
        compressed_end = int.from_bytes(header[0x4:0x7], 'little')

        # Look for the table, it's after a bunch of 00 bytes
        cursor = compressed_end
        f.seek(compressed_end)
        buf = f.read(1)
        #print(buf, buf == b'\x00')
        while buf == b'\x00':
            buf = f.read(1)
            cursor += 1
            #print(hex(cursor))
        f.seek(cursor)

        # Invert the table
        table = b''
        buf = b''
        while True:
            buf = f.read(0xc)
            if len(buf) == 0:
                break
            for b in buf:
                #print(b)
                #print(b ^ 0xFF)
                table += (b ^ 0xFF).to_bytes(1, 'little')
            #table += ~buf

        #print(table)

        offset = 0xc
        while table:
            name = table[:8]
            ext = table[8:11]
            data = table[11:20]
            table = table[20:]

            is_compressed = data[0] == 1

            decompressed_length = (int(data[7]) << 16) + (int(data[6]) << 8) + int(data[5])
            compressed_length = (int(data[3]) << 16) + (int(data[2]) << 8) + int(data[1])

            # adc bx, +0 (carry the one)
            if offset & 0x1 == 1:
                offset += 1

            filename = name.rstrip(b' ') + b'.' + ext

            this_file = BODFile(archive, filename, offset, compressed_length, decompressed_length)
            files_to_extract.append(this_file)

            print(name, ext, " ".join([hex(b)[2:].zfill(2) for b in data]), "at", hex(offset), "length is", hex(compressed_length))
            #print(this_file)
            offset += compressed_length

    for f in files_to_extract:
        filestring = f.get_filestring()
        with open(b'original/%b' % f.name, 'wb+') as g:
            g.write(filestring)


def repack(archive):
    print("Calling repack on", archive)
    #print(archive)
    just_archive = bytes(archive.split('\\')[-1], 'ascii')
    #print(just_archive)
    with open(archive, 'wb+') as f:
        archive_files = []
        compressed_files_end = 0xc

        # Collect info on which files are in this, and how long they are
        for bodfile in FILES:
            if bodfile.source == just_archive:
                #print(bodfile)

                with open(b'patched/%s' % bodfile.name, 'rb') as g:
                    buf = g.read()
                    #assert len(buf) == bodfile.compressed_length
                    if len(buf) != bodfile.compressed_length:
                        print('%s was changed, its length is now %s' % (bodfile.name, hex(len(buf))))
                    bodfile.compressed_length = len(buf)

                compressed_files_end += bodfile.compressed_length
                #print(hex(compressed_files_end))
                #print(hex(bodfile.location + bodfile.compressed_length))
                #print(bodfile)
                archive_files.append(bodfile)
                #assert compressed_files_end == bodfile.location + bodfile.compressed_length

                # Pad so each file begins at a word boundary
                if compressed_files_end & 0x1 == 1:
                    compressed_files_end += 1


        # Write FA1 header
        f.write(b'FA1')
        f.write(b'\x00')
        f.write(compressed_files_end.to_bytes(3, 'little'))
        f.write(b'\x00')
        f.write(len(archive_files).to_bytes(2, 'little'))
        f.write(ARCHIVES.index(bytes(just_archive)).to_bytes(1, 'little'))
        f.write(b'\x80')

        # Write file contents
        cursor = 0xc
        for bodfile in archive_files:
            #print(bodfile)
            #f.write(bodfile.get_filestring(b'patched'))
            #cursor += len(bodfile.get_filestring(b'patched'))
            with open(b'patched/%s' % bodfile.name, 'rb') as g:
                buf = g.read()
                #print(buf)
                f.write(buf)
                cursor += len(buf)
            #cursor += getSize(b'patched/%s' % bodfile.name)

            #print(hex(cursor))
            if cursor & 1 == 1:
                f.write(b'\x00')
                cursor += 1

        # what do 10ec00, 104c00, 109800, 10d800, 115c00 have in common?
            # Multiples of 0x400
        # Pad so the table begins at the next multiple of 0x400
        while cursor % 0x400 != 0:
            f.write(b'\x00')
            cursor += 1
        #print(hex(cursor))

        # Write file table to a normal string first
        table = b''
        for bodfile in archive_files:
            #print(bodfile, bodfile.is_compressed())
            table += bodfile.name_no_ext + (8 - len(bodfile.name_no_ext)) * b' '
            table += bodfile.ext
            if bodfile.is_compressed():
                table += b'\x01'
            else:
                table += b'\x00'
            table += bodfile.compressed_length.to_bytes(4, 'little')
            table += bodfile.decompressed_length.to_bytes(4, 'little')


        #print(table)

        # Invert the table and write it
        table = invert(table)
        f.write(table)


if __name__ == "__main__":
    files_to_extract = []
    #for archive in ARCHIVES:
    #    unpack(archive)
    #unpack(b'A.FA1')
    repack('patched\\A.FA1')
    repack('patched\\B.FA1')