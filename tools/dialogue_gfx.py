"""Dialogue boxes in MB3N's graphics mode, everything else in text mode.

The switch is in the common script, 99CMN.SCN (resident at 26d8:3000). Scripts open
the dialogue box through its entry table and close it through the same table:

    0x3006 -> 0x370e   draw the box frame (op b3), then the window at \\o13,17
    0x300c -> 0x3782   draw the box frame (op b3), then the window at \\o21,17 (portrait)
    0x3009 -> 0x371e   the same windows *without* drawing a frame: text straight onto
    0x300f -> 0x3792   the map, or into a box that is already up
    0x3063 -> 0x3ca5   ...and one at \\o13,20
    0x3015 -> 0x37ff   0x3018 -> 0x3800   close: (wait,) clear, end the block
    0x3012 -> 0x37ac   the location title at \\o26,3

The open routines end in the shared attribute string `\\c7\\b0\\i0\\t0\\f` and a return.
Graphics mode is only right inside a box frame - its clears paint the box's grey - so:

  * the two frame-drawing opens get a wrapper that calls them and then sets graphics
    mode (op 41 imm 0; see tools/mb3_gfx.py for the colours that go with it);
  * the frameless opens are left alone, so they keep whatever mode is on: graphics
    inside a box that is up, text otherwise;
  * the close routines and the title get a wrapper that sets text mode (op 41 imm 1) and
    then jumps to them.

The entry table and 99CMN's own calls and jumps to those routines are pointed at the
wrappers. Nothing moves, so no other pointer changes. The wrappers take 35 bytes past the
end of the file. The slot is 0xd00 bytes (it ends where slot 2 starts, at 0x3d00) and
the original file is 0xcc1.

    python tools/dialogue_gfx.py        # build the wrappers, print what changes
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0x3000                 # 99CMN is loaded at 26d8:3000
SLOT_END = 0x3d00

TEXT_MODE = bytes([0x41, 0x00, 0x01, 0x00])       # op 41, immediate 1
GFX_MODE = bytes([0x41, 0x00, 0x00, 0x00])        # op 41, immediate 0
CALL, JUMP, RETURN = 0x04, 0x09, 0x07

OPENS = [0x370e, 0x3782]                          # the ones that draw a box frame
CLOSES = [0x37ff, 0x3800]
# The location title draws a frame too (op b3), but its window is \w50,1 while its frame
# is only ~31 columns wide, so a graphics-mode clear paints grey across the map outside
# the frame. It would need its window narrowed to the frame first; one short line is not
# worth it, so it stays text mode.
TEXT_ONLY = [0x37ac]


def _word(v):
    return v.to_bytes(2, 'little')


def _refs(data, target, ops):
    """Offsets of `op <target>` instructions in the file (entry table excluded)."""
    entries = 0
    while data[entries] == JUMP:
        entries += 3
    out, pat = [], [bytes([op]) + _word(target) for op in ops]
    for i in range(entries, len(data) - 2):
        if data[i:i + 3] in pat:
            out.append(i)
    return out


# 99CMN's own calls and jumps to the routines, found by scanning and then checked by
# hand against the decoded blocks; the scan is only used to confirm these still hold.
INTERNAL = {
    0x370e: [0x37e5, 0x3838, 0x38a7, 0x3c63],     # 04 0e 37  call open
    0x37ff: [0x3858, 0x38c9, 0x3c7d],             # 09 ff 37  jump to close (wait)
    0x3800: [0x3995, 0x39d2],                     # 09 00 38  jump to close
}


def patch(data):
    """Original 99CMN.SCN -> patched. Raises if the file is not the one this was made for."""
    data = bytearray(data)
    entries = {}
    i = 0
    while data[i] == JUMP:
        entries[BASE + i] = int.from_bytes(data[i + 1:i + 3], 'little')
        i += 3
    for target, sites in INTERNAL.items():
        found = [BASE + x for x in _refs(data, target, (CALL, JUMP))]
        assert found == sites, '99CMN refs to %#x moved: %s' % (target, [hex(x) for x in found])

    at = BASE + len(data)
    wrappers, new = {}, bytearray()

    def emit(code):
        nonlocal new
        addr = at + len(new)
        new += code
        return addr

    gfx_tail = emit(GFX_MODE + bytes([RETURN]))
    for r in OPENS:
        wrappers[r] = emit(bytes([CALL]) + _word(r) + bytes([JUMP]) + _word(gfx_tail))
    for r in CLOSES + TEXT_ONLY:
        wrappers[r] = emit(TEXT_MODE + bytes([JUMP]) + _word(r))
    assert at + len(new) <= SLOT_END, '99CMN wrappers overflow the slot by %d bytes' % (
        at + len(new) - SLOT_END)

    for entry, target in entries.items():
        if target in wrappers:
            data[entry - BASE + 1:entry - BASE + 3] = _word(wrappers[target])
    for target, sites in INTERNAL.items():
        for s in sites:
            data[s - BASE + 1:s - BASE + 3] = _word(wrappers[target])
    return bytes(data + new)


# BD.BIN: back to text mode whenever a script run ends. The close routines above do it
# for the normal path, but a block may open a box and end (op 83) without them - BD takes
# the box down regardless - which would leave graphics mode on for whatever prints next.
# Every run of the interpreter (BD 0x33b2) leaves through `push cs / pop es / ret` at
# 0x33ce; that becomes a jump to 10 bytes in BD's unused tail (0xfbb9-0xfefd is zero in
# the image and was never read or written in 30 save states and 4 maps of play).
BD_EXIT, BD_HOOK = 0x33ce, 0xfc00
BD_EXIT_ORIGINAL = bytes([0x0e, 0x07, 0xc3])
BD_HOOK_CODE = bytes([
    0x50,                       # push ax
    0xb8, 0x01, 0x26,           # mov ax, 2601h        MB3N: text mode
    0xcd, 0x40,                 # int 40h
    0x58,                       # pop ax
    0x0e, 0x07, 0xc3,           # push cs / pop es / ret   (the original exit)
])


def patch_bd(data):
    """BD.BIN (original or reinserted - the code must not have moved) -> patched."""
    data = bytearray(data)
    assert data[BD_EXIT:BD_EXIT + 3] == BD_EXIT_ORIGINAL, 'BD %#x is not the interpreter exit' % BD_EXIT
    assert not any(data[BD_HOOK:BD_HOOK + len(BD_HOOK_CODE)]), 'BD %#x is not free' % BD_HOOK
    data[BD_EXIT:BD_EXIT + 3] = bytes([0xe9]) + (BD_HOOK - (BD_EXIT + 3)).to_bytes(2, 'little')
    data[BD_HOOK:BD_HOOK + len(BD_HOOK_CODE)] = BD_HOOK_CODE

    return bytes(data)


def apply_bd_to_ram(m, seg=0x16d8):
    base = seg << 4
    live = m.read(base, 0x10000)
    new = patch_bd(live)
    for at, n in ((BD_HOOK, len(BD_HOOK_CODE)), (BD_EXIT, 3)):
        m.write(base + at, new[at:at + n])


# The game writes the map number into a filename in 99CMN (`d\\mk00`, 0x3901-0x3902).
RUNTIME = {0x3901, 0x3902}


def apply_to_ram(m, seg=0x26d8):
    """Patch the resident 99CMN in a running machine: only the bytes the patch changes."""
    orig = open(os.path.join(HERE, 'original', 'decompressed', '99CMN.SCN'), 'rb').read()
    base = (seg << 4) + BASE
    live = m.read(base, len(orig))
    bad = [hex(BASE + i) for i in range(len(orig)) if live[i] != orig[i] and BASE + i not in RUNTIME]
    assert not bad, 'the 99CMN in RAM is not the original file: %s' % bad[:8]
    new = patch(orig)
    for i in range(len(orig)):
        if new[i] != orig[i]:
            m.write(base + i, new[i:i + 1])
    m.write(base + len(orig), new[len(orig):])
    apply_bd_to_ram(m)


if __name__ == '__main__':
    orig = open(os.path.join(HERE, 'original', 'decompressed', '99CMN.SCN'), 'rb').read()
    out = patch(orig)
    print('99CMN %#x -> %#x bytes (slot room %#x)' % (len(orig), len(out), SLOT_END - BASE))
    for i, (a, b) in enumerate(zip(orig, out)):
        if a != b:
            print('  %#06x: %02x -> %02x' % (BASE + i, a, b))
    print('  appended at %#x: %s' % (BASE + len(orig), out[len(orig):].hex(' ')))
