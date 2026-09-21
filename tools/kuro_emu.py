"""Drive Kuro no Ken in np21debug_x64.exe: input, screenshots, and closed-loop
movement using the player's position read straight from emulated RAM.

The emulator runs far faster than real hardware, so timed key-holds overshoot
unpredictably. Instead, walk_to() taps a direction with a hold sized to the
remaining distance, re-reads the position, and repeats until it's close enough.

    from kuro_emu import Emu
    emu = Emu()
    emu.pos()                     # (x, y)
    emu.walk_to(x=0x100)          # move horizontally only
    emu.walk_to(0x100, 0x1d0)     # x first, then y
    emu.press('SPACE')            # confirm / advance text
    emu.shot('scratch_emu/now.png')

Coordinates and RAM layout (found by differential RAM scans, 2026-09-18):
    16d8:0136/0138   camera scroll X/Y (= player - anchor offset, until clamped at a map edge)
    16d8:01aa+4/+6   player X/Y (object slot 0; pos() subtracts OBJ_ANCHOR so the two agree)
    16d8:0951  str   current map resource, e.g. "d\\ysk1" (manor grounds), "d\\ysk2"
                     (manor gate). Coordinates are per map.
Movement is about 3.3 units per 10 ms of key hold. Pushing into a wall slides
the player along it, so a stalled axis with the other axis moving means "wall".
"""
import ctypes
import ctypes.wintypes
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
# Appended, not prepended: Possessioner/ has its own rominfo.py/reinsert.py, which
# must never shadow this project's.
sys.path.append(os.path.join(HERE, '..', 'romtools'))
sys.path.append(os.path.join(HERE, '..', 'Possessioner'))  # bp_bridge.DebugBridge
from win32_bridge import find_windows, post_key, capture_window_image  # noqa: E402
from bp_bridge import DebugBridge  # noqa: E402

BD_SEG = 0x16d8          # BD.BIN (resident engine code + variables)
PLAYER_X = (BD_SEG << 4) + 0x136
PLAYER_Y = (BD_SEG << 4) + 0x138
MAP_NAME = (BD_SEG << 4) + 0x951

NOCLIP_ADDR = (BD_SEG << 4) + 0x31c2   # `jae 0x321c` after the map-collision call
NOCLIP_ORIG = b'\x73\x58'

# Shinobu's stats (words). Found by scanning for her max HP/MP (192/225) and
# confirmed by writing HP mid-battle; the others in this block are unidentified.
STAT_HP = (BD_SEG << 4) + 0x1007
STAT_HP_MAX = (BD_SEG << 4) + 0x100b
STAT_HP_COPY = (BD_SEG << 4) + 0x100d   # mirrors HP; write both
STAT_MP = (BD_SEG << 4) + 0x100f
STAT_MP_MAX = (BD_SEG << 4) + 0x1013

NP2_DIR =os.path.join(HERE, '..', 'romtools', 'np2debug')
STATE_DIR = os.path.join(HERE, 'states')
SCRATCH_SLOT = 9
CMD_RESET, CMD_SAVE0, CMD_LOAD0 = 40101, 40201, 40251   # np21debug menu command IDs
TITLE_ROWS_Y = [25, 41, 57, 73, 89]                      # title menu rows (display pixels)
LAUNCHER_ROWS_Y = [64, 88, 112, 136, 160]                # cold-boot launcher rows (display pixels)
LAUNCHER_BOX_EDGE = (153, 136, 170)

MAP_SEG_PTR = (BD_SEG << 4) + 0xa70    # word: segment of the current map's data (trigger zones)
OBJ_TABLE = (BD_SEG << 4) + 0x1aa   # slot 0 = player, stride 0xf0
OBJ_STRIDE = 0xf0
OBJ_SLOTS = 8
OBJ_ANCHOR = (0x28, 0x1c)           # object coords = pos() + this (sprite anchor vs camera)

