"""Kuro no Ken on np2core: the headless, in-process PC-98 emulator in
romtools/np2core (see romtools/CLAUDE.md).

CoreEmu is a drop-in replacement for kuro_emu.Emu. Every reader (positions,
zones, text boxes, menus, state detection) and every walking/fighting/reading
routine in kuro_test works unchanged; only the backend primitives differ:

    Emu (np21debug GUI)              CoreEmu (np2core)
    wall-clock sleeps                emulated frames (exact, ~50x real time)
    PostMessage key presses          PC-98 scancodes held for N frames
    window screenshots               the composed display, pixel-exact
    np21.S09 via WM_COMMAND          in-memory states (+ files under states/)
    shared GUI window                private to this process, no interference

    from kuro_core import CoreEmu
    from kuro_test import Tester
    t = Tester(emu=CoreEmu())      # boots the patched disk
    t.emu.new_game()                # launcher -> title -> New Game
    t.run_step({'op': 'wait_field'})

The disk image is loaded into RAM once; the .hdi on disk is never written, so
rebuilding the patched disk mid-session is safe (swap it in with reload_disk()).
"""
import os
import sys
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, os.path.dirname(HERE))          # so `romtools` imports as a package
from romtools.np2core import Machine, FRAMES_PER_SECOND  # noqa: E402

import kuro_emu  # noqa: E402
from kuro_emu import Emu, STATE_DIR  # noqa: E402

# PC-98 scancodes. The game moves with the numpad (8/2/4/6), like the GUI setup.
SCANCODES = {
    'UP': 0x43, 'DOWN': 0x4B, 'LEFT': 0x46, 'RIGHT': 0x48,   # numpad 8 2 4 6
    'SPACE': 0x34, 'ESC': 0x00, 'ENTER': 0x1C,
}


def patched_disk():
    sys.path.insert(0, HERE)
    from rominfo import DEST_DISK
    return os.path.abspath(os.path.join(HERE, DEST_DISK))


class CoreEmu(Emu):
    # Movement speed in emulated time, measured with calibrate(); walk_to() uses it
    # to size key holds.
    units_per_sec = 33       # measured: 31-34 units per emulated second
    min_hold = 1 / FRAMES_PER_SECOND
    nudge = 3 / FRAMES_PER_SECOND      # a 1-frame press doesn't always register as a step

    def __init__(self, hdd=None, boot_frames=0):
        self.hdd = hdd or patched_disk()
        # Kuro no Ken's boot disk loads VEM486 (386-only EMS driver); the GUI setup
        # it's known to run on uses 13 MB of extended memory.
        self.m = Machine(self.hdd, cpu='386', extmem_mb=13)
        self.hwnd = None
        self.mem = None
        self._last_lines, self._lines_since = None, 0.0
        self._states = {}
        if boot_frames:
            self.m.run(boot_frames)

    # --- backend primitives (see Emu) ------------------------------------------
    def read(self, phys, size):
        return self.m.read(phys, size)

    def write(self, phys, data):
        self.m.write(phys, bytes(data))

    def wait(self, seconds):
        self.m.run(max(1, round(seconds * FRAMES_PER_SECOND)))

    def clock(self):
        return self.m.frame / FRAMES_PER_SECOND

    def image(self):
        return self.m.screenshot().convert('RGB')

    def text_cells(self):
        """The text page the GDC is actually displaying (np2core reports its start
        cell), so no pixel heuristic: 0 in the field and dialogue, 0x800 in battle."""
        start = self.m.text_display_start() & 0xfff
        raw = self.read(kuro_emu.TVRAM + 2 * start, 80 * 25 * 2)
        cells = [(raw[2 * i], raw[2 * i + 1]) for i in range(2000)]
        return [cells[r * 80:(r + 1) * 80] for r in range(25)]

    def tap(self, key, hold=0.08):
        code = SCANCODES[key]
        self.m.key(code, True)
        self.m.run(max(1, round(hold * FRAMES_PER_SECOND)))
        self.m.key(code, False)
        self.m.run(2)        # let the game's polling see the release

    # --- emulator control -----------------------------------------------------
    def reset(self):
        self.m.reset()

    def command(self, cmd_id):
        raise NotImplementedError('np21debug menu commands have no np2core equivalent')

    def save_state(self, name):
        """Keep a named state in memory, and on disk (states/<name>.np2core) so
        later runs and routes can start from it."""
        data = self.m.save_state()
        self._states[name] = data
        os.makedirs(STATE_DIR, exist_ok=True)
        path = os.path.join(STATE_DIR, name + '.np2core')
        with open(path, 'wb') as f:
            f.write(zlib.compress(data, 1))
        return path

    def load_state(self, name):
        """Restore a state. RAM (scripts already loaded) comes from the state; files
        the game reads later come from the disk image currently in RAM."""
        data = self._states.get(name)
        if data is None:
            with open(os.path.join(STATE_DIR, name + '.np2core'), 'rb') as f:
                data = zlib.decompress(f.read())
            self._states[name] = data
        self.m.load_state(data)
        self._last_lines = None

    def reload_disk(self, path=None):
        """Swap a rebuilt disk image into the running machine (same size only)."""
        with open(path or self.hdd, 'rb') as f:
            self.m.set_hdd_image(f.read())

    # --- helpers --------------------------------------------------------------
    def new_game(self, timeout=120):
        """From power-on: through the launcher and title menu into a new game."""
        self.title_select(1, timeout=timeout)

    def calibrate(self, key='RIGHT', frames=10):
        """Units moved per emulated second while `key` is held (field only)."""
        x0 = self.pos()[0 if key in ('LEFT', 'RIGHT') else 1]
        self.tap(key, frames / FRAMES_PER_SECOND)
        self.m.run(10)
        x1 = self.pos()[0 if key in ('LEFT', 'RIGHT') else 1]
        return abs(x1 - x0) * FRAMES_PER_SECOND / frames


if __name__ == '__main__':
    e = CoreEmu()
    e.m.run(1800)
    print('\n'.join(r for r in e.screen_text() if r.strip()))
    e.shot(os.path.join(HERE, 'scratch_emu', 'core_boot.png'))
    print('launcher', e.launcher_cursor(), 'title', e.title_cursor())
