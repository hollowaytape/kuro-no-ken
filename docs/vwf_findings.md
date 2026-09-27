# Variable-width text: MB3N's graphics mode (feasibility, 2026-09-21)

Question: can dialogue be drawn with a variable-width font, the way glodia's
`vwf.py` does it? **Yes.** MB3N already has a graphics-VRAM text path equivalent to
glodia's. With an addressing fix it draws the dialogue box identically to text mode,
and the VWF is built on it (see the sections below). Still open: pixel-width
typesetting in `reinsert.py` and a readback for the verification tools.

Experiment: `python tools/gfx_text_experiment.py text` vs `... gfx 09 0f`
(screens go to `scratch_emu/`). Everything below was measured with it on
`r03_manor_inside`.

## Where text is drawn

Dialogue goes through **MB3N.BIN** ("MAKO-BIOS 3", resident at 12d7, `INT 40h`), not
BD.BIN: script op `40 02 <str> 00` -> BD 0x1f99 -> `AH=20h` -> MB3N 0x82c (print loop).

`cs:[0x828]` picks the output (**1 = text VRAM**, the default; **0 = graphics**). Script
op `41` sets it (BD 0x1fa9 -> `AH=26h`). In graphics mode MB3N:

- reads the same kanji-ROM glyphs (ports A1/A3/A5/A9) and ORs them into A800 through the
  GRCG in RMW mode, colour `[0x825]` - one byte per scanline for half-width (0xc31),
  a word for full-width (0xb75). Optional bold `[0x82b]`, drop shadow `[0x827]` (0xff = off).
  This is exactly the setup glodia's VWF shifts sub-byte.
- clears the window (0xa99) with a GRCG TDW fill in colour `[0x824]` (0xff = no clear).
- computes addresses (0x9a1) as `([0x810] + line*(16+[0x81e]))*80 + [0x80e] + col`,
  i.e. **`[0x810]` is a pixel row** in graphics mode but a text row in text mode.

The box setup is part of the print string: `\o13,17\w50,5` then `\c7\b0\i0\t0\f`.
`\t0` means no typing delay. A `\f` *inside* one string only resets and clears the window;
the wait between pages is the script's `\f\0 ; @\2` (op `3b`), which is why
`reinsert.py` separates pages that way.

## Why a plain mode switch draws garbage

The map scrolls with the GDC, and graphics VRAM is a **400-line ring (32000 bytes)**.
MB3N's vsync handler (0x186) loads the scroll from its shadow at `cs:0x68`: area 0 =
start `B` (bytes) for 296 lines, area 1 = the rest, starting at `B + 80*296 - 32000`.
So screen line y is at `B + 80*y`, minus 32000 once it passes the end of area 0.
In this state `B = 0x2188` and the box (text rows 17-21) straddles the wrap.
The box itself is graphics (palette 9 interior), drawn by BD with the wrap handled.

MB3N's graphics path knows nothing about `B` or the wrap. Fix, simulated in the
experiment with exec hooks:

1. at print entry / `\o`: window cell (col,row) -> `lin = B + row*16*80`,
   `[0x810] = lin // 80`, `[0x80e] = col + lin % 80`
2. wrap by -32000 when a pointer reaches `B + 80*len0`: line start (0x9c8), next
   scanline in the half/full-width blits (0xc79, 0xbc8), next row of the clear (0xacd)
3. fill colour `[0x824] = 9` (the box interior); `\b0` in the box string sets 0.

With that, both pages render the same as text mode: name line, `\i2` indent, the
engine's own wrap at 50 columns, page break, prompt icon (still gaiji on the text
layer) and box close. The graphics page did not flip and the scroll did not move while
the box was open.

## The addressing fix, in asm: `tools/mb3_gfx.py`

`mb3_gfx.patch(image)` turns the original MB3N image into one where graphics-mode text
is drawn where text mode would put it. Nothing turns graphics mode on yet, so on its own
the patch changes nothing the player sees (every hook is on a graphics-only branch).

