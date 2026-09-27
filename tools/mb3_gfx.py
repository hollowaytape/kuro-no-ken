"""Make MB3N's graphics-mode text work on the scrolling map screen.

MB3N (the "MAKO-BIOS 3" text driver, resident at 12d7, INT 40h) can draw text into
graphics VRAM instead of text VRAM when cs:[0x828] = 0. The original game never uses
that mode, and on the map screen it draws in the wrong place, because the map scrolls
with the GDC: graphics VRAM is a ring, shown as two display areas whose start addresses
MB3N itself keeps at cs:0x68 (area 0) and cs:0x6c (area 1). See docs/vwf_findings.md.

This patch makes every graphics-mode VRAM address go through the scroll:

  rowaddr   screen line -> VRAM offset, using the length and start of both areas
  0x9a6     line start: the window row stays a *text* row (x16) in graphics mode, as it
            is in text mode, so \\o and the box strings work unchanged. Also records
            where this line crosses from area 0 into area 1 (WRAPAT / DELTA).
  0xaa6     window clear: one rowaddr per scanline
  0xb9b     next scanline of a full-width glyph  } step di over the area boundary
  0xc56     next scanline of a half-width glyph  } (checked before each scanline)

The blits' own `add di,4f/4e` are left alone: the shadow code rewrites their immediate
bytes at runtime (cs:0xc78, cs:0xbc7). Drop shadow ([0x827] != 0xff) is still not
scroll-aware; nothing sets it.

New code lives past the end of MB3N's image (0x3f49): the image can grow to 0x4010
bytes, where BD.BIN starts, without moving anything (checked by booting it).

    python tools/mb3_gfx.py            # assemble, check, print the layout
"""
import os
import re
import sys

import capstone
import keystone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGINAL_LEN = 0x3f49
MAX_LEN = 0x4010             # BD.BIN is loaded at MB3N's segment + 0x401
TAIL = 0x3f4a                # new code (word-aligned)

# Every site's original bytes, checked before patching.
ORIGINAL = {
    0x9a6: bytes.fromhex('2ea11e08051000 2ef7261808 2e03061008 ba5000 f7e2 '
                         '2e03060e08 2e03061608 8bf8 c3'.replace(' ', '')),
    0xaa6: bytes.fromhex('60 2e8a262408 b080 e84d02 2e8b2e1208 b85000 2ef7261008 '
                         '2e03060e08 8bf0 2e8b1e1408 ba1000 8bfe 8bcd d1e9 f3ab 13c9 '
                         'f3aa 83c650 4a 75ee b050 2ef6261e08 03f0 4b 75df e80902 61'
                         .replace(' ', '')),
    0xb9b: bytes.fromhex('8bc3e6a5'),
    0xc56: bytes.fromhex('8ac3e6a5'),
    0x833: bytes.fromhex('b00be668'),        # print: kanji ROM access on
    0x878: bytes.fromhex('b00ae668'),        # print: ...and off
    0xb2c: bytes.fromhex('b00be668'),        # number print: on
    0xb6e: bytes.fromhex('b00ae668'),        # number print: off
    0xa82: bytes.fromhex('6800a807'),        # AH=22h clear: push a800 / pop es
    0xa89: bytes.fromhex('e89702'),          # AH=22h clear: call GRCG off
}

# 0x9a9: behind the jump at 0x9a6, the rest of the old line-start code is free.
ENTER_AT, ENTER_END = 0x9a9, 0x9c9
ENTER_ASM = """
# Start of a graphics-mode print (replaces mov al,0bh + out 68h,al). The box strings set
# text-mode attributes - \\c7 is white on the text layer but palette 7, a dim grey, in
# graphics, and \\b0 clears to palette 0, not the box's grey - and MB3N's bold flag is on,
# which only the graphics blit honours. Graphics mode is used for dialogue boxes only,
# so every graphics print gets the look of text mode: white, box-grey clears, no bold.
gfx_enter:
    mov al, 0x0b
    out 0x68, al
    mov word ptr cs:[FILL], 0x0f09      # [824] clear colour 9, [825] text colour 0x0f
    mov word ptr cs:[PLANES], 0xff00    # [826] no \\p plane mask, [827] no drop shadow
    mov byte ptr cs:[BOLD], 0
    JMP show_page
"""