TVRAM = 0xA0000
TEXT_PAGE_CELLS = 0x800             # second text page starts at A000:1000
PROMPT_ICON_FRAMES = {(0x56, h) for h in range(0x22, 0x2e)}  # animated "press a key" icon
MENU_CURSOR = (0x56, 0x21)          # the triangle cursor in battle/field menus
GLYPH = '□'                    # stand-in for the game's own glyphs
BAD = '�'
DOS_PROMPT = 'B-DRKNS>'
# Box geometry varies (plain box: text from col 13, prompt icon at 65; portrait box:
# text from col 21, icon at ~74), so overflow is judged against the prompt icon's
# column. Lines after a newline start 2 cols right of the first (the script's \i2 after
# the speaker name), so a full LINE_MAX (48) line ends 2 cols before the icon.
STALE_TEXT_SECS = 1.5               # unchanged, icon-less text older than this is leftover
ICON_MARGIN = 1                     # text must end at least this many cols before the icon


def _is_char(cell):
    """A printed, non-space character: kanji-ROM half-width (09 xx, dialogue) or
    plain ASCII (xx 00, the battle module)."""
    lo, hi = cell
    return (lo == 0x09 and 0x20 < hi < 0x7f) or (hi == 0 and 0x20 < lo < 0x7f)


def _is_kanji(cell):
    """Left half of a full-width character (the game's own 56 xx glyphs excluded)."""
    lo, hi = cell
    return hi != 0 and 0x01 <= lo <= 0x5d and lo not in (0x09, 0x0a, 0x0b, 0x56)


def _jis_to_sjis(j1, j2):
    s1 = (j1 + 1) // 2 + (0x70 if j1 <= 0x5e else 0xb0)
    s2 = j2 + (0x1f if j1 % 2 else 0x7e)
    if s2 >= 0x7f and j1 % 2:
        s2 += 1
    return bytes([s1, s2])


KEYS = {
    'UP': 0x68, 'DOWN': 0x62, 'LEFT': 0x64, 'RIGHT': 0x66,  # numpad 8/2/4/6
    'SPACE': 0x20,   # confirm / advance text
    'ESC': 0x1B,     # cancel
    'ENTER': 0x0D,   # avoid in menus: tends to register twice
}

UNITS_PER_SEC = 330      # measured movement speed while a direction is held
MIN_HOLD = 0.005         # ~2 units
MAX_HOLD = 0.12          # cap per tap so long walks re-check often


class Blocked(Exception):
    """walk_to() couldn't make progress: a wall, an NPC, or a dialogue box."""


GAME_DISK_NAME = 'Kuro no Ken'   # substring of the mounted SASI #0 image's file name


def _mounted_disks(hwnd):
    """The Disks-menu labels of an np21 window, e.g. 'SASI #0: Foo.hdi'."""
    user32 = ctypes.windll.user32
    menu = user32.GetMenu(hwnd)
    labels = []
    for i in range(user32.GetMenuItemCount(menu)):
        sub = user32.GetSubMenu(menu, i)
        for j in range(user32.GetMenuItemCount(sub) if sub else 0):
            buf = ctypes.create_unicode_buffer(260)
            user32.GetMenuStringW(sub, j, buf, 260, 0x400)
            if buf.value.startswith(('SASI', 'SCSI', 'FDD')):
                labels.append(buf.value)
    return labels


def find_game_window():
    """The np21 window with Kuro no Ken mounted. Other projects run their own np21
    copies at the same time (e.g. romtools/np2debug_glodia), so never just take
    the first 'Neko Project 21' window."""
    for hwnd in find_windows('Neko Project 21', class_name='NP2-MainWindow'):
        if any(GAME_DISK_NAME in label for label in _mounted_disks(hwnd)):
            return hwnd
    return None


