"""Parse an AS2 file's code table - the bits between the palette and the image.

Recovered by tracing the game's tree generator (entry 0x1469a) under np2core.

    count-1        5 bits
    action map     count x 5 bits   (permutation into the fixed action table)
    R              5 bits           total internal nodes; 0 => the whole tree
                                    is a single leaf
    tree           pre-order:
        node():  N = read5()                 # internal nodes in the LEFT subtree
                 left  = node() if N else leaf()
                 M = read5()                 # internal nodes in the RIGHT subtree
                 right = node() if M else leaf()
        leaf():  sym = read5()               # index into the action map

N and M are redundant with the subtree itself; the generator uses them to
compute the forward branch displacement (33*N + 23 bytes) without a second
pass, since each internal node costs 26 bytes of generated code and each leaf
costs 7.

The 32 actions are **fixed in the executable** (ds:0x0de8, 4 bytes each:
signed offset, then the handler address). Only which slot each leaf gets is
per-file.
"""

# ds:0x0de8, dumped from the running game. (offset, handler)
#   handler 0x18c0 = copy, with the ring-wrap check (large offsets)
#   handler 0x18c6 = copy, no wrap check (small offsets)
#   handler 0x18f0 = RLE (repeat previous byte)
#   handler 0x1432 = literal group (expands into its own sub-tree)
FIXED_ACTIONS = [
    (0,     'LITGROUP'), (-400,  'COPY'), (-800,  'COPY'), (-1200, 'COPY'),
    (-1600, 'COPY'),     (-3200, 'COPY'), (0,     'RLE'),  (-401,  'COPY'),
    (-399,  'COPY'),     (-2,    'COPY'), (-402,  'COPY'), (-802,  'COPY'),
    (-1602, 'COPY'),     (-398,  'COPY'), (-798,  'COPY'), (-1598, 'COPY'),
    (-4,    'COPY'),     (-804,  'COPY'), (-1604, 'COPY'), (-796,  'COPY'),
    (-1596, 'COPY'),     (-8,    'COPY'), (-808,  'COPY'), (-1608, 'COPY'),
    (-792,  'COPY'),     (-1592, 'COPY'), (-16,   'COPY'), (-801,  'COPY'),
    (-799,  'COPY'),     (-3,    'COPY'), (-403,  'COPY'), (-397,  'COPY'),
]


class Bits:
    def __init__(self, data, pos):
        self.d, self.p, self.buf, self.n = data, pos, 0, 0

    def bit(self):
        if self.n == 0:
            self.buf = int.from_bytes(self.d[self.p:self.p + 2], 'little')
            self.p += 2
            self.n = 16
        self.n -= 1
        b = (self.buf >> 15) & 1
        self.buf = (self.buf << 1) & 0xffff
        return b

    def read(self, k):
        v = 0
        for _ in range(k):
            v = (v << 1) | self.bit()
        return v

    def pos(self):
        """(byte offset of the next word, bits already consumed from it)."""
        return self.p, 16 - self.n


def parse_table(data, start=0x28):
    bs = Bits(data, start)
    count = bs.read(5) + 1
    amap = [bs.read(5) for _ in range(count)]
    total_internal = bs.read(5)

    codes = {}

    def leaf(path):
        sym = bs.read(5)
        codes[path] = sym

    def node(path):
        n = bs.read(5)
        (node if n else leaf)(path + '0')
        m = bs.read(5)
        (node if m else leaf)(path + '1')

    if total_internal == 0:
        leaf('')
    else:
        node('')
    return {
        'count': count,
        'amap': amap,
        'internal': total_internal,
        'codes': codes,        # bit path -> symbol index (into amap)
        'end': bs.pos(),
        'bits': bs,
    }


def resolve(parsed):
    """bit path -> (kind, offset) using the action map and the fixed table."""
    out = {}
    for path, sym in parsed['codes'].items():
        action = parsed['amap'][sym]
        off, kind = FIXED_ACTIONS[action]
        out[path] = (kind, -off if off else 0)
    return out


# ---------------------------------------------------------------- writing
import heapq


def huffman(freqs):
    """freqs: {symbol: count} for exactly 32 symbols -> {symbol: bit path}."""
    h = [(max(c, 1), i, s, None) for i, (s, c) in enumerate(sorted(freqs.items()))]
    heapq.heapify(h)
    nxt = len(h)
    while len(h) > 1:
        a = heapq.heappop(h); b = heapq.heappop(h)
        heapq.heappush(h, (a[0] + b[0], nxt, None, (a, b)))
        nxt += 1
    paths = {}

    def walk(node, pre):
        w, _, sym, kids = node
        if kids is None:
            paths[sym] = pre or '0'
            return
        walk(kids[0], pre + '0')
        walk(kids[1], pre + '1')
    walk(h[0], '')
    return paths