# Which helper each hook site calls (the helpers do what the replaced bytes did).
HOOKS = {
    0xb9b: 'wrap_full', 0xc56: 'wrap_half',
    0x833: 'gfx_enter', 0xb2c: 'gfx_enter',
    0x878: 'gfx_leave', 0xb6e: 'gfx_leave',
    0xa82: 'clear_enter', 0xa89: 'clear_leave',
}

# MB3N's own variables and routines used here (all cs-relative).
SYMBOLS = dict(
    SCROLL0=0x68, SCROLL1=0x6c,     # GDC scroll shadow: SAD (words), then LEN in bits 20-29
    WIN_COL=0x80e, WIN_ROW=0x810, WIN_W=0x812, WIN_H=0x814,
    CUR_COL=0x816, CUR_LINE=0x818, LINE_GAP=0x81e, FILL=0x824,
    MODE=0x828, BOLD=0x82b, PLANES=0x826, COLS_LEFT=0x81a,
    GLYPH_BUF=0x7ec,                # 32 bytes MB3N used only for drop-shadowed glyphs
    GRCG_SET=0xcfe,                 # al = mode, ah = tile colour
    GRCG_TEXT=0xcf7,                # RMW mode in the text colour
    GRCG_OFF=0xd23,
    ACCESS_PAGE=0x7a,               # graphics page the CPU writes to (MB3N AH=0Ah)
    SHOWN_PAGE=0x7b,                # graphics page on screen (MB3N AH=08h)
    # New variables, at the very end of the space (keystone gives a reference to a
    # data *label* a 32-bit address-size prefix, so they are absolute addresses).
    WRAPAT=0x400c,                  # di at which the current line leaves area 0 (ffff: never)
    DELTA=0x400e,                   # ...and what to add to di when it does
)
DATA = {0x400c: b'\xff\xff', 0x400e: b'\x00\x00'}

TAIL_ASM = """
# Draw on the page that is on screen, as BD's own box drawing does (it sets the access
# page with AH=0Ah around it); while the map scrolls the two differ. MB3N's record of
# the access page is left alone, so leaving just writes it back to the port.
show_page:                          # (gfx_enter, at 0x9a9, ends here)
    mov al, byte ptr cs:[SHOWN_PAGE]
    out 0xa6, al
    RET
gfx_leave:                          # replaces mov al,0ah + out 68h,al
    mov al, 0x0a
    out 0x68, al
work_page:
    mov al, byte ptr cs:[ACCESS_PAGE]
    out 0xa6, al
    RET
clear_enter:                        # replaces push a800 + pop es (ax is saved by the caller)
    mov ax, 0xa800
    mov es, ax
    jmp show_page
clear_leave:                        # replaces call GRCG_OFF
    CALL GRCG_OFF
    jmp work_page

wrap_full:                         # replaces mov ax,bx + out a5,al at 0xb9b
    mov ax, bx
    jmp wrap
wrap_half:                          # replaces mov al,bl + out a5,al at 0xc56
    mov al, bl
wrap:
    out 0xa5, al
    cmp di, word ptr cs:[WRAPAT]
    jb wrap_ok
    add di, word ptr cs:[DELTA]
wrap_ok:
    RET

# ax = screen line -> ax = VRAM offset of its first byte. dx is clobbered.
rowaddr:
    push bx
    mov bx, SCROLL0
    CALL area_len
    cmp ax, dx
    jb rowaddr_in
    sub ax, dx
    mov bx, SCROLL1
rowaddr_in:
    mov dx, 80
    mul dx
    add ax, word ptr cs:[bx]
    add ax, word ptr cs:[bx]        # the start address is in words
    pop bx
    RET

# bx -> a scroll area; dx = its length in lines
area_len:
    mov dx, word ptr cs:[bx + 2]
    shr dx, 4
    and dx, 0x3ff
    RET

# di = VRAM address of the current text position (replaces MB3N 0x9a6, which
# changed only ax, dx and di)
line_start:
    push bx
    mov ax, word ptr cs:[LINE_GAP]
    add ax, 16
    mul word ptr cs:[CUR_LINE]
    mov dx, word ptr cs:[WIN_ROW]
    shl dx, 4
    add ax, dx                      # ax = screen line of the top of this text line
    push ax
    mov bx, SCROLL0
    CALL area_len                   # dx = lines in area 0
    mov word ptr cs:[WRAPAT], 0xffff
    cmp ax, dx
    jae line_addr                   # the line starts in area 1: it never wraps
    mov ax, dx
    dec ax
    CALL rowaddr                    # the last line of area 0...
    add ax, 80
    mov word ptr cs:[WRAPAT], ax    # ...and just past it
    CALL area_len
    mov ax, dx
    CALL rowaddr                    # the first line of area 1
    sub ax, word ptr cs:[WRAPAT]
    mov word ptr cs:[DELTA], ax
line_addr:
VWF_RESET
    pop ax
    CALL rowaddr
    add ax, word ptr cs:[WIN_COL]
    add ax, word ptr cs:[CUR_COL]
    mov di, ax
    pop bx
    RET
"""

