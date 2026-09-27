"""Flame sprites for new title-card artwork, patched into the opening's code.

The title card's flames are drawn by code that lives inside **00IPL.SCN** (the
opening script, loaded at cs=0x26d8 with file offset == cs offset). Once per
frame, cs:0x0eb1 does:

    [0xf34] = [0xc2c] + 0x69c * ((frame/6) % 3)   ; pick one of 3 flame textures
    mov bx,0x0ee5 / call 0x0efd                    ; 黒
    mov bx,0x0eed / call 0x0efd                    ; の
    mov bx,0x0ef5 / call 0x0efd                    ; 剣
    inc word [0xc34]                               ; frame counter
    ret

and cs:0x0e45 nudges the burn-in progress word [0xc32] every 9 frames. So the
animation is a 3-frame flipbook *plus* a vertical wobble, and both come for
free to anything drawn through 0x0efd.

0x0efd takes an 8-byte entry at cs:bx = (x_bytes, width_words, y_top,
y_bottom) and blits a column of the current texture into planes B/R/G:

    si = (y_top - progress) * 24          ; texture row
    di =  y_top * 80 + x_bytes            ; screen position
    width: 12 words (192px) if width_words == 12, otherwise 7 words (112px)

Because `x_bytes` is only ever added to `di`, an entry can use one y_top for
*which texture rows it samples* and carry the difference to *where it lands on
screen* in x_bytes. The burn-in gate, the partial-reveal path and the row count
all stay consistent, since they only ever see y_top and y_bottom.

What can be placed:
  * x on an 8-pixel grid, width 192 or 112 pixels;
  * any rows, as long as the sampled texture rows stay inside its 376;
  * as many as fit in the cave (14 bytes each).

The patch appends a cave after the end of the file (cs:0x147d..0x16ff is
zero-filled and untouched for the whole opening - checked with a read/write
watchpoint) and diverts the first kanji draw (cs:0x0ece) through it, so the new
sprites are drawn **before** the kanji. Where a new rectangle overlaps a kanji
rectangle, the kanji then repaint their own area, and the overlap is harmless.
"""
import numpy as np

CAVE = 0x1480
CAVE_END = 0x1700          # verified untouched up to here
HOOK = 0x0ece
HOOK_BYTES = bytes.fromhex('bbe50ee82900')      # mov bx,0x0ee5 ; call 0x0efd
RESUME = HOOK + len(HOOK_BYTES)
SPRITE = 0x0efd
KANJI_TABLE = (0x0ee5, 0x0eed, 0x0ef5)

TEXTURE_ROWS = 376
REST_PROGRESS = -53        # where the burn-in progress word settles
WOBBLE = 4                 # it hovers a few rows either side of that
WIDTHS = {24: 12, 14: 7}   # width in 8px units -> width_words
MERGE_GAP = 12             # rows; closer bands share one texture mapping


# ---------------------------------------------------------------- reading
def kanji_rects(scn):
    """The stock sprites as screen rectangles (x0, x1, y0, y1), end-exclusive."""
    out = []
    for a in KANJI_TABLE:
        xb, w, top, bottom = [int.from_bytes(scn[a + 2 * i:a + 2 * i + 2], 'little')
                              for i in range(4)]
        out.append((xb * 8, xb * 8 + (192 if w == 12 else 112), top, bottom))
    return out


def rect_mask(rects, shape=(400, 640)):
    m = np.zeros(shape, bool)
    for x0, x1, y0, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


# ---------------------------------------------------------------- fitting
def _bands(new):
    rows = np.where(new.any(axis=1))[0]
    if not len(rows):
        return []
    bands, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r - prev > MERGE_GAP:
            bands.append((int(start), int(prev) + 1))
            start = r
        prev = r
    bands.append((int(start), int(prev) + 1))
    return bands


def _fit_columns(band):
    """Cover a band's columns with the fewest 192/112px rectangles, then the
    fewest joins through strokes, then the least area. -> [(x_units, w_units)]."""
    n = band.shape[1] // 8
    col = band.reshape(band.shape[0], n, 8).any(axis=(0, 2))

    def seam(j):
        if j <= 0 or j >= n:
            return 0
        x = 8 * j
        return int((band[:, x - 1] & band[:, x]).sum())

    INF = float('inf')
    best = [[INF, INF] for _ in range(n + 1)]    # [u][segment ended at u]
    back = [[None, None] for _ in range(n + 1)]
    best[0][0] = 0
    for u in range(n):
        for e in (0, 1):
            c = best[u][e]
            if c == INF:
                continue
            if not col[u] and c < best[u + 1][0]:          # leave u uncovered
                best[u + 1][0] = c
                back[u + 1][0] = (u, e, None)
            for L in range(1, 25):
                v = u + L
                if v > n:
                    break
                w = 14 if L <= 14 else 24
                x = u if u + w <= n else n - w
                if x < 0 or (x < u and col[x:u].any()):
                    continue                                  # would repaint a neighbour
                cost = c + 10 ** 6 + w * band.shape[0] + (10 ** 3 * seam(u) if e else 0)
                if cost < best[v][1]:
                    best[v][1] = cost
                    back[v][1] = (u, e, (x, w))
    e = 0 if best[n][0] <= best[n][1] else 1
    if best[n][e] == INF:
        raise ValueError('could not cover the artwork')
    rects, u = [], n
    while u:
        pu, pe, r = back[u][e]
        if r is not None:
            rects.append((r, pu, u))
        u, e = pu, pe
    rects.reverse()
    joins = []
    for (r1, a1, b1), (r2, a2, b2) in zip(rects, rects[1:]):
        if b1 == a2 and seam(a2):
            joins.append((8 * a2, seam(a2)))
    return [r for r, _, _ in rects], joins


