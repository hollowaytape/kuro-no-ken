"""Give the English subtitle its own flame sprites in the opening's code.

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
y_bottom) and blits a 192px-wide column of the current texture:

    si = (y_top - progress) * 24          ; texture row
    di =  y_top * 80 + x_bytes            ; screen position

The texture has only 376 rows - exactly enough for the tallest kanji - so an
entry with y_top = 330 would read off its end. But because `x_bytes` is just
added to `di`, an entry can use a *small* y_top (so `si` stays in range) and a
large `x_bytes` that carries the difference down to the subtitle's rows. The
burn-in gate, the partial-reveal path and the row count all stay consistent,
because they only ever see y_top and y_bottom.

The patch appends a cave after the end of the file (cs:0x147d onward is
zero-filled and untouched for the whole opening - checked with a read/write
watchpoint) and turns the `inc [0xc34]; ret` at cs:0x0ee0 into a jump to it.
"""
CAVE = 0x1480
HOOK = 0x0ee0
SPRITE = 0x0efd
HOOK_BYTES = bytes.fromhex('ff06340cc3')      # inc word [0xc34] ; ret


def _mov_bx(v):
    return b'\xbb' + v.to_bytes(2, 'little')


def _call(at, target):
    return b'\xe8' + ((target - (at + 3)) & 0xffff).to_bytes(2, 'little')


def _jmp(at, target):
    return b'\xe9' + ((target - (at + 3)) & 0xffff).to_bytes(2, 'little')


def sprite_entries(screen_top, rows, texture_row, x_bytes=(6, 30, 54), progress=-53):
    """Entries that draw `rows` lines at `screen_top`, sampling the flame
    texture from `texture_row` when the burn-in progress is at rest."""
    fake_top = texture_row + progress           # si = (fake_top - progress) * 24
    if fake_top < 0:
        raise ValueError('texture_row too small for this progress')
    shift = (screen_top - fake_top) * 80
    if texture_row + rows + 4 > 376:
        raise ValueError('would sample past the end of the 376-row texture')
    return [(xb + shift, 12, fake_top, fake_top + rows) for xb in x_bytes]


def patch_ipl(scn, entries):
    """Return 00IPL.SCN with extra sprite entries drawn every frame."""
    if scn[HOOK:HOOK + 5] != HOOK_BYTES:
        raise ValueError('unexpected bytes at the hook site; is this the '
                         'original 00IPL.SCN?')
    if len(scn) > CAVE:
        raise ValueError('file already extends past the cave')
    table = CAVE + 6 * len(entries) + 5
    table += table & 1
    code = bytearray()
    for i in range(len(entries)):
        at = CAVE + len(code)
        code += _mov_bx(table + 8 * i)
        code += _call(at + 3, SPRITE)
    code += HOOK_BYTES                           # the instructions we displaced
    while CAVE + len(code) < table:
        code += b'\x90'
    for e in entries:
        for w in e:
            code += (w & 0xffff).to_bytes(2, 'little')
    out = bytearray(scn) + bytes(CAVE - len(scn)) + code
    out[HOOK:HOOK + 5] = _jmp(HOOK, CAVE) + b'\x90\x90'
    return bytes(out)


def disassemble(scn, lo=CAVE, hi=None):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    return ['%04x  %-12s %s %s' % (i.address, i.bytes.hex(), i.mnemonic, i.op_str)
            for i in md.disasm(scn[lo:hi], lo)]