# 0xaa6: the graphics branch of the window clear, rewritten in place (74 bytes).
CLEAR_ASM = """
    pusha
    mov ah, byte ptr cs:[FILL]
    mov al, 0x80                    # GRCG TDW: every write stores the tile colour
    CALL GRCG_SET
    mov ax, word ptr cs:[LINE_GAP]
    add ax, 16
    mul word ptr cs:[WIN_H]
    mov bp, ax                      # scanlines to clear
    mov bx, word ptr cs:[WIN_ROW]
    shl bx, 4                       # first screen line
clear_row:
    mov ax, bx
    CALL rowaddr
    add ax, word ptr cs:[WIN_COL]
    mov di, ax
    mov cx, word ptr cs:[WIN_W]
    shr cx, 1
    rep stosw
    adc cx, cx
    rep stosb
    inc bx
    dec bp
    jnz clear_row
    CALL GRCG_TEXT
    popa
    RET
"""


# ---------------------------------------------------------------- variable-width font
# glodia's pen model (glodia/vwf.py): MB3N keeps its byte column - [816] column, [81a]
# columns left, di - so its wrapping, indent and clears work unchanged; FRAC is the pixel
# remainder (0-7) within the byte, reset by line_start at every new line, page or print.
# Each half-width glyph is read from the kanji ROM once into GLYPH_BUF, its ink columns
# measured (bsr/bsf: the game needs a 386), then drawn trimmed on the left and shifted
# right by FRAC; the pen moves by the ink width + 1 px (a space: SPACE_W px).
# Spacing: both are immediates in the blit, so changing them costs no code space, and
# tools/vwf_metrics.py reads them, so typesetting follows. (The advance is added to FRAC
# in a byte, so it must stay below 248.)
SPACE_W = 5                          # pen advance for a glyph with no ink (the space)
GAP = 1                              # blank columns between two glyphs' ink
VWF_A, VWF_A_END = 0xc3a, 0xc87      # the graphics half of the half-width blit (0xc31)
VWF_B, VWF_B_END = 0xc9a, 0xcd3      # the drop-shadow routine, only reached from it
FRAC = VWF_B_END - 1                 # 1 byte

VWF_ORIGINAL = {
    VWF_A: bytes.fromhex(
        'e85dfd740c0e072ec606780c0057bfec07e6a186c4e6a3b320b910008ac3e6a5e4a92e382e2b08'
        '74128ad08af0d0e2d0ee22f2d0e6f6d622c60ac2aa83c74f43e2dae81bfd74045fe81500eb11'),
    VWF_B: bytes.fromhex(
        '1e560e1fc606780c4f6800a807e84600beec07b91000515657ac8ae0d0ee0ac426884550aa83c7'
        '4fe2efe830005f5e59a483c74fe2fa5e1fc3'),
    0xa16: b'\x01',                  # after a glyph: `jne` over the text path's extra inc di
}