- **rowaddr**: screen line -> VRAM offset from both display areas' start and length
  (MB3N's scroll shadow at `cs:0x68` / `cs:0x6c`).
- **0x9a6 (line start)**: in graphics mode the window row is still a *text* row (x16),
  so `\o13,17` and the box strings work unchanged. The original game never enables
  graphics mode (no script uses op `41`, 232 scripts walked; BD's only other `AH=26h`
  sets text mode), so nothing depended on the old pixel-row meaning. It also records
  where the line leaves area 0 (`cs:400c`) and the jump to area 1 (`cs:400e`).
- **0xb9b / 0xc56**: before each glyph scanline, step `di` into area 1 if it has left
  area 0. (Not at the `add di,4f/4e`: the shadow code rewrites those immediates.)
- **0xaa6 (clear)**: one `rowaddr` per scanline.
- **Pages**: when the map has just scrolled, the page on screen (`cs:7b`) and the page
  being drawn (`cs:7a`) differ. BD's box code sets the access page to the shown one
  around its drawing (AH=0Ah); the patch does the same around print (0x833/0x878),
  number print (0xb2c/0xb6e) and the AH=22h clear (0xa82/0xa89).

**Where the code lives:** past the end of MB3N's image. FAD loads BD at MB3N + 0x401
paragraphs whatever MB3N's size, so the image can grow from 0x3f49 to 0x4010 bytes.
That was checked by booting a disk with a 0x4010-byte image: BD stayed at 16d8, the tail
survived, and the game ran. In the original, those 199 bytes hold leftover loader code:
identical in 40 save states, and never read or written. **The 199 bytes are now full.**
The freed 32 bytes at 0x9a9 (behind the jump) are the only slack left.

**Verified** with `tools/test_mb3_gfx.py`. It renders the same two-page dialogue in text
mode and in patched graphics mode, then compares whole screens. The only allowed
difference is #fff text vs #eee. 25 cases were pixel-identical, box close included,
across 7 maps and several scroll positions each: the box straddling the area boundary
mid-line and at a line boundary, the box wholly in area 0, wholly in area 1, and access
page != shown page. The bench cannot run a block in area_25/28 (no room in the map
script) or area_12/31 (the zone doesn't fire). `mb3_gfx.patch()` also boots from a
rebuilt A.FA1 and runs into New Game.

Not handled: drop shadow (`[0x827]`) is not scroll-aware, and nothing sets it.

## The dialogue-only switch: `tools/dialogue_gfx.py` (99CMN) + `gfx_enter` (MB3N)

Boxes are opened and closed by the common script **99CMN.SCN**, which is resident at
26d8:3000, through its entry table:

| entry | routine | does |
|---|---|---|
| 0x3006 | 0x370e | **draws the box frame (op `b3`)**, then the window `\o13,17\w50,5` |
| 0x300c | 0x3782 | **frame**, then the portrait window `\o21,17\w50,5` |
| 0x3009 / 0x300f / 0x3063 | 0x371e / 0x3792 / 0x3ca5 | the same windows with *no frame* (text on the map, or into a box already up) |
| 0x3015 / 0x3018 | 0x37ff / 0x3800 | close: (wait), `\f \n`, end of block. BD removes the box. |
| 0x3012 | 0x37ac | location title, `\o26,3\w50,1` |

All of them end in the shared string `\c7\b0\i0\t0\f`.

The switch has to follow the *frame*. A graphics-mode clear paints the box's grey, so
graphics text with no frame under it leaves a grey slab on the map. So:

- the two frame-drawing opens get a wrapper: call the routine, then op `41 00 00 00`
  (graphics);
- the close routines and the title get a wrapper: op `41 00 01 00` (text), then the
  routine;
- the frameless opens are untouched, so they inherit the current mode.

The entry words and 99CMN's 9 internal calls and jumps to those routines point at the
wrappers. The wrappers are 38 bytes appended at 0x3cc1; the slot ends at 0x3d00, and those
bytes are zero in every save state checked. The game writes the map number into
99CMN at 0x3901-0x3902 (a `d\mk00` filename), which is why `apply_to_ram` writes only
changed bytes.

**BD: text mode at the end of every script run.** The sweep below first found 156 blocks
that open a framed box and end with op `83` without going through the close routines.
BD takes the box down either way, but graphics mode stayed on for whatever printed next.
Every run of the interpreter (BD 0x33b2, which loops until op 83 sets `[0x94d]`) leaves
through `push cs / pop es / ret` at 0x33ce. `dialogue_gfx.patch_bd` makes that a jump to
10 bytes at BD 0xfc00 that switch MB3N to text mode and then do the same. BD
0xfbb9-0xfefd is zero in the image, identical in 30 save states, and was never read or
written in 4 maps of play; 0xfefe-0xffff is in use (stack).

`\c7` means white on the text layer but palette 7 (a dim grey) in graphics, `\b0` means
palette 0, and MB3N's bold flag defaults to on. So **every graphics-mode print** starts
with `gfx_enter` (at 0x9a9, the freed space), which sets colour 0x0f, clear colour 9 and
no bold. A `\c` *inside* a dialogue string still takes effect for the rest of that
string. In the original, dialogue only ever uses `\c7`; other colours appear only in the
intro and ending scripts (00IPL, 27KKII00), which don't use the box routines.

**Build:** `python build.py --gfx-dialogue` (or `reinsert.py --gfx-dialogue`) writes the
patched MB3N.BIN and 99CMN.SCN into `patched/` and has `fa1.repack` recompress them. It
is **off by default**: it looks the same as text mode, and `verify_text.py`,
`verify_blocks.py` and the bench read dialogue from the text layer, which is empty in
graphics mode. The flag needs `keystone-engine`. If 99CMN is ever translated (added to
FILES_TO_REINSERT), the patch stops the build, because it expects the original file.

**Tests:**
- `python tools/test_mb3_gfx.py --script r03_manor_inside area_22`: each of the five
  opens, 4 camera positions, 2 maps. 40/40 pixel-identical to text mode. Frame opens print
  in graphics (`ttggt`: window and attributes in text, both pages in graphics, then close)
  and frameless opens in text. Text mode is back on after every block.
- `python tools/sweep_dialogue_gfx.py r03_manor_inside --inject --original --shard i/8`:
  plays every printing block of every original slot-1/2 script with both patches. It
  flags graphics mode still on in the field ("leak") and graphics prints outside the
  three box windows.

## The VWF: `mb3_gfx.build(vwf=True)` (the default)

It follows glodia's pen model. MB3N keeps its byte column (`[816]` column, `[81a]`
columns left, `di`), so its line breaking, `\i` indent, clears and paging are unchanged.
`FRAC` (cs:0xcd2) is the 0-7 px remainder within the byte, reset by `line_start` (every
print, `\n` and `\f` goes through it).

- **0xc3a** (the graphics half of the half-width blit, 77 bytes): reads the glyph's 16
  rows from the kanji ROM into the old shadow buffer at cs:0x7ec and ORs them. `bsr`/`bsf`
  give the ink columns (386 instructions; the game already needs a 386). A glyph with no
  ink is a space.
- **0xc9a** (the old drop-shadow routine, dead now): draws each row as
  `row << (15 - leftmost - FRAC)` with one `stosw`, so it spills into the next byte and the
  GRCG's RMW mode paints only ink. It steps scanlines with the area-boundary wrap. It then
  advances by ink width + `GAP` (1 px; a space by `SPACE_W`, 5 px), and moves `di`/`[816]`/`[81a]` by the whole
  bytes.
- **0xa16**: one byte. In graphics mode the caller now returns at once, since the blit
  advanced the pen.
- **`gfx_enter`** also forces `[826]`=0 (no `\p`) and `[827]`=0xff (no drop shadow), so
  nothing else uses the buffer.

No width table is needed. `tools/vwf_metrics.py` computes the same widths in Python from
FONT.ROM (the file np2core loads). `tools/test_vwf_metrics.py` renders 8 lines covering
every printable ASCII character and checks where the ink ends on screen: all 8 match to
the pixel. Most glyphs are 6-7 px, `i` 2, `l` 3, `.`/`,`/`'`/`!` 3, space 5, against 8
for everything in text mode. `tools/vwf_preview.py` shows text mode and VWF pages one
above the other.

The full block sweep with the VWF matches the one without it: 2449 blocks, 1267 with
graphics-mode dialogue, no problems, and the same 119 abnormal endings (dos/battle/
timeout), block for block, as the unpatched game.

**Space:** the tail has 7 bytes left, 0x9a9 has 5, and 0xc7d-0xc86 (10) is dead.

**Known gaps:**
- **Line breaks.** MB3N breaks a line when a glyph starts with no column left, mid-word
  (text mode does the same, which is why `reinsert.typeset` breaks lines itself). With the
  VWF, a line fits while its pixel width + 8 * indent <= 400 (50 columns). A glyph that
  starts in the last column may spill up to 7 px into the box margin, which is wider.
  `typeset()` still counts 48 characters, so VWF lines come out short but correct until it
  breaks by pixels.
- **Full-width glyphs after VWF text.** The full-width blit (0xb75) draws at the byte
  column and ignores `FRAC`, so a full-width character right after half-width ones can
  overlap them by up to 7 px. This matters for untranslated or mixed lines. The fix is to
  round the pen up to a whole byte before a full-width glyph (~25 bytes), and there is no
  room for it yet.
- The number print (AH=21h) goes through the same blit. Nothing seems to use it in
  graphics mode.

## Pixel-width typesetting (`reinsert.py --gfx-dialogue`)

`wrap_line()` takes a measuring function and `typeset(..., vwf=True)` wraps by
`vwf_metrics.width` to `VWF_LINE_PX` = 384 px: the box's 50 columns x 8 px, minus 16 px
for a speaker line's `\i2`, which is the same reasoning as `LINE_MAX` = 50 - 2 characters.
Character mode is unchanged: it is byte-identical to HEAD on the samples tried. A typical
line holds about 60 characters instead of 48.

**Only strings known to print in graphics mode are set by pixels.** A VWF-width line
printed in text mode would overflow 50 columns, and MB3N would break it mid-word. Which
strings print in graphics mode depends on the path that reached them, so it is measured:

- `sweep_dialogue_gfx.py --record` logs every print (script, string offset, mode) while
  playing every block of every original script with the patches on;
- `tools/dialogue_modes.py` aggregates the logs into `tools/dialogue_modes.json`
  (checked in, so the build does not need the emulator), and `mode_of(file, offset)`
  finds the print a workbook cell belongs to: the `40 02` before it. Shift-JIS text has no
  00 or 02 bytes.

From 96 scripts it recorded 3740 print strings always in graphics mode, 42 always in text,
and 3 in both. Of the translated workbook cells, **699 are set by pixels**. 22 are text or
both, and 1308 are unknown and keep the 48-character setting: 644 are in scripts the
sweep cannot inject (map scripts in slot 0, and scripts with no entry table such as
00IPL), and 662 are in blocks it never reached (behind story conditions). The build
prints these counts.

A static guess would have covered more: take the nearest framed open or close call
before the string. Checked against the recording, it got 3402 graphics strings right but
called 30 of the 42 text-mode strings graphics - the direction that overflows - because
a box closed by op 83 cannot be seen in the raw bytes. So it is not used.

**Test:** `tools/test_vwf_typeset.py` typesets every pixel-set cell exactly as the build
does, shows it in the dialogue box with the VWF, and counts MB3N's own line breaks: its
call to 0x938 when a glyph starts with no column left, at 0xa0b (half-width) and 0xa5c
(full-width). There must be none.

## The other text surfaces (measured 2026-09-22)

A graphics-mode surface needs two things: a **flat background** the clear can repaint
(its clear paints one colour across the whole window), and **something that redraws it**,
because graphics writes destroy what is under them while the text layer is an overlay.

| surface | goes through MB3N? | frame | verdict |
|---|---|---|---|
| dialogue box (13,17 / 21,17 / 13,20, 50x5) | yes | op `b3`, grey (palette 9) | done |
| battle message (20,9, 40x1) | **yes**, same print call | drawn by the battle module, *not* op `b3` | blocked: battle double-buffers (below) |
| location title (26,3, 50x1) | yes | op `b3`, grey | not worth it (see below) |
| text on the map (a frameless open with no box up) | yes | none | not suitable: nothing would repaint the map |
| menus, HUD, item and status screens | **no** - BD's own text-VRAM writer (0xa630) | - | separate renderer; column layouts |

- **Battle: tried, and it does not work this way** (2026-09-22). Its text does go through
  the same MB3N print, and switching the mode for it is easy - BD 0x9bd2 is the print
  wrapper the battle code calls (return address 16d8:9bd9), with BD's free tail right
  there for a hook. Two things then showed up, by watching frames around a message:
  1. The battle prints the message *before* drawing its panel (unpatched, the text appears
     on the battle art at one frame and the panel behind it two frames later). That is
     fine for text mode - the text layer is above graphics - but graphics text gets
     painted over. Deferring the print (stash the string at 0x9bd5, print it at BD 0x9ba2,
     after the panel routine and before the wait) was implemented and did print in
     graphics mode at the right window.
  2. It was still invisible, and the reason is the real blocker: **battle double-buffers**.
     When the panel appears, *nothing writes to VRAM* - MB3N's record of the shown page
     changes from 0 to 1. The battle composes each frame in the hidden page and flips.
     Graphics text drawn into the visible page is gone at the next flip.

  So battle text would have to be drawn into every composed frame, after the scene: a hook
  in the battle renderer (or on the page flip, MB3N AH=08h, redrawing the message each
  time), not a one-shot mode switch. The experiment was reverted; nothing of it is in the
  tree.
- **The location title** draws a frame (op b3) over the same grey, and switching it is a
  one-line change to `OPENS`, but its window is `\w50,1` while its frame is only ~31
  columns: the clear then paints grey across the map outside the frame (2549 pixels
  differ from text mode; tried and reverted). It would need its window narrowed to the
  frame first, and it is one short line, so there is nothing to gain.
- **Map text** (a frameless open with no box) is ~1% of recorded strings (45 of 3785)
  and cannot work in graphics mode: the map behind it would have to be redrawn.
- **Menus and the HUD** never call MB3N; BD writes those cells itself. A VWF there would
  be a second renderer, and their columns are laid out in character cells.

## What a real VWF needs

- ~~the addressing fix~~ done, above
- glodia's pen model: keep MB3N's byte column (`[0x816]`/`[0x81a]`) so its wrapping,
  clears and paging are untouched, and add a 0-7 pixel remainder that resets when
  anything else moves the cursor; shift each scanline byte into a word
- a width table from FONT.ROM's half-width row, and pixel-width typesetting in
  `reinsert.py` (glodia: `vwf.py` `width_table()`, `check_text_fit.py`)
- ~~switching to graphics for dialogue only~~ done, above
- a readback for graphics-mode dialogue, so the verification tools keep working. One
  option: hook MB3N's print entry (0x82c) and record DS:SI, the string it is given.
- **code space**: the MB3N tail is used up by the addressing fix. A VWF blit plus a
  96-byte width table needs another home. Candidates: the 32 freed bytes at 0x9a9, the
  zeros after BD 0xfbb9 (maybe BSS), or MB3N code that becomes dead once dialogue is
  graphics-only. Each needs a glodia-style watchpoint check.

**Legibility:** MB3N's bold flag `[0x82b]` is 1 by default. Text mode ignores it, but the
graphics blit applies it (0xc5c), so graphics text comes out bold. With `[0x82b] = 0` and
colour 0x0f the lit pixels are *identical* to text mode (0 pixels differ across both test pages);
only the shade differs (palette 0x0f is #eee, text-mode white is #fff). Palette 7 (`\c7`)
is a dim #9aa. `tools/gfx_text_experiment.py gfx 09 0f - 00` reproduces text mode.

Open risk: cutscenes where the camera moves while a box is open, so the scroll changes
or pages flip under text already drawn. BD's own box has the same exposure.
