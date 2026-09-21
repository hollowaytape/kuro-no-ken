"""Kuro no Ken AS2 codec: decoder + encoder.

Format (established by reading the game's own decompressor under np2core):

    0x00  "AS2\\0"
    0x04  uint32  file size
    0x08  uint32  ?           (0x5000 for full-screen scenes)
    0x0C  uint16  row stride in bytes (0x190 = 400 for 640x400)
    0x0E  uint16  ?
    0x10  24 bytes palette, two 4-bit components per byte, high nibble first,
          16 entries of (B, R, G)
    0x28  a bit-packed table that the loader expands into an unrolled
          Huffman decoder (NOT decoded here - see `tree` below)
    ...   the image bitstream, MSB-first over 16-bit little-endian words

The bitstream codes three symbol kinds: LIT (emit a byte), COPY (copy `n`
bytes from `offset` back) and RLE (repeat the previous byte `n` times).
Lengths use an Elias-gamma code: k leading zeros, then k+1 bits, value
+ (2**(k+1) - 1), for k = 0..7.

The prefix code itself is **per file** - the loader generates the decoder
code from the table at 0x28. That table's format is not decoded; instead a
file's tree is recovered by tracing the game's decoder once (see
`extract_tree.py`) and is then reused for re-encoding, which works because
the useful symbol set is stable for a given kind of artwork.

Output is column-major: the stream is 80 columns x 4 "planes" x `stride`
bytes, and each group of 4 source bytes is bit-interleaved into one byte of
each of the four PC-98 VRAM planes (see `transpose`/`untranspose`).
"""
import os

LIT, OFF, RLE = 0, 1, 2
ROW = 0x190
WINDOW = 0x1900        # the decoder's ring buffer


# --------------------------------------------------------------- bitstream
class BitReader:
    def __init__(self, data, pos):
        self.d, self.p, self.buf, self.n = data, pos, 0, 0

    def bit(self):
        if self.n == 0:
            if self.p + 2 > len(self.d):
                raise EOFError
            self.buf = int.from_bytes(self.d[self.p:self.p + 2], 'little')
            self.p += 2
            self.n = 16
        self.n -= 1
        b = (self.buf >> 15) & 1
        self.buf = (self.buf << 1) & 0xffff
        return b


class BitWriter:
    def __init__(self):
        self.words, self.buf, self.n = bytearray(), 0, 0

    def bit(self, b):
        self.buf = ((self.buf << 1) | b) & 0xffff
        self.n += 1
        if self.n == 16:
            self.words += self.buf.to_bytes(2, 'little')
            self.buf, self.n = 0, 0

    def bits(self, s):
        for c in s:
            self.bit(1 if c == '1' else 0)

    def flush(self):
        while self.n:
            self.bit(0)
        return bytes(self.words)


def read_length(br):
    k = 0
    while k < 7 and br.bit() == 0:
        k += 1
    nb = k + 1
    v = 0
    for _ in range(nb):
        v = (v << 1) | br.bit()
    return v + ((1 << nb) - 1)


def length_bits(n):
    """Inverse of read_length: the bit string encoding length n (or None)."""
    for k in range(8):
        nb = k + 1
        base = (1 << nb) - 1
        if base <= n < base + (1 << nb):
            prefix = '0' * k + '1' if k < 7 else '0' * 7
            return prefix + format(n - base, '0%db' % nb)
    return None


# ------------------------------------------------------------------ decode
def decode(data, start, total, tree, prefix=b'', row=ROW):
    br = BitReader(data, start)
    out = bytearray(prefix)
    base = len(out)
    while len(out) - base < total:
        remaining = row
        while remaining > 0:
            bits = ''
            while bits not in tree:
                bits += str(br.bit())
                if len(bits) > 24:
                    raise ValueError('bad code at %d' % (len(out) - base))
            kind, arg = tree[bits]
            if kind == LIT:
                out.append(arg)
                remaining -= 1
            else:
                n = read_length(br)
                if kind == RLE:
                    out.extend([out[-1]] * n)
                else:
                    src = len(out) - arg
                    if src < 0:
                        raise ValueError('offset before start')
                    for i in range(n):
                        out.append(out[src + i])
                remaining -= n
        if remaining != 0:
            raise ValueError('row overrun by %d' % -remaining)
    return bytes(out[base:]), br.p


# ------------------------------------------------------------------ encode
def build_codebook(tree):
    lit, off, rle = {}, {}, None
    for bits, (kind, arg) in tree.items():
        if kind == LIT:
            if arg not in lit or len(bits) < len(lit[arg]):
                lit[arg] = bits
        elif kind == OFF:
            if arg not in off or len(bits) < len(off[arg]):
                off[arg] = bits
        else:
            if rle is None or len(bits) < len(rle):
                rle = bits
    return lit, off, rle


def _cand_lengths(n):
    """Lengths worth trying for a match of max length n: the longest match and
    each length-code boundary below it (cost only changes at the boundaries)."""
    out = [n]
    for k in range(8):
        b = (1 << (k + 1)) - 1
        if 1 <= b <= n:
            out.append(b)
        top = b + (1 << (k + 1)) - 1
        if 1 <= top < n:
            out.append(top)
    return sorted(set(out))