# 0xc3a. In: di pushed (0xc31), ah = 09 (JIS row - 20h), al = the character, es = VRAM
# with the GRCG in read-modify-write mode (only 1 bits are painted).
VWF_A_ASM = """
vwf_glyph:
    push si
    push ds
    push cs
    pop ds
    out 0xa1, al
    mov al, ah
    out 0xa3, al
    mov bx, 0x20                    # kanji ROM line select: 20h + line, left half
    xor dx, dx
vg_read:
    mov al, bl
    out 0xa5, al
    in al, 0xa9
    mov byte ptr [bx + BUF_M20], al
    or dl, al                       # dl = every column with ink
    inc bx
    cmp bl, 0x30
    jb vg_read
    mov al, SPACE_W
    test dx, dx
    jz vg_space
    bsr cx, dx                      # leftmost ink column (bit 7 = the glyph's first pixel)
    bsf ax, dx                      # rightmost
    neg al
    add al, cl
    add al, GAP + 1                 # advance = ink width + GAP
    push ax
    neg cl
    add cl, 15
    sub cl, byte ptr [FRAC]         # row << (15 - leftmost - FRAC): ink starts FRAC px in
    JMP vwf_draw
vg_space:
    JMP vwf_advance
"""

# 0xc9a. vwf_draw: cl = shift, the advance pushed; vwf_advance: al = pixels to advance.
# ds = cs; below that the stack has si, ds and the original di.
VWF_B_ASM = """
vwf_draw:
    mov si, GLYPH_BUF
    mov dh, 16
vg_row:
    lodsb
    xor ah, ah
    shl ax, cl
    xchg al, ah
    stosw                           # left byte, then the one it spills into
    add di, 78
    CALL WRAP_CHECK
    dec dh
    jnz vg_row
    pop ax
vwf_advance:
    add al, byte ptr [FRAC]
    mov ah, al
    and ah, 7
    mov byte ptr [FRAC], ah
    shr al, 3
    cbw                             # ax = whole bytes to advance
    sub word ptr [COLS_LEFT], ax
    add word ptr [CUR_COL], ax
    pop ds
    pop si
    pop di
    add di, ax
    RET
"""


def _assemble(src, at, symbols):
    """keystone, 16-bit, with its quirks worked around. In the sources:

    `#` starts a comment (`;` separates statements in keystone's GNU syntax);
    RET, CALL x and JMP x are hand-encoded, because keystone gives near ret/call/jmp
    a 66 prefix. A CALL/JMP to one of `symbols` (an absolute MB3N address) is encoded
    against the start of the block, since keystone evaluates `const - .` with . = 0.
    """
    def branch(m):
        op, target = m.group(1), m.group(2)
        opcode = '0xe8' if op == 'CALL' else '0xe9'
        if target in symbols:
            disp = '%s - AT_ - (. - START_) - 2' % target
        else:
            disp = '%s - . - 2' % target
        return '.byte %s\n    .word %s' % (opcode, disp)
    src = src.replace('RET', '.byte 0xc3')
    src = re.sub(r'(CALL|JMP) (\w+)', branch, src)
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_16)
    head = ''.join('%s = %#x\n' % kv for kv in symbols.items())
    head += 'AT_ = %#x\nSTART_:\n' % at
    enc, _ = ks.asm(head + src, at)
    return bytes(enc)


def _labels(src):
    return [line.split(':')[0].strip() for line in src.splitlines()
            if ':' in line.split('#')[0] and line.split(':')[0].strip().isidentifier()
            and not line.strip().startswith('.')]


def _assemble_with_labels(src, at, symbols):
    """-> (code, {label: address}): a trailing `.word` table reports each label."""
    names = _labels(src)
    enc = _assemble(src + '\n' + '\n'.join('.word %s' % n for n in names), at, symbols)
    code, table = enc[:-2 * len(names)], enc[-2 * len(names):]
    return code, {n: int.from_bytes(table[2 * i:2 * i + 2], 'little') for i, n in enumerate(names)}


def _check(code, at, what):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    n = 0
    for ins in md.disasm(code, at):
        n += ins.size
        if {0x66, 0x67} & set(ins.bytes[:3]):
            raise AssertionError('%s: 32-bit prefix at %#x: %s %s' % (
                what, ins.address, ins.mnemonic, ins.op_str))
    return n