def texture_row_for(top, rows, preferred):
    """Which texture row a band's top samples at rest.

    A band that fits under the kanji's own mapping (texture row = screen row
    + 53) uses it, so it burns in and brightens exactly like the kanji. Lower
    bands can't - the texture runs out - and start at `preferred` instead.
    """
    if top - REST_PROGRESS + rows + WOBBLE <= TEXTURE_ROWS:
        return top - REST_PROGRESS
    return max(0, min(preferred, TEXTURE_ROWS - WOBBLE - rows))


def fit(new, preferred_row):
    """Plan sprites for every white pixel the kanji rectangles don't cover.

    Returns a list of bands: dict(top, bottom, texture_row, rects=[(x, w)],
    joins=[(x, rows_cut)]), all in pixels.
    """
    plan = []
    for top, bottom in _bands(new):
        rows = bottom - top
        if rows + WOBBLE > TEXTURE_ROWS:
            raise ValueError('artwork rows %d-%d are taller than the flame texture'
                             % (top, bottom - 1))
        rects, joins = _fit_columns(new[top:bottom])
        plan.append(dict(top=top, bottom=bottom,
                         texture_row=texture_row_for(top, rows, preferred_row),
                         rects=[(8 * x, 8 * w) for x, w in rects], joins=joins))
    return plan


def entries_for(plan):
    """Sprite-table entries (x_bytes, width_words, y_top, y_bottom)."""
    out = []
    for b in plan:
        rows = b['bottom'] - b['top']
        fake_top = b['texture_row'] + REST_PROGRESS     # si = (y_top - progress) * 24
        shift = (b['top'] - fake_top) * 80
        for x, w in b['rects']:
            out.append((x // 8 + shift, WIDTHS[w // 8], fake_top, fake_top + rows))
    return out


# ---------------------------------------------------------------- patching
def _mov_bx(v):
    return b'\xbb' + v.to_bytes(2, 'little')


def _call(at, target):
    return b'\xe8' + ((target - (at + 3)) & 0xffff).to_bytes(2, 'little')


def _jmp(at, target):
    return b'\xe9' + ((target - (at + 3)) & 0xffff).to_bytes(2, 'little')


def patch_ipl(scn, entries):
    """Return 00IPL.SCN with `entries` drawn every frame, before the kanji."""
    if scn[HOOK:HOOK + len(HOOK_BYTES)] != HOOK_BYTES:
        raise ValueError('unexpected bytes at the hook site; is this the '
                         'original 00IPL.SCN?')
    if len(scn) > CAVE:
        raise ValueError('file already extends past the cave')
    code_len = 6 * len(entries) + len(HOOK_BYTES) + 3
    table = CAVE + code_len + (code_len & 1)
    if table + 8 * len(entries) > CAVE_END:
        raise ValueError('%d sprites do not fit in the code cave (max about %d)'
                         % (len(entries), (CAVE_END - CAVE - 12) // 14))
    code = bytearray()
    for i in range(len(entries)):
        at = CAVE + len(code)
        code += _mov_bx(table + 8 * i)
        code += _call(at + 3, SPRITE)
    at = CAVE + len(code)
    code += _mov_bx(KANJI_TABLE[0])                  # the instructions we displaced
    code += _call(at + 3, SPRITE)
    code += _jmp(CAVE + len(code), RESUME)
    while CAVE + len(code) < table:
        code += b'\x90'
    for e in entries:
        for w in e:
            code += (w & 0xffff).to_bytes(2, 'little')
    out = bytearray(scn) + bytes(CAVE - len(scn)) + code
    out[HOOK:HOOK + len(HOOK_BYTES)] = _jmp(HOOK, CAVE) + b'\x90' * (len(HOOK_BYTES) - 3)
    return bytes(out)


def disassemble(scn, lo=CAVE, hi=None):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    return ['%04x  %-12s %s %s' % (i.address, i.bytes.hex(), i.mnemonic, i.op_str)
            for i in md.disasm(scn[lo:hi], lo)]
