"""
    Dump the files from the FA1 filesystem of BOD.
"""
import os
from rominfo import BODFile, ARCHIVES, FILES, FILES_TO_REINSERT, BSD_FILES_WITH_TEXT
from compress import compress as compress_data
from decompress import decompress as decompress_data

def getSize(filename):
    st = os.stat(filename)
    return st.st_size

def invert(bs):
    result = b''
    for b in bs:
        result += (b ^ 0xFF).to_bytes(1, 'little')
    return result


def unpack(archive, file_dir=b'original'):
    #print(archive)
    files_to_extract = []
    with open(os.path.join(file_dir, archive), 'rb') as f:
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

            #print(name, ext, " ".join([hex(b)[2:].zfill(2) for b in data]), "at", hex(offset), "length is", hex(compressed_length))
            #print(this_file)
            offset += compressed_length

    for f in files_to_extract:
        filestring = f.get_filestring(path=file_dir)
        with open(os.path.join(file_dir, f.name), 'wb+') as g:
            #if f.name == b'BD_FLAG1.DAT':
                #print(filestring)
                #print(file_dir)
            g.write(filestring)


def repack(archive, also_reinserted=()):
    """Rebuild `archive` from patched/. Files in FILES_TO_REINSERT, BSD_FILES_WITH_TEXT or
    `also_reinserted` are read from patched/ decompressed and recompressed; the rest keep
    their original bytes."""
    print("Calling repack on", archive)
    just_archive = bytes(archive.split('\\')[-1], 'ascii')

    # Original archive size for overflow validation
    orig_archive_path = os.path.join(b'original', just_archive)
    orig_archive_size = os.path.getsize(orig_archive_path)

    with open(archive, 'wb+') as f:
        archive_files = []
        file_buffers = []  # pre-read (and possibly compressed) file contents
        compressed_files_end = 0xc

        for bodfile in FILES:
            if bodfile.source != just_archive:
                continue

            with open(b'patched/%s' % bodfile.name, 'rb') as g:
                buf = g.read()

            filename = bodfile.name.decode('ascii')
            was_compressed = bodfile.compressed_length < bodfile.decompressed_length
            is_reinserted = (filename in FILES_TO_REINSERT or filename in BSD_FILES_WITH_TEXT
                             or filename in also_reinserted)

            if is_reinserted and was_compressed:
                with open(b'original/%s' % bodfile.name, 'rb') as g:
                    original_compressed = g.read()
                original_stream = decompress_data(original_compressed)

                # The compressed stream encodes all bytes of BSD/SMI files, but the game
                # overwrites the first 6 in RAM (b4 0b ...), so memory dumps show runtime
                # values there. Always write the stream's own header back.
                ext = filename.rsplit('.', 1)[-1].upper()
                if ext in ('BSD', 'SMI'):
                    buf = original_stream[:6] + buf[6:]

                if buf == original_stream:
                    # Unchanged - keep the original compressed bytes
                    buf = original_compressed
                    bodfile._repack_is_compressed = True
                    bodfile.decompressed_length = len(original_stream)
                    compressed = None
                else:
                    bodfile.decompressed_length = len(buf)
                    compressed = compress_data(buf)

                if compressed is None:
                    pass
                elif len(compressed) < len(buf):
                    buf = compressed
                    bodfile._repack_is_compressed = True
                else:
                    # Compression didn't help; store uncompressed
                    bodfile._repack_is_compressed = False
                    print('  %s: compression inflated, storing uncompressed' % filename)
            elif is_reinserted:
                # Uncompressed file (e.g. DAT files) — store as-is
                bodfile.decompressed_length = len(buf)
                bodfile._repack_is_compressed = False
            else:
                # Not reinserted — keep original (already compressed or not)
                bodfile._repack_is_compressed = was_compressed

            if len(buf) != bodfile.compressed_length:
                print('  %s: %s -> %s' % (filename,
                    hex(bodfile.compressed_length), hex(len(buf))))
            bodfile.compressed_length = len(buf)

            compressed_files_end += bodfile.compressed_length
            if compressed_files_end & 0x1 == 1:
                compressed_files_end += 1

            archive_files.append(bodfile)
            file_buffers.append(buf)

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
        for bodfile, buf in zip(archive_files, file_buffers):
            f.write(buf)
            cursor += len(buf)

            if cursor & 1 == 1:
                f.write(b'\x00')
                cursor += 1

        # Pad so the table begins at the next multiple of 0x400
        while cursor % 0x400 != 0:
            f.write(b'\x00')
            cursor += 1

        # Write inverted file table
        table = b''
        for bodfile in archive_files:
            table += bodfile.name_no_ext + (8 - len(bodfile.name_no_ext)) * b' '
            table += bodfile.ext
            if bodfile._repack_is_compressed:
                table += b'\x01'
            else:
                table += b'\x00'
            table += bodfile.compressed_length.to_bytes(4, 'little')
            table += bodfile.decompressed_length.to_bytes(4, 'little')

        table = invert(table)
        f.write(table)

        final_size = f.tell()

    # Overflow validation
    if final_size > orig_archive_size:
        print('WARNING: %s overflows! %s -> %s (+%d bytes)' % (
            just_archive.decode(), hex(orig_archive_size),
            hex(final_size), final_size - orig_archive_size))
    else:
        slack = orig_archive_size - final_size
        print('  %s: %s bytes (slack: %d bytes)' % (
            just_archive.decode(), hex(final_size), slack))


if __name__ == "__main__":
    #files_to_extract = []
    for archive in ARCHIVES:
        unpack(archive)
    unpack(b'A.FA1')
    #repack('patched\\A.FA1')
    #repack('patched\\B.FA1')