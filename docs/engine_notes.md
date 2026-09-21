# Kuro no Ken engine notes (for tooling and cheats)

Found live in np21debug (2026-09-18) while building `kuro_emu.py` / `kuro_test.py`.
BD.BIN is resident at segment **16d8**, and its RAM image matches
`original/decompressed/BD.BIN` byte-for-byte, so file offset = 16d8 offset.

## Player, camera, objects
| Address | What |
|---|---|
| 16d8:0136 / 0138 | Camera scroll X/Y. Equal to player - (0x28, 0x1c) except where 0x368b clamps it at a map edge (y can read 0 while the player is elsewhere). `Emu.pos()` uses the player object instead. |
| 16d8:01aa + n*0xf0 | Object table. Slot 0 is the player. +0 type word (0 = empty), +4/+6 X/Y in "anchor" coords, which are camera + (0x28, 0x1c). |
| 16d8:0951 | Last-loaded resource name, e.g. `d\ysk1`, `olb1.mp2`, `bac_00.as2`. It is **not** strictly the map name: it changes on script and battle loads too. |
| 16d8:0a70 | Word: segment of the current map's data block (trigger tables below). |

## Shinobu's stats (words, 16d8)
| Address | What |
|---|---|
| 1007 | current HP (confirmed by writing it mid-battle) |
| 100b | max HP |
| 100d | copy of current HP (write both) |
| 100f / 1013 | current / max MP |
| 1009, 1011, 1015+ | unidentified (probably ATK/DEF/etc.). Candidates for a "high stats" cheat |

`Emu.heal()` refills HP and MP. `Tester(god=True)` (the default) heals every battle loop, so fights can't be lost.

## Movement / collision (BD.BIN)
- 0x3040: the player input handler. It masks input with `[094e]`, then tries the pressed direction and then the wall-slide alternatives (0x321d/0x322c), each through the check at 0x3167.
- 0x3167 per-step check:
  1. `call 0x440d` bump-zone test. Carry set runs the zone's script via table `[0932]`.
  2. `call 0x456a` map collision. **Carry clear = wall** → `jae 0x321c` at **0x31c2**.
  3. `call 0x44b8` NPC collision.
- 0x36a0 applies a move: al bits 1 = up, 2 = down, 4 = left, 8 = right. It inc/decs object +6/+4.
- **No-clip cheat:** 16d8:31c2 `73 58` → `90 90`. Triggers, exits and NPCs still work (`Emu.set_noclip`). Not yet baked into asm.py.

## Trigger zones (teleport groundwork)
The map data segment `S = [16d8:0a70]` holds:
- `S:[4]` pointer, `S:[6]` count: **bump** zones, tested against the tile being moved into (0x440d). These are doors, signs and chests.
- `S:[8]` pointer, `S:[a]` count: **step** zones, tested against the current position (0x4475). These are exits and walk-on events.
- Each entry is 10 bytes: x1, y1, x2, y2 (anchor coords), a script index byte, and a flags byte (0x80 = disabled). Scripts run by index through `[0932]` in seg `[09fe]`.
- Talking to Innes set the 0x80 flag on her house's door bump zone. So event progress is written into these tables, presumably restored from a flag array on map load (not found yet).
- `Emu.zones()` lists them; `Tester.goto_zone()` walks into one.
- World map (`fld1`): step zone 2 = Albein (town), zone 3 = manor grounds (`ysk1`).
- Town (`olb1`): step zone 10 = south exit.
- Manor grounds (`ysk1`): step 1 = door, step 0 = exit.

**Teleport idea:** call the map-change code a step-zone script uses (the script for zone N in `fld1` contains the target map and entry point). The script opcode that loads a map hasn't been found yet. Look at what the `fld1` zone scripts do, in the current hub SCN at 26d8:0000.

## The entry table is a pointer table too (crash #4, 2026-09-20)

Entering the manor grounds (`fld1` step zone 3 -> `ysk1.mp1`) exited to DOS. The
autoplayer found it; `tools/repro_crash.py` reproduced it in one command, and a
disk-variant bisect narrowed it to **03YSK01B.SCN**.

Cause: the `09 <addr>` entry table at the top of every script is a pointer table, and
none of `find_pointers`'s byte patterns match it, so those addresses never moved. The
first string in that file is a name - カイエス -> "Keiuss", two bytes shorter - so every
block after it shifted back by 2 while entry 15 still pointed at the old place, two
bytes into the previous block.

