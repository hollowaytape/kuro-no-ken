"""
    Trying to get meaningful info about the files in Kuro no Ken.
"""

class BODFile:
    def __init__(self, source, name, location, length):
        self.source = source
        self.name = name
        self.location = location
        self.length = length

    def get_filestring(self):
        with open(self.source, 'rb') as f:
            f.seek(self.location)
            contents = f.read(self.length)
        return contents

    def __repr__(self):
        return "%s (%s, %s)" % (self.name, self.source, hex(self.location))

if __name__ == "__main__":
    with open('B.FA1', 'rb') as f:
        header = f.read(0xa)
        print(header)
        entries = int.from_bytes(header[0x8:0xa], 'little')

        compressed_end = int.from_bytes(header[0x4:0x7], 'little')
        print(hex(compressed_end))

        f.seek(0x10ec00)   # TODO: There's robably a programmatic way to get this
        table = b''
        buf = b''
        while True:
            buf = f.read(0xc)
            if len(buf) == 0:
                break
            for b in buf:
                print(b)
                print(b ^ 0xFF)
                table += (b ^ 0xFF).to_bytes(1, 'little')
            #table += ~buf

        print(table)

        offset = 0xc
        while table:
            name = table[:8]
            ext = table[8:11]
            data = table[11:20]
            table = table[20:]

            which_length = data[0]
            if which_length == 0:
                file_length = (int(data[7]) << 16) + (int(data[6]) << 8) + int(data[5])
            else:
                file_length = (int(data[3]) << 16) + (int(data[2]) << 8) + int(data[1])
            if offset & 0x1 == 1:
                offset += 1

            filename = name.rstrip(b' ') + b'.' + ext

            this_file = BODFile("B.FA1", filename, offset, file_length)

            #print(name, ext, " ".join([hex(b)[2:].zfill(2) for b in data]), "at", hex(offset), "length is", hex(file_length))
            print(this_file)
            offset += file_length


            # Correct until we hit something with a 01 in the first slot.
            # ADON.BCA 01 82 0d 00 00 a9 15 00 00
            # Location is 0x1ed2. Expected length is 15a9, so next one should have offset (2)347b
                # But the resulting value is 2c54.
                    # This means it's adding the first value instead.
            # Now it went 1ed2, 2c54, 327a, c4a4. The program predicted 3279, c4a2.
                # I'll add a +1 to it now


        # This is for dumping it from the RAM itself, using memory_ed.bin.
        # Less useful than dumping it from the .FA1 archives
        """
        f.seek(0xab4c)
        num = 0
        offset = 0xc
        while True:
            name = f.read(8)
            ext = f.read(3)
            data = f.read(9)

            file_length = (int(data[7]) << 16) + (int(data[6]) << 8) + int(data[5])

            print(num, name, ext, " ".join([hex(b)[2:].zfill(2) for b in data]))
            print(hex(file_length))
            num += 1
            if b'WYARM' in name:
                break
    print(num, hex(num))
    """

    # 10ec00, 104c00