def emit_table(action_path, count=32):
    """Serialise a main tree (paths per action index) to a bit list."""
    paths = {p: a for a, p in action_path.items()}
    allp = set(paths)

    def internal(prefix):
        if prefix in allp:
            return 0
        return 1 + internal(prefix + '0') + internal(prefix + '1')

    # leaves in pre-order get symbol indices 0,1,2,...; amap maps them to actions
    order = []

    def collect(prefix):
        if prefix in allp:
            order.append(prefix); return
        collect(prefix + '0'); collect(prefix + '1')
    collect('')
    sym_of = {p: i for i, p in enumerate(order)}
    amap = [paths[p] for p in order]

    bits = []
    def w(v, k):
        for i in range(k - 1, -1, -1):
            bits.append((v >> i) & 1)
    w(count - 1, 5)
    for a in amap:
        w(a, 5)
    w(internal(''), 5)

    def emit(prefix):
        for side in '01':
            child = prefix + side
            n = internal(child)
            w(n, 5)
            if n:
                emit(child)
            else:
                w(sym_of[child], 5)
    emit('')
    return bits


def pack(bits):
    out = bytearray()
    b = bits + [0] * ((-len(bits)) % 16)
    for i in range(0, len(b), 16):
        v = 0
        for x in b[i:i + 16]:
            v = (v << 1) | x
        out += v.to_bytes(2, 'little')
    return bytes(out), len(bits) % 16



def bits_of(data, start, nbits):
    bs = Bits(data, start)
    return [bs.bit() for _ in range(nbits)]




# ------------------------------------------------- the literal sub-tree
def contrib(V):
    """A literal leaf's contribution, mirroring 0x1495f..0x14986.

    V's four bits are spread into the even bit positions (the `or al,imm`
    form used at the second level) and into the odd positions (the
    `mov al,imm` form used at the first level).
    """
    if V == 0:
        return 0x00, 0x00                    # 0x149af
    if V == 1:
        return 0x01, 0x02                    # 0x149da
    cl, ch = (V << 4) & 0xff, 0
    for _ in range(4):
        ch = (ch * 2) & 0xff
        cx = (((ch << 8) | cl) * 2) & 0xffff
        ch, cl = (cx >> 8) & 0xff, cx & 0xff
    return ch, (ch * 2) & 0xff


def v_for_byte(b):
    """(V_level1, V_level2) that produce byte b, or None if impossible."""
    hi = sum(((b >> (2 * i + 1)) & 1) << i for i in range(4))   # odd bits -> mov
    lo = sum(((b >> (2 * i)) & 1) << i for i in range(4))       # even bits -> or
    return hi, lo


def parse_literals(bs):
    """Read the literal tree from the same bitstream; -> {bit path: V}."""
    leaves = {}

    def leaf(path):
        leaves[path] = bs.read(4)

    def node(path):
        n = bs.read(4)
        (node if n else leaf)(path + '0')
        m = bs.read(4)
        (node if m else leaf)(path + '1')

    (node if bs.read(4) else leaf)('')
    return leaves


def literal_alphabet(leaves, litpath=''):
    """The full literal code -> byte map: two levels, mov(V1) | or(V2).

    A tree with L leaves therefore spells exactly L*L byte values, which is
    why DS_T1 (3 leaves) has 9 literals and DS_T2 (9 leaves) has 81.
    """
    out = {}
    for c1, v1 in leaves.items():
        for c2, v2 in leaves.items():
            _, mov = contrib(v1)
            orm, _ = contrib(v2)
            out[litpath + c1 + c2] = mov | orm
    return out


def emit_literals(leaves):
    """Serialise a literal tree ({bit path: V}) back to bits."""
    paths = set(leaves)
    bits = []

    def w(v, k=4):
        for i in range(k - 1, -1, -1):
            bits.append((v >> i) & 1)

    def internal(prefix):
        return 0 if prefix in paths else 1 + internal(prefix + '0') + internal(prefix + '1')

    def emit(prefix):
        for side in '01':
            child = prefix + side
            n = internal(child)
            w(n)
            if n:
                emit(child)
            else:
                w(leaves[child])

    w(internal(''))
    if internal('') == 0:
        w(leaves[''])
    else:
        emit('')
    return bits


if __name__ == '__main__':
    import os, pickle, sys
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
    f = open(os.path.join(HERE, 'ext', 'A', 'DS_T1.AS2'), 'rb').read()
    p = parse_table(f)
    print('count', p['count'], 'internal', p['internal'], 'leaves', len(p['codes']))
    print('action map', p['amap'])
    print('table ends at byte %#x, %d bits into it' % p['end'])
    res = resolve(p)
    traced = pickle.load(open(os.path.join(HERE, 'tree_DS_T1.pkl'), 'rb'))
    print()
    ok = bad = 0
    for path, (kind, off) in sorted(res.items(), key=lambda kv: (len(kv[0]), kv[0])):
        t = traced.get(path)
        if kind == 'LITGROUP':
            kids = [b for b in traced if b.startswith(path)]
            print('  %-12s LITGROUP -> %d traced literal codes below it' % (path, len(kids)))
            continue
        exp = ('RLE', 0) if kind == 'RLE' else ('COPY', off)
        if t == exp:
            ok += 1
        else:
            bad += 1
            print('  MISMATCH %-12s parsed=%s traced=%s' % (path, exp, t))
    print('\nnon-literal codes: %d match, %d mismatch' % (ok, bad))