Fixed by registering each file's entry table in `POINTERS_TO_ADD` (17 entries for
03YSK01B.SCN, 24 for 02OLB03.SCN, which had the same defect and had not been reported
yet). The rows were **appended to the existing sheets**, not regenerated: re-running
find_pointers on 03YSK01B.SCN turns 6 rows into 77, bringing back rows that were
deliberately removed.

**`check_pointers.py` catches this class statically**, with no emulator: it decompresses
each patched script (some are stored compressed, some plain) and checks that entry *i*
still points at the same block, by index, as it did in the original. Asking only "does
this land on a block start" is too weak - the block finder misses starts, so working
files look broken. Run it after every reinsert:

    python tools/check_pointers.py     # exit code 1 if any script has a stale entry pointer

Still open: the same shift applies to branch targets inside a block (`07 0d 02 00 <addr>`,
`80 00 03 00 00 <addr>`), which are equally invisible to the regexes. Those only bite
when a file's text length changes, and the entry-table fix covers the entry points, but
decoding the script format properly is still the real answer.

## The script interpreter's opcode table (BD.BIN 0x22d0)

This is the thing to build on, and it ends the guessing about which words are pointers.
The interpreter's main loop is at BD.BIN **0x33b2**:

```
33b2  es = [0x9fe]              ; the script segment
33bb  lodsb                     ; next opcode byte, from es:si
33bd  bl = al; bh = 0
33c1  bx += bx
33c3  call word ptr [bx+0x22d0] ; 256-entry handler table
33c7  loop while [0x94d] == 0
```

So `handler(op) = word at BD.BIN 0x22d0 + 2*op`, and each handler's own `lodsb` /
`lodsw` show exactly what operands that opcode takes. Decoded so far:

| opcode | handler | what it does |
|---|---|---|
| 0x80 | 0x24d0 | **spawn an object**; the word operand is its script address, stored at object+0x28 (and +1 = 0x80, the flag the NPC-collision loop at 0x44b8 tests) |
| 0x88 | 0x2569 | store a **byte constant** into variable N (`88 <var> <byte>`) |
| 0x89 | 0x2571 | store a **word constant** into variable N - a value, *not* a pointer |
| 0x0d | 0x1d30 | conditional branch, 16-bit target |
| 0x09 | 0x1cee | jump, 16-bit target |
| 0x04 | 0x1c9d | call, 16-bit target |
| 0x83 | 0x2531 | end of block |
| 0xb0 | 0x2aa4 | (the `b0 00 <addr>` that names the next block) |

`89 <var> <word>` is exactly the trap this project hit with 02OLB02.SCN: ten of them in
03YSK01B.SCN look like pointers to a byte scan and are plain values. Do not register a
word as a pointer without checking its opcode here.

**The next step for the remaining manor crashes** is to use this table rather than byte
patterns: walk each script from its entry points, decode operand widths from the
handlers, and enumerate every address operand. That is ground truth, and it replaces
find_pointers' regexes for .SCN files.

### Diagnosing a "crash" in this engine

It is usually not a crash. `tools/how_it_exits.py` hooks INT 21h and shows the
game printing its console-restore string and calling **INT 21h/4C, exit code 0** - an
orderly quit. So the question is never "where did it jump into garbage" but "what sent
the interpreter into the engine's return-to-DOS path".

`tools/trace_script.py` answers that: record the script offsets an action reads on
the patched build and on a build where the file is left Japanese, map the patched
offsets back through the file alignment, and align the two sequences. Where they first
disagree is where the wrong address was used. That found the `b0 00 <addr>` family after
three byte-pattern families had already been fixed.

### 03YSK01B.SCN: three pointer families, and what is still broken

The manor is one file's story. 03YSK01B.SCN's first string is a name, カイエス ->
"Keiuss", two bytes shorter, so everything after it moved back by 2. Its sheet had **6**
pointers; it needs at least 62:

| family | how it looks | count | symptom when stale |
|---|---|---|---|
| entry table | `09 <addr>` at the top of the file | 17 | grounds entry -> DOS |
| conditional branch | `80 00 0X 00 00 <addr>` | 10 | interior entry -> DOS |
| short branch | `07 0d 02 00 <addr>` (to the next instruction) | 6 | interior entry -> DOS |
| inline jump | `09 <addr>` in the body, usually after a block's `83` | 24 | interior **soft-locked**: input never re-enabled |

