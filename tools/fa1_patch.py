"""Replace one member of an FA1 archive, byte-for-byte faithful otherwise.

`fa1.repack` rebuilds an archive from the whole `patched/` tree and the
translation manifest. For art work we want the opposite: take the original
archive and swap a single file, leaving every other byte exactly as it was.

The layout (see `fa1.py`):

    0x00  "FA1\\0"
    0x04  3 bytes  end of the file data
    0x07  0x00
    0x08  uint16   entry count
    0x0a  uint8    archive index
    0x0b  0x80
    0x0c  file data, each entry starting on an even offset
          zero padding up to the next multiple of 0x400
          the entry table, 20 bytes per entry, every byte inverted

A member can therefore grow by up to the size of that padding without the
archive changing size at all, which keeps the disk image's FAT untouched.
"""
import os

ENTRY = 20
TABLE_ALIGN = 0x400


def parse(raw):
    """-> (header, [ {name, ext, compressed, offset, clen, dlen} ], table_start)"""
    end = int.from_bytes(raw[0x4:0x7], 'little')
    cursor = end
    while raw[cursor] == 0:
        cursor += 1
    table = bytes(b ^ 0xFF for b in raw[cursor:])
    entries, offset = [], 0xc
    while table:
        name, ext, data, table = table[:8], table[8:11], table[11:20], table[20:]
        clen = (data[3] << 16) + (data[2] << 8) + data[1]
        dlen = (data[7] << 16) + (data[6] << 8) + data[5]
        if offset & 1:
            offset += 1
        entries.append({
            'name': name, 'ext': ext, 'compressed': data[0] == 1,
            'offset': offset, 'clen': clen, 'dlen': dlen,
            'filename': (name.rstrip(b' ') + b'.' + ext).decode('ascii', 'replace'),
        })
        offset += clen
    return raw[:0xc], entries, cursor


def build(raw, entries, payloads):
    """Rebuild an archive. `payloads[i]` is entry i's bytes."""
    out = bytearray()
    body = bytearray()
    cursor = 0xc
    for e, buf in zip(entries, payloads):
        if cursor & 1:
            body += b'\x00'
            cursor += 1
        body += buf
        cursor += len(buf)
        e = dict(e)
    data_end = cursor
    pad = (-cursor) % TABLE_ALIGN
    table = bytearray()
    for e, buf in zip(entries, payloads):
        nm = e['name'].rstrip(b' ')
        table += nm + b' ' * (8 - len(nm))
        table += e['ext']
        table += b'\x01' if e['compressed'] else b'\x00'
        table += len(buf).to_bytes(4, 'little')
        table += e['dlen'].to_bytes(4, 'little')
    out += b'FA1\x00'
    out += data_end.to_bytes(3, 'little')
    out += b'\x00'
    out += len(entries).to_bytes(2, 'little')
    out += raw[0x0a:0x0b]
    out += raw[0x0b:0x0c]
    out += body
    out += b'\x00' * pad
    out += bytes(b ^ 0xFF for b in table)
    return bytes(out)


def replace(raw, filename, new_bytes, compressed=None, dlen=None):
    """Return a rebuilt archive with `filename` swapped for `new_bytes`.

    `new_bytes` is what gets stored. For a compressed member pass the
    decompressed length as `dlen`; for a stored one it is len(new_bytes).
    """
    _, entries, _ = parse(raw)
    payloads, hit = [], False
    for e in entries:
        if e['filename'].upper() == filename.upper():
            payloads.append(new_bytes)
            if compressed is not None:
                e['compressed'] = compressed
            if dlen is not None:
                e['dlen'] = dlen
            elif not e['compressed']:
                e['dlen'] = len(new_bytes)
            hit = True
        else:
            payloads.append(raw[e['offset']:e['offset'] + e['clen']])
    if not hit:
        raise KeyError(filename)
    return build(raw, entries, payloads)


def identity(raw):
    """Rebuild with no change - must reproduce `raw` exactly."""
    _, entries, _ = parse(raw)
    return build(raw, entries,
                 [raw[e['offset']:e['offset'] + e['clen']] for e in entries])


def headroom(raw):
    """How many bytes the archive's data may grow before it gets bigger."""
    _, entries, table_start = parse(raw)
    end = int.from_bytes(raw[0x4:0x7], 'little')
    return table_start - end


# ---------------------------------------------------------------- disk image
def patch_disk(hdi_path, out_path, archive_name, new_archive, original_archive):
    """Write a same-size archive into a copy of the disk image, in place."""
    import shutil
    shutil.copyfile(hdi_path, out_path)
    with open(out_path, 'rb') as fh:
        img = bytearray(fh.read())
    if len(new_archive) != len(original_archive):
        raise ValueError('archive changed size (%d -> %d); the FAT would need '
                         'updating' % (len(original_archive), len(new_archive)))
    probe = original_archive[:4096]
    at = img.find(probe)
    if at < 0:
        raise ValueError('%s not found in the disk image' % archive_name)
    if bytes(img[at:at + len(original_archive)]) != original_archive:
        raise ValueError('%s is not stored contiguously' % archive_name)
    img[at:at + len(new_archive)] = new_archive
    with open(out_path, 'wb') as fh:
        fh.write(bytes(img))
    return at


if __name__ == '__main__':
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
    raw = open(os.path.join(HERE, 'original', 'A.FA1'), 'rb').read()
    print('A.FA1 %d bytes, headroom %d bytes' % (len(raw), headroom(raw)))
    same = identity(raw)
    print('identity rebuild reproduces the original exactly:', same == raw)
