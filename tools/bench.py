"""Text render bench: make the game display an arbitrary script string on demand.

The point is to check how a line of the translation *actually looks in the game's own
text box* without having to reach the place where it is spoken. The route in:

  - Every map script file ends with a word table of script-block addresses; the live
    pointer to it is `[16d8:0932]` in segment `[16d8:09fe]` (found by disassembling
    the per-step trigger check at BD.BIN 0x3167).
  - A bump-zone entry (10 bytes: x1, y1, x2, y2 as words, script index, flags) names a
    block by index into that table. BD.BIN 0x440d tests the rectangle against the tile
    the player is stepping into.
  - So: write a synthetic block `40 02 <string> 00 83` into the free space past the end
    of the loaded map script, point a table slot at it, move bump zone 0 onto the
    player, and take one step. The engine runs the block and prints the string.

Readback is np2core's text layer, so what comes back is exactly what a player would
read: the engine's own line wrapping, page breaks and control-code handling.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from kuro_core import CoreEmu          # noqa: E402
from kuro_test import Tester           # noqa: E402

SEG = 0x26d80          # script segment 26d8
BD = 0x16d80           # BD.BIN, resident at 16d8
TEXT_PAGES = (0xa0000, 0xa1000)
FF = bytes([0x5c, 0x66])       # "\f" end of page
NL = bytes([0x5c, 0x6e])       # "\n" next line
BLOCK_AT = 0xd00       # free space past the map script inside slot 0
SCRIPT_IDX = 3         # the table slot we hijack
CALL_OPEN = bytes([0x04, 0x06, 0x30])    # what real dialogue blocks start with
CALL_END = bytes([0x09, 0x15, 0x30])     # ...and end with
BOX_COLS = 50          # measured with a ruler string: the box is 50 wide, 5 rows,
BOX_ROWS = 5           # at screen column 13. A 6th line is silently dropped.


class Bench:
    def __init__(self, state, hdd=None):
        self.e = CoreEmu(hdd=hdd)
        self.t = Tester(emu=self.e, log=lambda *a: None)
        self.e.load_state(state)
        self.e.set_noclip(True)
        self.e.heal()
        self.base = self.e.m.save_state()

    def _word(self, phys):
        return int.from_bytes(self.e.read(phys, 2), 'little')

    def arm(self, script_byte):
        """Put bump zone 0 over the player, running script index `script_byte`."""
        e = self.e
        S = self._word(BD + 0x0a70) << 4
        tbl = S + self._word(S + 4)
        x, y = e.pos()
        ax, ay = x + 0x28, y + 0x1c          # anchor coords, as the zone tables use
        ent = (int.to_bytes(max(0, ax - 40), 2, 'little') + int.to_bytes(max(0, ay - 40), 2, 'little')
               + int.to_bytes(ax + 40, 2, 'little') + int.to_bytes(ay + 40, 2, 'little')
               + bytes([script_byte, 0]))
        e.write(tbl, ent)
        return {'zone_table': hex(tbl), 'count': self._word(S + 6), 'entry': ent.hex(' ')}

    def reset(self):
        self.e.m.load_state(self.base)
        self.e._last_lines = None
        self.e.set_noclip(True)
        self.e.heal()


class RenderBench(Bench):
    def map_script(self):
        """(filename, length) of the map script loaded in slot 0, by header match."""
        import glob
        head = self.e.read(SEG, 32)
        for p in glob.glob(os.path.join(os.path.dirname(__file__), '..',
                                        'original', 'decompressed', '*.SCN')):
            d = open(p, 'rb').read()
            if d[:32] == head:
                return os.path.basename(p), len(d)
        return None, None

    def free_at(self, need):
        """Somewhere in slot 0 past the end of the loaded script to put a block."""
        _, n = self.map_script()
        at = ((n or 0xd00) + 0x1f) & ~0xf
        assert at + need < 0x1800, 'no room in slot 0 for a %d-byte block' % need
        return at

    def table(self):
        """Live address of the map script's block-address table."""
        return (self._word(BD + 0x09fe) << 4) + self._word(BD + 0x0932)

    def clear_text(self):
        """Blank both text pages, so a readback can only show what this render drew."""
        blank = bytes([0x20, 0x00]) * 0x800
        for p in TEXT_PAGES:
            self.e.write(p, blank)

    def load_script(self, fn, base=0x1800):
        """Put a patched script into a slot ourselves, so its blocks can be run without
        reaching the map that loads it.

        The engine reads scripts out of this segment and does not care who put them
        there, so a file written into slot 1 behaves as if the game had loaded it. The
        common routines it calls (0x3006 open window, 0x3015 close) live outside the
        slot and are always resident, which is what makes this work from any map.
        """
        import glob
        from check_pointers import as_script
        path = os.path.join(os.path.dirname(__file__), '..', 'patched', fn)
        data = as_script(open(path, 'rb').read())
        assert data, 'could not read %s' % fn
        assert base + len(data) < 0x3d00, '%s is too big for slot %#06x' % (fn, base)
        self.e.write(SEG + base, data)
        return len(data)

    def run_block(self, addr, idx=SCRIPT_IDX, max_pages=8):
        """Run a block that is already in the loaded script, and read its pages.

        Same hijack as render(), except the table slot points at an existing address
        instead of a synthetic block, so the block plays exactly as it would in game.
        """
        self.reset()
        e = self.e
        # Most blocks are not standalone: they are called with the text window already
        # open, so running one cold leaves the engine in the wrong state and it quits.
        # Give it the frame a real caller would - open, call the block, close.
        at = self.free_at(12)
        e.write(SEG + at, CALL_OPEN + bytes([0x04]) + int.to_bytes(addr, 2, 'little') + CALL_END)
        e.write(self.table() + 2 * idx, int.to_bytes(at, 2, 'little'))
        self.arm(idx)
        self.clear_text()
        for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
            e.tap(k, 0.25)
            e.wait(0.6)
            if e.state() != 'field':
                break
        else:
            return []
        pages, last, stable = [], None, None
        quiet = 0
        for _ in range(max_pages * 30):
            e.wait(0.15)
            if e.state() == 'dos':
                break
            if not pages:
                quiet += 1
                if quiet > 20:        # nothing drawn in 3 s: this block shows no text
                    break
            d = e.dialogue() or {}
            lines = [l.rstrip() for l in (d.get('lines') or []) if l.strip()]
            if lines and lines == last:
                if lines != stable:
                    stable = lines
                    pages.append([l.strip() for l in lines])
                if d.get('waiting'):
                    self.clear_text()
                    e.tap('SPACE', 0.1)
                    e.wait(0.3)
                    last = stable = None
                    if len(pages) >= max_pages:
                        break
                    continue
            last = lines
            if e.state() == 'field' and stable is not None:
                break
        return pages

    def render(self, text, block_at=None, idx=SCRIPT_IDX, prologue=CALL_OPEN,
               epilogue=CALL_END, max_pages=8):
        """Print `text` (raw script bytes) in the game's text box; return its pages."""
        self.reset()
        e = self.e
        block_at = block_at or self.free_at(len(text) + len(prologue) + 8)
        e.write(SEG + block_at, prologue + bytes([0x40, 0x02]) + text + bytes([0]) + epilogue)
        e.write(self.table() + 2 * idx, int.to_bytes(block_at, 2, 'little'))
        self.arm(idx)
        self.clear_text()
        for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
            e.tap(k, 0.25)
            e.wait(0.6)
            if e.state() != 'field':
                break
        else:
            return None                       # the block never ran
        # The text is typed out a character at a time and the engine flips text pages
        # while doing it, so a single read can catch a half-drawn line. Only a snapshot
        # that comes back identical twice in a row counts as what the player sees.
        pages, last, stable = [], None, None
        for _ in range(max_pages * 40):
            e.wait(0.12)
            d = e.dialogue() or {}
            lines = [l.rstrip() for l in (d.get('lines') or []) if l.strip()]
            if lines and lines == last:
                if lines != stable:
                    stable = lines
                    pages.append(lines)
                if d.get('waiting'):          # prompt icon: page complete, turn it
                    self.clear_text()
                    e.tap('SPACE', 0.1)
                    e.wait(0.3)
                    last = stable = None
                    if len(pages) >= max_pages:
                        break
                    continue
            last = lines
            if e.state() == 'field' and stable is not None:
                break
        return pages


if __name__ == '__main__':
    b = RenderBench(sys.argv[1])
    ruler = b''.join(bytes(str(i % 10), 'ascii') for i in range(1, 91))
    tests = [b'Hello, bench test.' + FF,
             ruler + FF,
             b'Page one' + FF + b'Page two' + FF,
             NL.join([b'L1', b'L2', b'L3', b'L4', b'L5', b'L6']) + FF]
    for txt in tests:
        pages = b.render(txt)
        print(repr(txt[:34]), '->', b.e.state(), '%d page(s)' % len(pages or []))
        for p in pages or []:
            for l in p:
                print('    |' + l[:74])
            print('    ---')