The soft-lock is the one to remember: no crash, the map loads, the player simply never
gets control back, because the script jumped two bytes past the code that re-enables
input. A crash-only check calls that "fixed".

**Resolved (2026-09-20).** All of it, including the last three, which were
`89 2a <addr>`: opcode 0x89 writes a constant into a field of the *current object*, and
field +0x2a is that object's script pointer. So the constant is an address, three bytes
away from an identical-looking `89 04 <number>` that is not one - no byte pattern can
separate them, which is why this family was written off twice as "values, not pointers".
Left behind, the object ran whatever had moved into its old block and eventually read a
`00` byte, and **opcode 0x00's handler (BD.BIN 0x0072) does `sp = 0; retf`** - the engine's
exit. That is the whole reason these looked like crashes: the game was quitting cleanly.

03YSK01B.SCN needed **79** pointers where its sheet had 6. The manor now sweeps clean:
36 targets inside, 7 on the grounds, 26 in Albein, no crashes, player control normal.

| symptom | family | count |
|---|---|---|
| grounds entry -> DOS | entry table, `09 <addr>` | 17 |
| interior entry -> DOS | `80 00 0X 00 00 <addr>` (spawn) + `07 0d 02 00 <addr>` | 16 |
| interior soft-locked | inline `09 <addr>` jumps | 24 |
| npc 1 -> DOS | `09 <jump> b0 00 <addr>` | 10 |
| three zone actions -> DOS | `89 2a <addr>` object script pointers | 12 |

### Decoding a script instead of pattern-matching it

`script_decode.py` walks a .SCN using the opcode table above, so a word is a pointer
because of the instruction it belongs to, not because of the bytes around it. Run it
over every translated file with `tools/stale_report.py`, which keeps only the
addresses whose target moved while the stored value did not - the ones that actually
break:

    python tools/script_decode.py 03YSK01B.SCN --check   # pointers vs what is registered
    python tools/stale_report.py             # what reinsert left behind

Across the whole translated set that was 4 pointers (02OLB02A 0x49d, 02OLB03 0x7bc /
0x7c1 / 0x7cd - all opcode 0x0c/0xb0 branch targets), now registered. The decoder finds
about 300 addresses the sheets never listed, but most sit before any text edit and never
needed moving; the difference between "is a pointer" and "is a *stale* pointer" is what
makes the list actionable.

**Two traps worth remembering.**

*Alignment.* The first run of stale_report also flagged entry-table slots in 02OLB01 and
02OLB02. Those were wrong: difflib slides its alignment across a repetitive run (an entry
table is 31 copies of `09 xx 18`), so the "patched" word read back belonged to a
neighbour. Registering them would have corrupted two working files. The check now
verifies the mapping lands on the same opcode byte, and reads entry-table slots at fixed
offsets, since that table never moves.

*Regenerating a sheet.* `find_pointers` on 03YSK01B.SCN turns 6 rows into 77, bringing
back rows that were removed deliberately. Edit the sheet in place (see the scratchpad
sync script) rather than regenerate it.

### Finding these pointers

1. `tools/deep_pointer_audit.py FILE` - aligns original and patched and lists
   every address left behind. Over-reports badly (81 candidates for this file), so it
   is a lead generator, not a fix list.
2. `tools/confirm_pointers.py FILE STATE --target=npc:1` - runs the broken action
   with a read watchpoint on the script slot and keeps only candidates the interpreter
   **fetched as an address operand**. That is the proof.
3. `tools/cross_pointer_audit.py HOLDER TARGET STATE SPEC` - for addresses one
   script holds into another's slot, which (1) cannot see because the holder is
   unchanged.

## Random battles (still not found - what has been ruled out)

Random encounters are what stop the autoplayer walking anywhere in a dungeon (on
`stg.mpc` a fight starts within about three steps), so a "no random battles" cheat is
worth having. Ruled out so far, to save the next attempt the work:

- **Not** any of BD.BIN's per-step calls: 0x36a0 (apply move), 0x36c3, 0x3264, 0x36e1,
  0x3761, 0x4651 - all disassembled, none tests a counter or starts a fight.
- **Not** `16d8:11f1`, despite ticking down per step and being reset by the battle: the
  code that reads it (`2c651`) computes `(1000 - x) / rand()` over every entity, i.e.
  battle **turn order**, not an encounter roll. Holding it high changes nothing.
