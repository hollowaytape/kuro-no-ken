"""Check tools/mb3_gfx.py: graphics-mode text must look exactly like text-mode text.

For each save state (and a few camera positions in it), the same two-page dialogue is
rendered twice - once as the game does it (text VRAM), once with the MB3N patch applied
in RAM and graphics mode switched on - and the two screens are compared pixel by pixel.
The only allowed difference is the text colour: text-mode white is #fff, graphics
palette 0x0f is #eee. Anything else (a glyph in the wrong place, a missed wrap, a clear
that leaves junk or paints over the map) shows up as a differing pixel.

By default graphics mode, text colour and bold are forced from a hook at MB3N's print
entry. With --script, 99CMN is patched too (tools/dialogue_gfx.py) and nothing is forced:
the box routines switch graphics mode on themselves, each of the five ways 99CMN opens a
box is tried, and text mode must be back on once the block has ended.

    python tools/test_mb3_gfx.py                       # default states
    python tools/test_mb3_gfx.py area_05 area_17 ...
    python tools/test_mb3_gfx.py --script r03_manor_inside
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import RenderBench, FF, NL, CALL_OPEN, CALL_END, SEG   # noqa: E402
from kuro_core import SCANCODES                                    # noqa: E402
from romtools.np2core import HOOK_LOG                              # noqa: E402
from PIL import Image                                              # noqa: E402
import mb3_gfx                                                     # noqa: E402
import dialogue_gfx                                                # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scratch_emu', 'mb3_gfx')
MB = 0x12d70
PAGE = FF + bytes([0x00, 0x3b, 0x40, 0x02])         # end string, wait for a key, print on
TEXT = (b'Karin' + NL + b'\\i2The quick brown fox jumps over the lazy dog,' + NL +
        b'then wanders off to find something better to do.' + NL +
        b'Digits and marks: 0123456789 !?,.\'"()-:;' + NL +
        b'Line four, the last one that fits in the box.' + PAGE +
        b'Second page after a page break. This line is long enough that the engine has to wrap it.' + FF)
TEXT_WHITE, GFX_WHITE = (255, 255, 255), (238, 238, 238)
DEFAULT_STATES = ['r03_manor_inside', 'area_05', 'area_12', 'area_17', 'area_22', 'area_28']


def scroll_areas(m):
    """[(start byte, lines) for display areas 0 and 1, (access page, display page)]"""
    out = []
    for at in (0x68, 0x6c):
        q = m.read(MB + at, 4)
        out.append(((q[0] | q[1] << 8 | (q[2] & 3) << 16) * 2, (q[2] >> 4) | (q[3] & 0x3f) << 4))
    out.append(tuple(m.read(MB + 0x7a, 2)))
    return out


def render(b, walk, how, opener=CALL_OPEN):
    """Show TEXT; -> (screens after each page, scroll areas when the box opened,
    MB3N's mode flag once the block has finished).

    how: 'text'   - the game as it is
         'forced' - MB3N patched, graphics mode forced on at every print
         'script' - MB3N and 99CMN patched, nothing forced (the real switch)
    """
    e, m = b.e, b.e.m
    b.reset()
    for key, frames in walk:                       # move the camera first
        m.key(SCANCODES[key], True); m.run(frames); m.key(SCANCODES[key], False); m.run(10)
    at = b.free_at(len(TEXT) + 16)
    e.write(SEG + at, opener + b'\x40\x02' + TEXT + b'\x00' + CALL_END)
    e.write(b.table() + 2 * 3, at.to_bytes(2, 'little'))
    b.arm(3)
    st = {'printed': False, 'areas': None, 'modes': []}

    def cb(ev):
        st['printed'] = True
        st['modes'].append(m.read(MB + 0x828, 1)[0])
        if st['areas'] is None:
            st['areas'] = scroll_areas(m)
        if how == 'forced':
            m.write(MB + 0x828, b'\x00')           # graphics mode
            m.write(MB + 0x824, b'\x09')           # clear to the box interior
            m.write(MB + 0x825, b'\x0f')           # white
            m.write(MB + 0x82b, b'\x00')           # not bold
        return False
    m.set_callback(cb)
    m.hook(MB + 0x82c, HOOK_LOG)
    if how != 'text':
        mb3_gfx.apply_to_ram(m, vwf=False)      # fixed width: comparable with text mode
    if how == 'script':
        dialogue_gfx.apply_to_ram(m)
    for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
        m.key(SCANCODES[k], True)
        for _ in range(40):
            m.run(1)
            if st['printed']:
                break
        m.key(SCANCODES[k], False); m.run(2)
        if st['printed']:
            break
        m.run(20)
    shots = []
    if st['printed']:
        for _ in range(3):                        # page 1, page 2, box closed
            m.run(300); shots.append(e.image()); e.tap('SPACE', 0.1)
    m.run(60)
    m.clear_hooks(); m.set_callback(None)
    render.modes = st['modes']             # MB3N's mode at each print, for the caller
    return shots, st['areas'], m.read(MB + 0x828, 1)[0]


def compare(a, b):
    """-> (pixels that differ other than white/#eee text, text pixels in `a`)."""
    bad = text = 0
    for p, q in zip(a.getdata(), b.getdata()):
        if p == TEXT_WHITE:
            text += 1
        if p != q and not (p == TEXT_WHITE and q == GFX_WHITE):
            bad += 1
    return bad, text


def main(states, how='forced'):
    os.makedirs(OUT, exist_ok=True)
    walks = [[], [('UP', 30)], [('DOWN', 30)], [('UP', 60), ('LEFT', 30)]]
    # With the real switch, try each way 99CMN opens a box (entry -> routine).
    openers = [('3006', CALL_OPEN)]
    if how == 'script':
        openers = [(name, bytes([0x04, int(name[2:], 16), 0x30]))
                   for name in ('3006', '3009', '300c', '300f', '3063')]
    failures = 0
    b = None
    for state in states:
        try:
            if b is None:
                b = RenderBench(state)
            else:                                  # np2core: one Machine per process
                b.e.load_state(state)
                b.e.set_noclip(True)
                b.e.heal()
                b.base = b.e.m.save_state()
        except Exception as x:                    # noqa: BLE001
            print('%-18s skipped: %s' % (state, x))
            continue
        for w, walk in enumerate(walks):
          for oname, opener in openers:
            try:
                text, areas, _ = render(b, walk, 'text', opener)
                gfx, areas_g, mode_after = render(b, walk, how, opener)
            except AssertionError as x:           # e.g. no free space for the block
                print('%-18s walk %d: skipped: %s' % (state, w, x))
                break
            if not text or not gfx:
                print('%-18s walk %d: the block did not run' % (state, w))
                continue
            (s0, l0), (s1, l1), (access, shown) = areas
            results = [compare(t, g) for t, g in zip(text, gfx)]
            # The real switch must also leave text mode on once the block is over, and the
            # dialogue (the last prints) must really have gone through graphics mode for
            # the frame-drawing opens and through text mode for the frameless ones.
            # (e.g. 'ttggt': window + attributes in text, both pages in graphics, then the
            # close routine's own print after it has switched back)
            modes = ''.join('t' if x else 'g' for x in render.modes)
            want_gfx = how == 'forced' or oname in ('3006', '300c')
            ok = (all(bad == 0 for bad, _ in results) and areas == areas_g
                  and ('g' in modes) == want_gfx and (how == 'forced' or mode_after == 1))
            failures += not ok
            print('%-18s walk %d open %s: area0 %#06x x%3d, area1 %#06x x%3d, page %d/%d  %s  prints %s, after %d  %s' % (
                state, w, oname, s0, l0, s1, l1, access, shown,
                ' '.join('p%d %d bad/%d text' % (i + 1, bad, t) for i, (bad, t) in enumerate(results)),
                modes, mode_after, 'OK' if ok else 'FAIL'))
            if not ok:
                sheet = Image.new('RGB', (1280, 400 * len(text)))
                for i, (t, g) in enumerate(zip(text, gfx)):
                    sheet.paste(t, (0, 400 * i)); sheet.paste(g, (640, 400 * i))
                sheet.save(os.path.join(OUT, '%s_walk%d_%s.png' % (state, w, oname)))
    print('failures:', failures)
    return failures


if __name__ == '__main__':
    args = sys.argv[1:]
    how = 'forced'
    if '--script' in args:
        args.remove('--script'); how = 'script'
    sys.exit(1 if main(args or DEFAULT_STATES, how) else 0)
