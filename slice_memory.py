start = 0x33780
stop = start + 0x12e9

source = 'memory.bin'
name = 'SHINOBU.SMI'

with open(source, 'rb') as f:
    f.seek(start)
    with open('original/decompressed/%s' % name, 'wb+') as g:
        g.write(f.read(stop - start))

# 5380-6280:
# also 0x8b40 to 0x95e2
# also 0x26d1c - 0x27faa