- The writes come from the field module around **0x2c000**, not from BD.BIN, so this
  needs live disassembly (`tools/disasm_live.py`) rather than BD.BIN.

Next thing to try: np2core's **code coverage** - record it over several steps with no
battle, then over the step that starts one, and diff. The encounter branch is in what
only the second run executed. `scratch_emu/find_encounter*.py` have the walking and
RAM-diff scaffolding.

## Teleport: destination is a global variable (found 2026-09-20)

Every exit on the world map is one instruction:

    20 <var 3> <N>    83

and opcode 0x20 (handler BD.BIN 0x1ded) is "global word variable = value", the array
being at **16d8:06d2** (index i at 0x6d2 + 2i). Variable **3 is the destination**, so
running that as a synthetic block through the bench sends the player anywhere:

    python tools/teleport.py ysk2_final 5      # -> sks1
    python tools/area_states.py                            # a save state per area

**Check the control when testing this.** The first attempt looked like it worked from a
world-map state, but a block that did nothing teleported too - the player simply stood
next to the manor exit. Run `teleport.py STATE -1` (a no-op block) next to any real test.

| N | map | | N | map | | N | map |
|---|---|---|---|---|---|---|---|
| 1 | ysk1 manor grounds | | 11 | stg | | 21 | gagoil |
| 2 | olb1 Albein | | 12 | gakusha2 | | 22 | isk2 |
| 3 | ysk2 manor interior | | 13 | haka | | 23 | kies_m5 (scene) |
| 4 | old | | 14 | ymm1 | | 24 | umb1 |
| 5 | sks1 | | 15 | mkr1 | | 25 | ds_16 (scene) |
| 6 | blk1 | | 16 | isk1 | | 26 | kkr |
| 7 | yoroi.mca - **exits to DOS** | | 17 | drl1 | | 27 | taicho_o |
| 8 | ckd | | 18 | goblin_s | | 28 | mimic |
| 9 | hik | | 19 | ire1 | | 29 | knt |
| 10 | tni1 | | 20 | nnp | | 31 | bac_11 |

32 and up fall back to the current map. Destination 7 **is** a real destination - 14YMM.SCN
teleports there - but arriving cold quits, and 14YMM.SCN is untranslated, so this is the
same out-of-context failure the area sweeps show rather than anything the patch did.

Only five destinations (7, 8, 12, 21, 28) are reached by a `20 <var 3> N` in a script
that the decoder can read. The rest live in the **map scripts**, which have no `09 <addr>`
entry table at the top and no end-of-block idiom the block finder can see - 01FLD.SCN
decodes to three instructions. Their blocks come from the zone tables instead, which are
a runtime structure: `tools/zone_table.py STATE` prints them for the loaded map.
Decoding a map script statically needs those tables located in the file first, which is
still unsolved (an earlier shape-based guess produced nonsense and was dropped).

The names line up with the script prefixes (`04OLD` -> old, `05SKS` -> sks1, `17DRL` ->
drl1...), so this is also the area list behind script_map.md's progress table.

## Progression flags: a bitfield at 16d8:08d2 (found 2026-09-20)

Opcode 0x0d tests whether a flag is set, and its condition reader (BD.BIN 0x17dd) takes a
16-bit flag index and resolves it to

    byte 16d8:08d2 + index / 8,   bit index % 8

so every flag the scripts test lives in one bit array.

**Which way the code runs** - easy to get backwards, and it decides what a line needs:
`0c <flag> <addr>` *jumps* when the flag is **set**, so the code after it runs when it is
**clear**; `0d` is the reverse. Settled by running it, not by reading the handler: the
manor Chancellor's three-page introduction sits behind `0c 73 00 <addr>` in 03YSK01B and
plays with 0x73 clear (`tools/flag_demo.py`). `0c F ... 1d F ... text` is therefore
the "first time only" idiom - the lines play once and setting F skips them afterwards.

Confirmed against save states:
`r01_after_opening` has 3 flags set, a later state 14, strictly added, none cleared.

`tools/flags.py STATE_A STATE_B` lists what an event set, which is how to find the
flag for a specific piece of progress: save either side of it and diff. Setting one is a
single byte write, so this is also the "set progression flags" cheat.

