"""Author a complete AS2 file: main tree, literal alphabet and image bitstream.

`as2.py` codes an image against a *given* tree; `as2table.py` reads and writes
the tables. This ties them together: given target artwork it picks a literal
alphabet that covers the bytes the artwork needs, Huffman-shapes both trees
against the symbols the encoder actually emits, and assembles the file.

The two trees are fitted iteratively, because the code lengths change which
matches the encoder picks, which changes the frequencies.
"""
import heapq

import as2
import as2table as T

LIT_IDX = next(i for i, (o, k) in enumerate(T.FIXED_ACTIONS) if k == 'LITGROUP')
RLE_IDX = next(i for i, (o, k) in enumerate(T.FIXED_ACTIONS) if k == 'RLE')
OFF_IDX = {-o: i for i, (o, k) in enumerate(T.FIXED_ACTIONS) if k == 'COPY'}


def huffman(freqs):
    """{symbol: count} -> {symbol: bit path}; zero counts still get a leaf."""
    h = [(max(c, 1), i, s, None) for i, (s, c) in enumerate(sorted(freqs.items()))]
    heapq.heapify(h)
    nxt = len(h)
    while len(h) > 1:
        a = heapq.heappop(h)
        b = heapq.heappop(h)
        heapq.heappush(h, (a[0] + b[0], nxt, None, (a, b)))
        nxt += 1
    out = {}

    def walk(n, pre):
        if n[3] is None:
            out[n[2]] = pre or '0'
            return
        walk(n[3][0], pre + '0')
        walk(n[3][1], pre + '1')
    walk(h[0], '')
    return out


def literal_tree(byte_freq):
    """Pick a literal tree covering every byte in `byte_freq`.

    A byte needs V1 for its odd bits and V2 for its even bits, so the leaf set
    is just the union of those over the artwork, Huffman-shaped by use.
    """
    vfreq = {}
    for b, f in byte_freq.items():
        v1, v2 = T.v_for_byte(b)
        vfreq[v1] = vfreq.get(v1, 0) + f
        vfreq[v2] = vfreq.get(v2, 0) + f
    return {path: V for V, path in huffman(vfreq).items()}


def codebook(action_path, lit_leaves):
    """-> (lit, off, rle, tree) for as2.encode_row / as2.decode."""
    litpath = action_path[LIT_IDX]
    lit = {}
    for code, b in T.literal_alphabet(lit_leaves, litpath).items():
        if b not in lit or len(code) < len(lit[b]):
            lit[b] = code
    off = {o: action_path[i] for o, i in OFF_IDX.items() if i in action_path}
    rle = action_path[RLE_IDX]
    tree = {c: (as2.LIT, b) for b, c in lit.items()}
    tree.update({c: (as2.OFF, o) for o, c in off.items()})
    tree[rle] = (as2.RLE, 0)
    return lit, off, rle, tree


def author(stream, iters=2, log=print):
    """Fit both trees to `stream` and return (action_path, lit_leaves, enc)."""
    freq = {}
    for b in stream:
        freq[b] = freq.get(b, 0) + 1
    lit_leaves = literal_tree(freq)
    action_path = huffman({i: 1 for i in range(32)})
    if log:
        log('  %d distinct bytes -> %d literal leaves (alphabet %d)'
            % (len(freq), len(lit_leaves), len(lit_leaves) ** 2))
    best = None
    for it in range(iters):
        lit, off, rle, _ = codebook(action_path, lit_leaves)
        missing = [b for b in freq if b not in lit]
        if missing:
            raise ValueError('literal alphabet misses %s'
                             % [hex(x) for x in missing[:6]])
        afreq = {i: 0 for i in range(32)}
        bfreq = {}
        rows = []
        for r in range(len(stream) // as2.ROW):
            ops, _ = as2.encode_row(stream, r * as2.ROW, lit, off, rle)
            rows.append(ops)
            for kind, arg, L in ops:
                if kind == 'L':
                    afreq[LIT_IDX] += 1
                    bfreq[arg] = bfreq.get(arg, 0) + 1
                elif kind == 'R':
                    afreq[RLE_IDX] += 1
                else:
                    afreq[OFF_IDX[arg]] += 1
        bw = as2.BitWriter()
        for ops in rows:
            for kind, arg, L in ops:
                if kind == 'L':
                    bw.bits(lit[arg])
                else:
                    bw.bits(rle if kind == 'R' else off[arg])
                    bw.bits(as2.length_bits(L))
        enc = bw.flush()
        size = len(T.emit_table(action_path)) + len(T.emit_literals(lit_leaves))
        total = 0x28 + (size + len(enc) * 8 + 15) // 16 * 2
        if log:
            log('  pass %d: %d bytes' % (it, total))
        if best is None or total < best[0]:
            best = (total, action_path, lit_leaves, enc)
        action_path = huffman(afreq)
        lit_leaves = literal_tree(bfreq or freq)
    return best[1], best[2], best[3]


def assemble(header, action_path, lit_leaves, enc):
    """header (the file's first 0x28 bytes) + tables + image -> a new AS2 file."""
    bits = T.emit_table(action_path) + T.emit_literals(lit_leaves)
    if len(bits) % 16:
        raise ValueError('tables must end on a word boundary (got %d bits)'
                         % len(bits))
    for i in range(0, len(enc), 2):
        w = int.from_bytes(enc[i:i + 2], 'little')
        bits.extend((w >> k) & 1 for k in range(15, -1, -1))
    packed, _ = T.pack(bits)
    out = bytearray(header[:0x28]) + packed
    out[0x04:0x08] = len(out).to_bytes(4, 'little')     # the header carries the size
    return bytes(out)


def verify(data, expect_stream):
    """Parse an authored file back with the normal reader and decode it."""
    p = T.parse_table(data)
    leaves = T.parse_literals(p['bits'])
    res = T.resolve(p)
    litpath = next(c for c, (k, o) in res.items() if k == 'LITGROUP')
    tree = {c: (as2.LIT, b) for c, b in T.literal_alphabet(leaves, litpath).items()}
    for c, (kind, o) in res.items():
        if kind == 'COPY':
            tree[c] = (as2.OFF, o)
        elif kind == 'RLE':
            tree[c] = (as2.RLE, 0)
    bs = p['bits']            # continues straight into the image bitstream

    def rlen():
        k = 0
        while k < 7 and bs.bit() == 0:
            k += 1
        nb = k + 1
        v = 0
        for _ in range(nb):
            v = (v << 1) | bs.bit()
        return v + ((1 << nb) - 1)

    out = bytearray(bytes(0x2000))
    base = len(out)
    while len(out) - base < len(expect_stream):
        rem = as2.ROW
        while rem > 0:
            c = ''
            while c not in tree:
                c += str(bs.bit())
            kind, arg = tree[c]
            if kind == as2.LIT:
                out.append(arg)
                rem -= 1
            else:
                n = rlen()
                if kind == as2.RLE:
                    out.extend([out[-1]] * n)
                else:
                    src = len(out) - arg
                    for i in range(n):
                        out.append(out[src + i])
                rem -= n
        if rem != 0:
            raise ValueError('row overrun by %d' % -rem)
    return bytes(out[base:]) == expect_stream