def encode_row(data, pos, lit, off, rle, row=ROW):
    """Near-optimal (min-bits) encoding of data[pos:pos+row] as a symbol list."""
    INF = float('inf')
    cost = [INF] * (row + 1)
    choice = [None] * (row + 1)
    cost[row] = 0
    maxlen = 510
    offs = [(o, len(bits)) for o, bits in off.items() if o <= WINDOW]
    lb_rle = len(rle) if rle is not None else None
    for i in range(row - 1, -1, -1):
        p = pos + i
        best, bestc = INF, None
        b = data[p]
        cb = lit.get(b)
        if cb is not None:
            c = len(cb) + cost[i + 1]
            if c < best:
                best, bestc = c, ('L', b, 1)
        if lb_rle is not None and p > 0 and data[p - 1] == b:
            n = 0
            lim = min(maxlen, row - i)
            while n < lim and data[p + n] == b:
                n += 1
            for L in _cand_lengths(n):
                lbs = length_bits(L)
                if lbs is None:
                    continue
                c = lb_rle + len(lbs) + cost[i + L]
                if c < best:
                    best, bestc = c, ('R', 0, L)
        for o, lo in offs:
            if o > p:
                continue
            n = 0
            lim = min(maxlen, row - i)
            q = p - o
            while n < lim and data[p + n] == data[q + n]:
                n += 1
            if not n:
                continue
            for L in _cand_lengths(n):
                lbs = length_bits(L)
                if lbs is None:
                    continue
                c = lo + len(lbs) + cost[i + L]
                if c < best:
                    best, bestc = c, ('C', o, L)
        cost[i], choice[i] = best, bestc
    if cost[0] == INF:
        raise ValueError('cannot encode row at %d' % pos)
    ops, i = [], 0
    while i < row:
        ops.append(choice[i])
        i += choice[i][2]
    return ops, cost[0]


def encode(data, tree, row=ROW, progress=None):
    lit, off, rle = build_codebook(tree)
    bw = BitWriter()
    for r in range(len(data) // row):
        ops, _ = encode_row(data, r * row, lit, off, rle, row)
        for kind, arg, L in ops:
            if kind == 'L':
                bw.bits(lit[arg])
            else:
                bw.bits(rle if kind == 'R' else off[arg])
                bw.bits(length_bits(L))
        if progress and r % 40 == 0:
            progress(r, len(data) // row)
    return bw.flush()


# --------------------------------------------------- VRAM plane transpose
def _r8(v, n):
    v &= 0xff
    return ((v << n) | (v >> (8 - n))) & 0xff


def _r16(v, n):
    v &= 0xffff
    return ((v << n) | (v >> (16 - n))) & 0xffff


def transpose(A, B, C, D):
    """4 source bytes -> one byte for each VRAM plane (B, R, G, I)."""
    al = _r8(A, 2); ah = B
    ax = _r16((ah << 8) | al, 2); al = ax & 0xff; ah = (ax >> 8) & 0xff
    ah = _r8(ah, 2); bl = ah; ah = C; bh = D
    ax = _r16((ah << 8) | al, 2); al = ax & 0xff; ah = (ax >> 8) & 0xff
    bl, al = al, bl
    ax = _r16((ah << 8) | al, 2); al = ax & 0xff; ah = (ax >> 8) & 0xff
    ah = _r8(ah, 2)
    bx = _r16((bh << 8) | bl, 2); bl = bx & 0xff; bh = (bx >> 8) & 0xff
    I = bl; bl = al
    bx = _r16((bh << 8) | bl, 2); bl = bx & 0xff; bh = (bx >> 8) & 0xff
    G = bl; bl = ah
    bx = _r16((bh << 8) | bl, 2); bl = bx & 0xff; bh = (bx >> 8) & 0xff
    bh = _r8(bh, 2)
    return bh, bl, G, I


def _perm():
    p = {}
    for i in range(4):
        for b in range(8):
            v = [0, 0, 0, 0]
            v[i] = 1 << b
            out = transpose(*v)
            hit = [(j, k) for j in range(4) for k in range(8) if (out[j] >> k) & 1]
            assert len(hit) == 1
            p[(i, b)] = hit[0]
    return p


PERM = _perm()
IPERM = {v: k for k, v in PERM.items()}


def untranspose(Bp, Rp, Gp, Ip):
    """One byte from each VRAM plane -> the 4 source bytes."""
    s = [0, 0, 0, 0]
    for j, val in enumerate((Bp, Rp, Gp, Ip)):
        for k in range(8):
            if (val >> k) & 1:
                i, b = IPERM[(j, k)]
                s[i] |= 1 << b
    return s


def planes_to_stream(planes, cols=80, rows=400, row=ROW):
    """planes: 4 arrays of shape (rows, cols) -> the decoder's byte stream."""
    out = bytearray()
    for col in range(cols):
        blk = [bytearray(row) for _ in range(4)]
        for y in range(rows):
            s = untranspose(int(planes[0][y][col]), int(planes[1][y][col]),
                            int(planes[2][y][col]), int(planes[3][y][col]))
            for i in range(4):
                blk[i][y] = s[i]
        for i in range(4):
            out += blk[i]
    return bytes(out)


def stream_to_planes(data, cols=80, rows=400, row=ROW):
    import numpy as np
    pl = [np.zeros((rows, cols), np.uint8) for _ in range(4)]
    for col in range(cols):
        blk = data[col * 4 * row:(col + 1) * 4 * row]
        for y in range(rows):
            v = transpose(blk[y], blk[row + y], blk[2 * row + y], blk[3 * row + y])
            for p in range(4):
                pl[p][y, col] = v[p]
    return pl