Zone tables carry the other half of event state: talking to Innes sets the 0x80 bit on
her door's bump zone (see above), and those bits are presumably restored from this array
on map load.

## Script format (found 2026-09-19, by disassembling BD.BIN with capstone)

A `.SCN` is a list of **blocks** plus tables of addresses into them. Addresses are
stored as `base + offset`, where base is the slot the file is loaded into: **0x0000**,
**0x1800** or **0x3d00** in segment **26d8**. Slot 0 holds the map script, slot 1 the
common/hub script, slot 2 a scene script.

- The file starts with a table of `09 <addr-word>` entries (opcode 09 = jump), one per
  entry point.
- A map script also ends with a plain **word array of block addresses**, indexed by a
  trigger zone's script byte. Live pointer: offset `[16d8:0932]` in segment
  `[16d8:09fe]` (i.e. inside the loaded file itself).
- A dialogue block looks like:
  `04 06 30` (call the common script at 0x3006 - opens the window)
  `40 02 <string> 00` (print the string)
  `09 15 30` (jump to the common script at 0x3015 - closes it and returns)
- Strings are Shift-JIS with **ASCII escapes**: `\f` (5c 66) ends a page, `\n` (5c 6e)
  next line, `\i2` indent, `\c09` colour, `\w80,4` wait, `\s1`, `\k0`, `\t0`...

### How a trigger runs a block (BD.BIN 0x3167, the per-step check)

```
call 0x440d              ; bump-zone test; carry set -> al = the zone's script byte
bx = al;  [0x6fc] = bx   ; remember the index
bx = bx*2 + [0x932]      ; word table of block addresses...
ds = [0x9fe]             ; ...in the script segment
si = [bx]                ; block address
call 0x33d1              ; run the block from si
```
`0x440d` compares the tile being stepped into against each 10-byte zone entry
(x1, y1, x2, y2 **as words**, then script byte, flags; 0x80 = disabled), signed.
NPC collision is a separate path (`0x44b8`, objects every 0x78 bytes from 0x132 -
note that is *half* the 0xf0 stride `kuro_emu.objects()` uses, so that model sees
every other entry).

## Text box geometry (measured in game, not guessed)

`tools/bench.py` prints a ruler string through the engine and reads the text
layer back:

| | |
|---|---|
| Box | **50 columns x 5 rows**, starting at screen column 13 |
| Wrapping | the engine wraps at 50 and breaks on spaces when it can |
| Overflow | a 6th `\n` line is **silently dropped** - no scroll, no page break |

So `reinsert.typeset`'s LINE_MAX=48 / BOX_ROWS=5 is correct, if slightly conservative
on width (the 2 columns are what `\i2` costs after a speaker name).

## Rendering any line on demand (the text bench)

`tools/bench.py` `RenderBench.render(text)` shows an arbitrary string in the
game's own box, headless, in about a second:

1. write `04 06 30  40 02 <text> 00  09 15 30` into the free space past the end of the
   map script in slot 0 (`free_at()` finds it by identifying the loaded file),
2. point a slot of the block-address table at it,
3. rewrite bump zone 0's rectangle to cover the player and give it that index,
4. take one step - the engine runs the block.

`verify_text.py` uses this to render **every translated page in the workbook** and
compare what the screen shows against what the workbook says, which catches overflow,
dropped text, bad control codes and garbled glyphs without having to reach the line in
the game. Run: `python tools/verify_text.py --workers 6`.

## Text VRAM
- Dialogue is written as kanji-ROM half-width cells `09 xx`. The battle module writes plain ASCII `xx 00`.
- The game's own glyphs are `56 xx`: `56 21` menu cursor, `56 26` press-a-key icon, `56 2e`/`56 2f` fill rows.
- **Two text pages**: A000:0000 (field/dialogue) and A000:1000 (battle). The hidden page keeps stale text. `Emu.text_cells()` picks the page whose text cells show near-white pixels on screen.
- The box holds **a speaker name + 4 lines**. `\f` (5c 66) ends a page and `\n` (5c 6e) continues it. After the name, `\i2` indents later lines 2 columns, so a 48-char continuation line ends at column 62.

## Emulator control (np21debug)
- WM_COMMAND IDs: 40101 = reset; 40201+n = save state n; 40251+n = load state n.
- `Emu.save_state/load_state` go through slot 9 (`romtools/np2debug/np21.S09`) and keep named copies in `states/`.
