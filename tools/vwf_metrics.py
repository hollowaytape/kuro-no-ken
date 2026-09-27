"""Pixel widths of dialogue text under the VWF in tools/mb3_gfx.py, for typesetting.

The renderer measures each half-width glyph's ink columns at run time; this does the
same from the same font (FONT.ROM, which np2core also loads - the kanji ROM's half-width
row, as glodia/vwf.py reads it). A glyph advances the pen by its ink width + GAP; a
space (a glyph with no ink) by SPACE_W.

MB3N still counts the line in bytes: 50 columns = 400 px, and it breaks a line (without
looking for a space) when a glyph starts with no column left. So a line fits when its
pixel width, plus the indent, stays within the window's columns * 8.

    python tools/vwf_metrics.py "Some text"     # its width in pixels
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mb3_gfx                                                      # noqa: E402

FONT_ROM = os.path.join(HERE, '..', '..', 'romtools', 'np2debug', 'FONT.ROM')
ROM_HALFWIDTH = 0x7400        # glyph for byte c: FONT.ROM[0x7400 + c*0x20 : +16]
GAP = mb3_gfx.GAP
SPACE_W = mb3_gfx.SPACE_W

_ADV = None


def advances():
    """Pen advance in pixels for each byte 0x20-0x7e."""
    global _ADV
    if _ADV is None:
        rom = open(FONT_ROM, 'rb').read()
        _ADV = {}
        for c in range(0x20, 0x7f):
            ink = 0
            for r in rom[ROM_HALFWIDTH + c * 0x20:][:16]:
                ink |= r
            if not ink:
                _ADV[c] = SPACE_W
            else:
                cols = [x for x in range(8) if ink & (0x80 >> x)]
                _ADV[c] = cols[-1] - cols[0] + 1 + GAP
    return _ADV


def width(text):
    """Width in pixels of plain ASCII `text` (bytes or str) on one line."""
    if isinstance(text, str):
        text = text.encode('ascii')
    adv = advances()
    return sum(adv.get(c, 8) for c in text)


def ink_end(text):
    """x (from the pen's start) just past the last ink pixel - where the line visibly ends."""
    if isinstance(text, str):
        text = text.encode('ascii')
    adv = advances()
    x = end = 0
    for c in text:
        a = adv.get(c, 8)
        if a != SPACE_W or c != 0x20:
            end = x + a - GAP
        x += a
    return end


def columns_used(text):
    """Bytes MB3N counts for `text` (the pen's byte column after it)."""
    return width(text) // 8


if __name__ == '__main__':
    for s in sys.argv[1:] or ['The quick brown fox jumps over the lazy dog.']:
        print('%4d px  %2d cols  %r' % (width(s), columns_used(s), s))