def launch_emulator(wait=20):
    """Start np21debug with the patched Kuro no Ken disk (detached, so it outlives
    the calling shell) and return its window."""
    import subprocess
    sys.path.insert(0, HERE)
    from rominfo import DEST_DISK
    exe = os.path.join(NP2_DIR, 'np21debug_x64.exe')
    subprocess.Popen([exe, os.path.abspath(os.path.join(HERE, DEST_DISK))], cwd=NP2_DIR,
                     creationflags=0x00000008 | 0x00000200, close_fds=True)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        hwnd = find_game_window()
        if hwnd:
            return hwnd
    raise RuntimeError('emulator did not come up with the Kuro no Ken disk')


class Emu:
    units_per_sec = UNITS_PER_SEC
    min_hold = MIN_HOLD
    nudge = 0.02            # shortest tap that reliably moves the player one step

    def __init__(self):
        self.hwnd = find_game_window()
        if self.hwnd is None:
            raise RuntimeError(f'no np21 window has a disk named *{GAME_DISK_NAME}* mounted; '
                               'start one with kuro_emu.launch_emulator()')
        # Memory access only - no breakpoint activation, so nothing about run state changes.
        self.mem = DebugBridge.attach(self.hwnd, 0, activate=False)
        self._last_lines, self._lines_since = None, 0.0   # for state()'s stale-text rule

    # --- RAM -----------------------------------------------------------------
    def read(self, phys, size):
        return self.mem.read_phys(phys, size)

    def word(self, phys):
        b = self.read(phys, 2)
        return b[0] | b[1] << 8

    def pos(self):
        """The player's position: object slot 0's anchor minus OBJ_ANCHOR, i.e. the
        same numbers as the camera scroll (16d8:0136/0138) wherever the camera
        isn't clamped at a map edge. The camera stops following near edges, so
        it's only a stand-in for the player in the middle of a map."""
        return (self.word(OBJ_TABLE + 4) - OBJ_ANCHOR[0],
                self.word(OBJ_TABLE + 6) - OBJ_ANCHOR[1])

    def camera(self):
        return self.word(PLAYER_X), self.word(PLAYER_Y)

    def map_name(self):
        raw = self.read(MAP_NAME, 12).split(b'\x00')[0]
        return raw.decode('ascii', 'replace').replace('d\\', '')

    def objects(self):
        """Active map objects (NPCs etc.) as dicts with x/y in the same space as pos().
        Slot 0 is the player; empty slots have a zero type word."""
        out = []
        for i in range(1, OBJ_SLOTS):
            r = self.read(OBJ_TABLE + i * OBJ_STRIDE, 8)
            kind = r[0] | r[1] << 8
            if not kind:
                continue
            out.append({'slot': i, 'kind': kind,
                        'x': (r[4] | r[5] << 8) - OBJ_ANCHOR[0],
                        'y': (r[6] | r[7] << 8) - OBJ_ANCHOR[1]})
        return out

    def zones(self):
        """The current map's trigger rectangles, in pos() coordinates. Two tables in
        the map data segment (word at 16d8:0a70): 'bump' zones fire when you walk
        into them (BD.BIN 0x440d: doors, signs, chests), 'step' zones when you
        stand in them (0x4475: exits, walk-on events). 10-byte entries: x1, y1, x2,
        y2 (object-anchor coords), script index, flags (0x80 = disabled)."""
        seg = self.word(MAP_SEG_PTR)
        base = seg << 4
        out = []
        for kind, ptr_at, count_at in (('bump', 4, 6), ('step', 8, 0xa)):
            ptr, count = self.word(base + ptr_at), self.word(base + count_at)
            for i in range(min(count, 200)):
                a = base + ptr + i * 10
                x1, y1, x2, y2 = (self.word(a + k) for k in (0, 2, 4, 6))
                script, flags = self.read(a + 8, 2)
                out.append({'kind': kind, 'index': i, 'script': script,
                            'enabled': not flags & 0x80,
                            'x1': x1 - OBJ_ANCHOR[0], 'x2': x2 - OBJ_ANCHOR[0],
                            'y1': y1 - OBJ_ANCHOR[1], 'y2': y2 - OBJ_ANCHOR[1]})
        return out

    def map_sig(self):
        """A fingerprint of the current map: its trigger-zone layout (without the
        enabled flags, which events flip). Neither the map-data segment (reused
        across maps) nor the resource name at 0951 (also set by battle and script
        loads) identifies the map reliably; the zone layout does."""
        return tuple((z['kind'], z['x1'], z['y1'], z['x2'], z['y2'], z['script'])
                     for z in self.zones())

    def npc(self, slot):
        return next((o for o in self.objects() if o['slot'] == slot), None)

    # --- screen text ---------------------------------------------------------
    def text_cells(self):
        """The displayed text page as 25 rows of 80 (lo, hi) cells.

        The game double-buffers text VRAM: page 0 at A000:0000 (field, dialogue)
        and page 1 at A000:1000 (battle), switching the text GDC's start address
        somewhere outside BD.BIN. Rather than chase that, the displayed page is
        whichever one's printed cells line up with bright pixels on screen; the
        hidden page keeps stale text, so a page nobody can see reads as blank."""
        raw = self.read(TVRAM, 0x2000)
        pages = []
        for base in (0, TEXT_PAGE_CELLS):
            cells = [(raw[2 * (base + i)], raw[2 * (base + i) + 1]) for i in range(2000)]
            printed = [i for i, cell in enumerate(cells) if _is_char(cell) or _is_kanji(cell)]
            pages.append((cells, printed))
        scores = [self._lit_fraction(printed) if printed else -1 for _, printed in pages]
        best = max((0, 1), key=lambda p: scores[p])
        if scores[best] >= 0.5:
            chosen = pages[best][0]
        else:
            # Nothing printed is visible. Keep the game's own glyphs (fill rows, the
            # prompt icon) from page 0 but drop its stale text.
            chosen = [c if c[0] in (0x56, 0xd6) else (0x20, 0) for c in pages[0][0]]
        return [chosen[r * 80:(r + 1) * 80] for r in range(25)]

    def _lit_fraction(self, cells, sample=40):
        """Fraction of the given text cells whose 8x16 screen area shows white text
        (3+ pure-white pixels). The text layer draws from the fixed digital palette,
        so its white is exactly 255,255,255; the graphics layer's 4-bit analog
        palette tops out a step below in practice (stone highlights are 238,238,238),
        so bright scenery behind a hidden page's stale text doesn't count."""
        img = self.image()
        step = max(1, len(cells) // sample)
        picked = cells[::step]
        lit = 0
        for i in picked:
            row, col = divmod(i, 80)
            box = img.crop((col * 8, row * 16, col * 8 + 8, row * 16 + 16))
            lit += sum(1 for px in box.getdata() if px == (255, 255, 255)) >= 3
        return lit / len(picked)

    def screen_text(self):
        """Text VRAM decoded to 25 strings of 80 columns. The game prints dialogue
        with kanji-ROM half-width cells (09 xx), full-width text as JIS pairs;
        its own glyphs (56 xx: box fill, prompt icon) become GLYPH, and plain
        ASCII cells (only DOS writes those) are kept as-is."""
        rows = []
        for cells in self.text_cells():
            out = []
            c = 0
            while c < 80:
                lo, hi = cells[c]
                if lo == 0x09 and 0x20 <= hi < 0x7f:
                    out.append(chr(hi))
                elif hi == 0:
                    out.append(chr(lo) if 0x20 <= lo < 0x7f else ' ')
                elif lo == 0x56:
                    out.append(GLYPH)
                elif lo & 0x80:
                    out.append(GLYPH)           # right half of a glyph whose left was lost
                elif 0x01 <= lo <= 0x5f and c + 1 < 80:
                    try:
                        out.append(_jis_to_sjis(lo + 0x20, hi).decode('shift_jis'))
                    except UnicodeDecodeError:
                        out.append(BAD)
                    out.append('')              # full-width: occupies two cells
                    c += 1
                else:
                    out.append(BAD)
                c += 1
            rows.append(''.join(out))
        return rows

    def dialogue(self):
        """The open text box as {'lines': [...], 'waiting': bool, 'cols': [(first, last)...],
        'icon_col': int|None}, or None. waiting = the "press a key" icon is showing;
        its column marks the box's right edge (the box moves right when a portrait shows)."""
        cells = self.text_cells()
        rows = self.screen_text()
        lines, spans, waiting, icon_col, icon_row = [], [], False, None, 24
        for r in range(25):
            for c in range(80):
                if cells[r][c] in PROMPT_ICON_FRAMES:
                    waiting, icon_col, icon_row = True, c, r
        # The icon sits on the box's last row. Anything below it is not part of this
        # page: an overfull earlier page can leave a line drawn under the box that the
        # game never clears (seen: "inside." from 03YSK01A 0x131f on every later page).
        for r in range(icon_row + 1):   # fill rows (all 56 xx glyphs) contribute no 'used' cells
            used = [c for c in range(80) if _is_char(cells[r][c]) or _is_kanji(cells[r][c])]
            if used:
                lines.append(rows[r].replace(GLYPH, ' ').rstrip())
                spans.append((min(used), max(used)))
        if not lines and not waiting:
            return None
        return {'lines': lines, 'waiting': waiting, 'cols': spans, 'icon_col': icon_col}

    def menu(self):
        """The menu with the cursor glyph (56 21, a triangle), as {'row', 'col',
        'item', 'items': [(row, text)...]} or None. Items are the rows whose text
        starts in the column right after the cursor."""
        cells = self.text_cells()
        rows = self.screen_text()
        for r in range(25):
            for c in range(79):
                if cells[r][c] == MENU_CURSOR:
                    col = c + 2
                    # items may be half-width (English build) or full-width (攻撃, 魔法...)
                    items = [(rr, rows[rr][col:].split('□')[0].strip()) for rr in range(25)
                             if (_is_char(cells[rr][col]) or _is_kanji(cells[rr][col]))
                             and not _is_char(cells[rr][col - 1])
                             and not _is_kanji(cells[rr][col - 1])]
                    item = rows[r][col:].split('□')[0].strip()
                    return {'row': r, 'col': col, 'item': item, 'items': items}
        return None

    def state(self):
        """'dos' (game exited/crashed to the prompt), 'battle' (the HP/MP status panel
        is up), 'menu' (a cursor menu), 'dialogue', or 'field'."""
        rows = self.screen_text()
        for row in rows:
            if DOS_PROMPT in row or 'Abnormal' in row or 'Divide' in row:
                return 'dos'
        if any(row.lstrip().startswith('HP ') for row in rows) and \
                any(row.lstrip().startswith('MP ') for row in rows):
            return 'battle'
        if self.menu():
            return 'menu'
        d = self.dialogue()
        if d and not d['waiting']:
            # Text with no prompt icon: a page still being typed out, or leftovers the
            # game never cleared. Leftovers don't change, so after STALE_TEXT_SECS of
            # identical text it counts as the field.
            now = self.clock()
            if d['lines'] != self._last_lines:
                self._last_lines, self._lines_since = d['lines'], now
            elif now - self._lines_since > STALE_TEXT_SECS:
                return 'field'
        if d:
            return 'dialogue'
        return 'field'

    # --- input / output ------------------------------------------------------
    # The backend primitives. CoreEmu (kuro_core.py) overrides these to run the
    # game in-process on np2core, in emulated frames instead of wall-clock time.
    def wait(self, seconds):
        time.sleep(seconds)

    def clock(self):
        return time.time()

    def write(self, phys, data):
        self.mem.write_phys(phys, bytes(data))

    def image(self):
        """The emulated display (640x400 client area, RGB)."""
        img = capture_window_image(self.hwnd).convert('RGB')
        r = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        p = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(self.hwnd, ctypes.byref(p))
        ox, oy = p.x - r.left, p.y - r.top
        return img.crop((ox, oy, ox + 640, oy + 400))

    def tap(self, key, hold=0.08):
        post_key(self.hwnd, KEYS[key], hold=hold)

    def press(self, key, times=1, gap=0.35):
        """Menu/text input. Short, spaced presses so nothing auto-repeats."""
        for _ in range(times):
            self.tap(key, 0.06)
            self.wait(gap)

    def shot(self, path):
        self.image().save(path)
        return path

    # --- cheats (live RAM patches to resident BD.BIN code) -----------------------
    def set_noclip(self, on=True):
        """Walk through walls. BD.BIN 0x3167 is the player's per-step check: event
        trigger (0x440d), then map collision (0x456a, CF clear = wall), then NPCs
        (0x44b8). NOPing the `jae` after the map test skips only the walls, so
        exits, event triggers and NPC bumps still work. Lost on reset / state load
        from before it was set; reapply after either."""
        cur = self.read(NOCLIP_ADDR, 2)
        want = b'\x90\x90' if on else NOCLIP_ORIG
        if cur not in (NOCLIP_ORIG, b'\x90\x90'):
            raise RuntimeError(f'unexpected bytes at BD.BIN 0x31c2: {cur.hex()}')
        self.write(NOCLIP_ADDR, want)

    def heal(self):
        """Refill Shinobu's HP and MP (works mid-battle; the panel updates next turn)."""
        hp_max, mp_max = self.word(STAT_HP_MAX), self.word(STAT_MP_MAX)
        for addr in (STAT_HP, STAT_HP_COPY):
            self.write(addr, hp_max.to_bytes(2, 'little'))
        self.write(STAT_MP, mp_max.to_bytes(2, 'little'))

    # --- emulator control ----------------------------------------------------
    def command(self, cmd_id):
        ctypes.windll.user32.PostMessageW(self.hwnd, 0x111, cmd_id, 0)   # WM_COMMAND

    def reset(self):
        self.command(CMD_RESET)

    def save_state(self, name):
        """Save a named emulator state under states/. Goes through the emulator's
        slot SCRATCH_SLOT (np21.S09 is shared by every project using np21debug)."""
        slot_file = os.path.join(NP2_DIR, f'np21.S{SCRATCH_SLOT:02d}')
        before = os.path.getmtime(slot_file) if os.path.exists(slot_file) else 0
        self.command(CMD_SAVE0 + SCRATCH_SLOT)
        for _ in range(100):
            self.wait(0.1)
            if os.path.exists(slot_file) and os.path.getmtime(slot_file) != before:
                break
        self.wait(0.5)   # let the write finish
        os.makedirs(STATE_DIR, exist_ok=True)
        dest = os.path.join(STATE_DIR, name + '.state')
        shutil.copyfile(slot_file, dest)
        return dest

    def load_state(self, name):
        """Load a state saved with save_state(). RAM (including already-loaded
        scripts) comes from the state; files read afterwards come from the
        current disk image, so reload from before the scene you're testing."""
        src = os.path.join(STATE_DIR, name + '.state')
        shutil.copyfile(src, os.path.join(NP2_DIR, f'np21.S{SCRATCH_SLOT:02d}'))
        self.command(CMD_LOAD0 + SCRATCH_SLOT)
        self.wait(1.5)

    def title_cursor(self):
        """Row of the title-menu cursor (0 Opening, 1 New Game, 2 Continue,
        3 Color, 4 Exit), or None if the title menu isn't showing."""
        img = self.image().convert('L')
        best, best_row = 0, None
        for r, y in enumerate(TITLE_ROWS_Y):
            score = sum(1 for x in range(15, 31) for dy in range(-4, 5)
                        if img.getpixel((x, y + dy)) > 150)
            if score > best:
                best, best_row = score, r
        return best_row if best > 5 else None

    def launcher_cursor(self):
        """Row of the boot launcher's highlight (0 Load, 1 New Game, 2 Switch
        Monitor, 3 Switch Audio, 4 Extra Info), or None if it isn't showing. The
        launcher appears on a cold start, drawn in graphics; the highlight box's
        left edge is (153,136,170) around x=257."""
        img = self.image()
        scores = [sum(1 for x in range(253, 261) for dy in range(-10, 11)
                      if img.getpixel((x, y + dy)) == LAUNCHER_BOX_EDGE)
                  for y in LAUNCHER_ROWS_Y]
        best = max(range(len(scores)), key=lambda i: scores[i])
        return best if scores[best] > 10 else None

    def title_select(self, target, timeout=60):
        """Wait for the title menu, move the cursor to `target` and confirm with
        Space (Enter double-registers here)."""
        end = self.clock() + timeout
        while self.clock() < end:
            lrow = self.launcher_cursor()
            if lrow is not None:
                # cold boot: the launcher comes first; its New Game leads to the title
                if lrow == 1:
                    self.press('SPACE', gap=2.0)
                else:
                    self.press('UP' if lrow > 1 else 'DOWN', gap=0.5)
                continue
            row = self.title_cursor()
            if row == target:
                self.wait(0.5)
                self.press('SPACE')
                return True
            if row is None:
                self.wait(1)
                continue
            self.press('UP' if row > target else 'DOWN', gap=0.6)
        raise Blocked(f'title menu: could not select row {target}')

    # --- movement ------------------------------------------------------------
    def _walk_axis(self, axis, target, tol, settle, max_taps):
        idx = 0 if axis == 'x' else 1
        other = 1 - idx
        stalls = 0
        for _ in range(max_taps):
            cur = self.pos()
            delta = target - cur[idx]
            if abs(delta) <= tol:
                return cur
            if axis == 'x':
                key = 'RIGHT' if delta > 0 else 'LEFT'
            else:
                key = 'DOWN' if delta > 0 else 'UP'
            hold = min(MAX_HOLD, max(self.min_hold, abs(delta) / self.units_per_sec * 0.9))
            self.tap(key, hold)
            self.wait(settle)
            new = self.pos()
            moved = new[idx] - cur[idx]
            if moved == 0 or (moved > 0) != (delta > 0):
                stalls += 1
                if stalls >= 3:
                    slid = new[other] != cur[other]
                    raise Blocked(f'{axis} stuck at {new[idx]:#x} (target {target:#x})'
                                  + (' - sliding along a wall' if slid else ' - no movement '
                                     '(wall, NPC, or a dialogue/menu is open)'))
            else:
                stalls = 0
        raise Blocked(f'{axis} did not converge on {target:#x}, at {self.pos()[idx]:#x}')

    def exit_via(self, key, max_taps=80, settle=1.5):
        """Walk in one direction until the map changes (through a door/edge).
        Returns the new map name. Stand in line with the exit first."""
        start = self.map_sig()
        for _ in range(max_taps):
            before = self.pos()
            self.tap(key, max(0.03, self.nudge))
            self.wait(0.25)
            if self.map_sig() != start:
                self.wait(settle)
                return self.map_name()
            if self.pos() == before:
                raise Blocked(f'stopped at {before} heading {key} without leaving {self.map_name()}')
        raise Blocked(f'no exit found heading {key} from {self.map_name()}')

    def walk_to(self, x=None, y=None, tol=2, settle=0.15, max_taps=60, y_first=False):
        """Walk to (x, y), one axis at a time. Omit an axis to leave it alone."""
        order = [('y', y), ('x', x)] if y_first else [('x', x), ('y', y)]
        for axis, target in order:
            if target is not None:
                self._walk_axis(axis, target, tol, settle, max_taps)
        return self.pos()


if __name__ == '__main__':
    emu = Emu()
    x, y = emu.pos()
    print(f'map {emu.map_name()}  x={x:#x} y={y:#x}')