def build(vwf=True):
    """-> {address: bytes} for every patch site, including the new tail.

    vwf=False gives the fixed-width graphics mode (the text-mode look, pixel for pixel),
    which is what tools/test_mb3_gfx.py compares against text mode."""
    syms = dict(SYMBOLS, FRAC=FRAC, SPACE_W=SPACE_W, GAP=GAP, BUF_M20=SYMBOLS['GLYPH_BUF'] - 0x20)
    tail_src = TAIL_ASM.replace('VWF_RESET', '    mov byte ptr cs:[FRAC], 0' if vwf else '')
    tail, labels = _assemble_with_labels(tail_src, TAIL, syms)
    syms.update(labels)                  # the clear calls rowaddr
    _check(tail, TAIL, 'tail')
    assert TAIL + len(tail) <= min(DATA), 'tail is %d bytes too long' % (TAIL + len(tail) - min(DATA))

    clear = _assemble(CLEAR_ASM, 0xaa6, syms)
    _check(clear, 0xaa6, 'clear')
    assert len(clear) <= len(ORIGINAL[0xaa6]), 'clear is %d bytes too long' % (
        len(clear) - len(ORIGINAL[0xaa6]))
    clear += b'\x90' * (len(ORIGINAL[0xaa6]) - len(clear))

    def branch(op, at, target, size):
        code = _assemble('%s target' % op, at, {'target': target})
        _check(code, at, op)
        return code + b'\x90' * (size - len(code))

    sites = {
        0x9a6: branch('JMP', 0x9a6, labels['line_start'], len(ORIGINAL[0x9a6])),
        0xaa6: clear,
        TAIL: tail,
    }
    enter, enter_labels = _assemble_with_labels(ENTER_ASM, ENTER_AT, syms)
    _check(enter, ENTER_AT, 'gfx_enter')
    assert ENTER_AT + len(enter) <= ENTER_END, 'gfx_enter is %d bytes too long' % (
        ENTER_AT + len(enter) - ENTER_END)
    sites[ENTER_AT] = enter             # after 0x9a6's jump + nop padding, so it wins
    labels.update(enter_labels)

    for at, helper in HOOKS.items():
        if vwf and at == 0xc56:
            continue                     # the half-width blit is replaced whole
        sites[at] = branch('CALL', at, labels[helper], len(ORIGINAL[at]))
    sites.update(DATA)

    if vwf:
        syms.update(labels, WRAP_CHECK=labels['wrap'] + 2)   # wrap without its out a5h
        b, b_labels = _assemble_with_labels(VWF_B_ASM, VWF_B, syms)
        _check(b, VWF_B, 'vwf_advance')
        assert VWF_B + len(b) <= FRAC, 'vwf_advance is %d bytes too long' % (VWF_B + len(b) - FRAC)
        syms.update(b_labels)
        a = _assemble(VWF_A_ASM, VWF_A, syms)
        _check(a, VWF_A, 'vwf_glyph')
        assert VWF_A + len(a) <= VWF_A_END, 'vwf_glyph is %d bytes too long' % (
            VWF_A + len(a) - VWF_A_END)
        sites[VWF_A] = a
        sites[VWF_B] = b
        sites[FRAC] = b'\x00'
        sites[0xa16] = b'\x0c'           # graphics: straight to the ret, the blit advanced
        labels.update(b_labels)
    return sites, labels


def patch(image, vwf=True):
    """Original MB3N image (0x3f49 bytes) -> patched image (0x4010 bytes)."""
    assert len(image) == ORIGINAL_LEN, 'expected the original MB3N.BIN, %#x bytes' % len(image)
    for at, orig in list(ORIGINAL.items()) + list(VWF_ORIGINAL.items()):
        assert image[at:at + len(orig)] == orig, 'MB3N %#x is not the original code' % at
    sites, _ = build(vwf)
    out = bytearray(image) + bytearray(MAX_LEN - ORIGINAL_LEN)
    for at, code in sites.items():
        out[at:at + len(code)] = code
    return bytes(out)


def apply_to_ram(m, seg=0x12d7, vwf=True):
    """Write just the patched code into a running machine (no runtime data touched)."""
    sites, labels = build(vwf)
    for at, code in sites.items():
        m.write((seg << 4) + at, code)
    return labels


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    from decompress import decompress
    img = decompress(open(os.path.join(HERE, 'original', 'MB3N.BIN'), 'rb').read())
    sites, labels = build()
    patch(img)
    for at, code in sorted(sites.items()):
        print('%#06x  %3d bytes' % (at, len(code)))
    end = TAIL + len(sites[TAIL])
    print('tail %#x-%#x, %d bytes free before the variables at %#x' % (TAIL, end, min(DATA) - end, min(DATA)))
    print('labels:', ', '.join('%s=%#x' % kv for kv in sorted(labels.items(), key=lambda kv: kv[1])))
