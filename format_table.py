with open('memory_ed.bin', 'rb') as f:
    f.seek(0xab4c)
    num = 0
    while True:
        name = f.read(8)
        ext = f.read(3)
        data = f.read(9)
        print(num, name, ext, " ".join([hex(b)[2:].zfill(2) for b in data]))
        num += 1
        if b'WYARM' in name:
            break
print(num, hex(num))