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

### More of the opcode table, read for the castle's second stage (2026-09-26)

Read off the handlers with capstone (`scratchpad/scndis.py` is the linear disassembler
that uses them); the two flag branches were documented backwards until now:

| opcode | handler | what it does |
|---|---|---|
| 0x0c | 0x1d26 | branch to <w1> if flag <w0> is **set** (`test` then `lodsw`, which keeps ZF, then `je` skips the jump) |
| 0x0d | 0x1d30 | branch to <w1> if flag <w0> is **clear** |
| 0x01 / 0x02 | 0x1c36 / 0x1c5b | far call into native code at script segment:<word> (0x02: the address held in var <w0>), with bx = objects, si = vars, di = flags |
| 0x06 / 0x0b | 0x1ca8 / 0x1cf9 | jump table: `<var> <tagged default> <n> <n x tagged>`; entry k is the case for value k. Every area hub's stage switch is one (06BLK.SCN 0x16) or a chain of `10` compares (07CSL.SCN 0x0f) |
| 0x07 | 0x1cdc | return (pops the script call stack; the zone handlers end with it) |
| 0x39 | | load a script: `39 <tagged slot> 02 "name" 00` |
| 0x68 / 0x6a | | table lookups: `68 <var i> <tagged table> <var out>` = out := table[i]; `6a <var i> <tagged table> <flag>` sets a flag from a byte table. The stage script's entries 4 and 5 use them on the zone index (var 0x15) to find a zone's handler |
| 0x84-0x89 | 0x2537-0x2571 | fields of the object running the script: `84/85 <var> <field>` var := byte/word field, `86/87 <field> <var>`, `88/89 <field> <imm>` |
| 0xc8-0xcd | 0x2582-0x259b | the same on another object: `c8/c9 <var> <tagged obj> <field>`, `ca/cb <tagged obj> <field> <var>`, `cc/cd <tagged obj> <field> <imm>` (object n is at 0x132 + 0x78 n) |
| 0xa1 / 0xa3 | 0x28af / 0x28db | place the current object / object <tagged> at (x, y), each tagged, 0xffff = keep |
| 0x30-0x35, 0x2f | 0x1e87-0x1ec7 | more variable arithmetic, word + word (0x32 shifts left, 0x34 right: the hubs move a counter's low byte into its high byte with them) |

**How a zone reaches a script.** The engine's step-zone scan (BD.BIN 0x4475, called from
0x30e1) returns the zone's script index; the caller looks up `word [0x934] + 2 * index`
in the script segment and runs that address (bump zones: `[0x932]`). Both tables are the
hub's, one pair per region (07CSL.SCN 0x166e/0x167a for the castle hall), and each hub
handler calls the stage script's entry 4 or 5 (`04 180c` / `04 180f`), which looks the
zone up again in the *stage's* tables (07CSL02.SCN 0x20b4..: four lists of per-region
tables, set into vars 0x50-0x53 by entry 3) and calls the handler found there. So a
region's zone means one thing in the hub (where it leads) and another per stage (what
it triggers): in the castle at stage 2, the hall's doorway at (88-99, 71) is the
handler at 0x2df6 that starts the audience (var 0x34 := 6) when flag 0xa9 is clear -
reachable only from the north, since from the south the bump zone in front of it is
the locked door (0x2d7d, "the door won't open") until flag 0xa8 is set.

**The castle's stage 2 is a state machine** on var 0x34, run per frame by the stage
script's entries 1 and 2: 3 = the arrival ambush (a fight the party must win; sets
flag 0xa6 at its end), 4 (needs 0xac clear), 5 (region 22, sets 0xa8: the door), 6 =
the audience (region 07_ea0c; entry 4 of 07CSL02A; writes var 7 := 2, 0x84 := 4,
0x85 := 3, 0x86 := 2, 0x87 := 2, **0x88 := 2**, sets 0xa9, 0xaa), 7, and -2/-3 = pushed
back by the guards. The throne room's zones all push back while flag 0xab is set (the
hub sets it on the first load at stage 2), and the push-back is a fight the party loses.

**Each hub maps its counter to a stage its own way** - this is what mattered for the
route follower. 06BLK's table loads 06blk01 for 0 and **06blk02 for 1**; 07CSL loads
07csl01 while the counter is <= 1 and 07csl02 at 2; 02OLB loads 02olb02 for 2, 3 and 4;
05SKS 05sks0n for n-1; 17DRL skips 2; 15MKR loads 15mkr01a at 0, 15mkr01b at 1-2, 01c at
3-5, 01d at 6, 01e at 7, 15mkr61 at 8 - the letter is the stage there, and 15MKR02A..H
are its scenes. `autoplay.hub_loads(area)` walks each hub's head for every counter
value (a small interpreter over the compares, switches and loads), `hub_scenes` the
scenes the hub loads itself (02OLB), and `resident_values(area, script)` the counter
values at which a script can be resident, through whichever stage script loads it. The
capital was at stage 2 the moment the pass's scene (11STG01, which writes 0x88 := 1)
had played - the audience is only what opens its stage 3.

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

## Variables, compares and story counters (found 2026-09-21, from BD.BIN handlers)

**Variables** are words at `16d8:06d2 + 2*index` (routine 17cc), and the flag bit array
starts at 08d2 - so there are exactly **0x100 variables**, and a flag index tops out where
the resource-name buffer starts at 0951. `tools/script_decode.py` uses both bounds to tell
real instructions from bytes that only look like them.

**Compare-and-branch, opcodes 10-1b** (handlers 1d62-1d9e): three words, the third a jump
target taken through 1d2d (`mov si, ax`), like 0c/0d. Even opcodes compare variable w0 with
the constant w1 (1daa), odd ones two variables (1db6). 10 jumps if !=, 12 if ==, 14 <=,
16 <, 18 >, 1a >= (unsigned). Until these were in the decoder's table, a walk stopped at the
first one, and their jump operands were never relocated: 02OLB02A's stage switch had five
of them missing from the hand-made pointer sheet.

**Variable arithmetic, 1c-2f**: 20 var = const, 21 var = var, 22 ++, 23 --, 28/2a/2c/2e
+= -= &= |= const, odd 29-2f the same with a variable. None holds an address.

**Story counters.** Each area hub (`02OLB.SCN`, ...) is a switch on one variable:
`10 <var> 00 <n> 00 <next>` then `39 00 00 <slot> 02 "<script>"`, loading different scene
scripts per value. Five of those variables only ever count up, each value set once, by one
script, anywhere in the game (`20 <var> 00 <n> 00`):

    0x84: 1 03YSK01A, 2 11STG01, 3 03YSK01B, 4 07CSL02, 5 07CSL05, 6 25TOU00C, 7 10TNI02, 8 03YSK70
    0x85, 0x86, 0x87, 0x95: likewise, tied to 0x84 by scripts that set several at once

so they are the game's chapter clock, and `tools/story_order.py` builds the story order of
the scripts from them.

### Every area has its own stage counter: variable 0x82 + the area number (2026-09-22)

The line above - "0x7e is each area's floor number, reused" - was reading the hubs one step
too early. **No hub switches on its counter directly.** It copies it into a scratch
variable first and switches on that:

    21 7e 00 89 00     var 0x7e := var 0x89        (07CSL.SCN 0x0f)
    2c 7e 00 ff 00     var 0x7e &= 0xff
    18 7e 00 01 00 33 00   unless 0x7e <= 1, jump to 0x33 - stage 1's case
    39 00 00 18 02 "07csl01" 00

0x7e and 0x7f are the scratch registers every hub reuses, so taking them at face value
merges unrelated areas and hides the real variable. Resolved through the copy, the pattern
is exact, with no exception in the 30 areas: **area N switches on variable 0x82 + N** -
02OLB 0x84, 03YSK 0x85, 04OLD 0x86, 05SKS 0x87, 06BLK 0x88, 07CSL 0x89, 08CKD 0x8a,
09HIK 0x8b, 10TNI 0x8c, 11STG 0x8d, 15MKR 0x91, 17DRL 0x93, 23SOH 0x99, 26KKR 0x9c,
27KKI 0x9d. The chapter clocks above are simply the area counters that happen to pass the
"each value set once, from anywhere" test.

Which stage is current is the whole of an area's story: the capital's 42 scripts are six
visits (06BLK01 .. 06BLK07), the castle's 28 are eight. What dates a stage is **who
advances the counter from outside the area**: `20 89 00 03 00` in 27KKI01 is where the
castle's stage 3 begins. A write from inside the area says nothing (all eight 07CSLnn set
0x89 back to 1), a write of 0 is a reset, not a start (17DRL03 does that to 15MKR's 0x91),
and the world map writes nearly everything.

### The counters are one network, and it is the story's skeleton (2026-09-23)

Taken one at a time, an area's counter only orders that area's own visits, so the order
across areas had to come from somewhere else - which area the player can first walk to.
That is the wrong shape for this game: a town is revisited at five separate points, and its
fifth visit belongs beside other areas' late scenes, not beside its own first one.

Taken **together** the counters say much more. Area N's counter is advanced from *outside*
area N, so each one is a list of other areas' scripts in the order they run:

    area 02 (0x84): 03YSK01A -> 11STG01 -> 03YSK01B -> 07CSL02 -> 07CSL05 -> 25TOU00C -> 10TNI02 -> 03YSK70
    area 06 (0x88): 11STG01 -> 07CSL02 -> 27KKI01 -> 07CSL05 -> 07CSL06E -> 05SKS -> 17DRL04A -> 18KSK -> 07CSL08 -> 27KKI03
    area 26 (0x9c): 15MKR01C -> 27KKI01 -> 22MZI -> 07CSL08 -> 17DRL04
    area 27 (0x9d): 17DRL04 -> 10TNI03 -> 19IRE94

Fourteen counters give **38 statements of the form "this runs before that", every one of
them crossing an area boundary, and together they have no cycle**: a single order satisfies
all of them. That is the strongest evidence in the game about the shape of the story, and
it owes nothing to the area numbering, which does not follow the story at all.

Two tests make the difference between a clean network and a contradictory one:

* **Only values a hub actually switches on count.** 27KKI01 also writes `0x95 = 18`; read
  as area 19's stage 18 it put that area's chain against area 05's, the one cycle in the
  whole set. Area 19 has four stages, so 18 is the variable being used for something else.
* **The milestone is the block, not the file.** A hub runs on every visit and advances its
  neighbours' counters from inside whichever stage branch it is in. `05SKS` as a whole is
  early; the branch of it that starts the capital's stage 6 is not.

`tools/story_order.py` turns the network into a **rank** - the longest path through it,
eleven deep - and every stage of every counter inherits the rank of the block that starts
it, so a scene the hub loads at that stage gets that rank wherever it lives. Rows then sort
by `(rank, place)`: the rank says which of the game's moments a scene belongs to, and the
old area-by-area place orders the scenes inside one moment, which is what it is good at.

Against the recorded playthrough this cut the scenes that sort out of order from 10 of 26
to 4, and the worst from 1330 rows to 180. The two it fixed outright were Kikuichi's second
and third visits, which area order had a thousand rows before the manor scene that the
chains - and the video - put first.

**Where the network says nothing.** A milestone with nothing before it in any chain gets
rank 0 from the longest path, and that means "no counter constrains this", **not** "this
happens first". City McCulloch, Dorral Village and Ruins McCulloch are all like that: they
hang off the travel-permit quest, which no counter records. Ranking them 0 threw them 2000
rows in front of the castle they follow. Those areas are dated from
`docs/video_anchors.json` instead, by reading their position against the anchors the chains
*do* rank - weaker evidence, kept separate and marked as such in the basis column, and
nothing else in the order depends on it.

A stage with no ranked writer at all is left out of the ranking rather than given rank 0,
which is a different thing again. The Black Dragon Cave's first two visits are started by
scripts the chains never constrain, and reading that as rank 0 put the endgame's cave in
the first hundred rows of the sheet, 9700 rows from the rest of it.

### A script's own progress counter orders the scenes inside it (2026-09-23)

An area counter separates an area's *visits*. One visit can still be a long sequence, and a
script tracks where the player is inside it with a variable of its own:

    @00ed  20 28 00 01 00          var 0x28 := 1
    @0047  10 28 00 07 00 53 18    unless 0x28 == 7, skip
           b0 00 68 18             ... run the block at 0x1868

03YSK01A is the whole of the first time at the manor - arriving, seeing the jewel, being
called a thief, the fight, escaping with a shikigami - and the block above is the scene for
walking back in *after* the escape. It is the file's first block, so file order opened the
manor with its ending. Reading 0x28 puts the file back in sequence, and 56 scripts have
such a counter.

Two details decide whether this works at all:

* **Compares have to be looked for at every offset, not with `finditer`.** Matches overlap,
  and a regex scan drops the second of two compares seven bytes apart - which lost the
  manor its middle step, the one the guards are called on.
* **`b0`/`b1` carry a tagged operand**, so the address is one byte further along than in
  `09`/`04`. Read as bare, every `b0` target lands thousands of bytes out - and `b0` is
  exactly what a guarded jump uses.

A block reached at two different steps takes the **earliest**, the same rule `weakest` uses
for scene conditions: scripts share their "say this line" helpers freely, and taking the
latest caller dragged ordinary townspeople to the end of the sequence.

**Opcode 0x0b is a jump table** (handler BD.BIN 0x1cf9), which is how 06BLK, 17DRL and
23SOH switch instead of a chain of compares:

    0b <var word> <tagged default> <count byte> <count x tagged word>

It reads the variable, and jumps to entry[value] - entry i is the block for stage i -
falling through past the table when the value is out of range and the default is 0xffff.
Until this was decoded, `tools/story_order.py` stopped at the table and every script of
those three areas sat at a single anchor; now each visit is placed on its own, and the
recorded playthrough agrees (06BLK01B early in part 1 is stage 0, 06BLK04O in part 3 is
stage 3, 07CSL01A in part 2 is stage 1, 07CSL04B in part 3 is stage 4).

The hubs of 16MKI, 19IRE and 24UMB have no switch at all: they are map scripts that pick
scenes by trigger zone.

## The dump is read in offset order, whatever the sheet's order (2026-09-21)

romtools returns a file's rows in sheet order, and reinsert's pointer walk, typesetting and
padding all assume ascending offset - rows out of order silently skip pointers.
`ordered_dump.OrderedDumpExcel` sorts them (and collapses the duplicated 02OLB03A rows
that come back with every merge of the translator's sheet). Verified: a randomly shuffled
workbook builds byte-identical to the original (584 files).

The same session fixed the backward-pointer write at its source (`pointer_edit.py`: the
word's position is its original offset plus the block's actual growth, verified against
the original bytes before writing), and reinsert now records its exact edits
(`patched/<script>.edits.json`), which `fix_pointers` and `stale_report` use instead of a
difflib alignment - that alignment slipped 2 bytes in 05SKS03 and "repaired" two correct
pointers into wrong ones.

## Which area leads where (2026-09-21)

A map change is a single instruction, `20 <var 3> <destination>` (tools/teleport.py), and
the **destination number is the area number**: 5 the border post, 6 the capital, 27 the
Black Dragon ruins. Scanning every script for that write gives the game's travel graph -
05SKS -> 6, 08CKD -> 9, 27KKI -> 28 -> 30 -> 29 -> 31 - which is what `tools/story_order.py`
uses to place an area the story counters never mention: it starts no earlier than the first
placed script that can send the player there.

Two things that make a write weak evidence:

* **01FLD, the world map, writes nearly every destination.** What decides whether an exit is
  open is the 0x80 disabled bit in the map's own zone table (see "Trigger zones"), not the
  script, so the world map says nothing about when an area opens up.
* **A hub script runs on every visit**, so its write may be in a late branch. 27KKI's write
  of destination 28 is one, and reading it as a first visit put the ending in the middle of
  the game. From a hub the most that can be said is "after everything else known in that area".

Story flags do not order areas: `1d <flag>` setters and `0d <flag>` tests pair up across
areas in *both* directions (07CSL <-> 26KKR, 02OLB <-> 06BLK, ...), because the flags are
shared party/event state rather than one-way gates. That was checked and dropped.

## Dating an area from a playtest (2026-09-21)

Where the scripts say nothing, the recorded runs can: a save state holds the story
counters (variables at 16d8:06d2 + 2*i), and a run's transcript says which lines played.
`tools/seen_when.py` matches each report against the lines that belong to one script only
(half the game shares 「・・・・・・」, so shared phrases prove nothing) and reads the
counters out of that run's state, writing docs/playtest_clocks.json.

That dated 12MRS, which nothing else could: 36 lines only 12MRS.SCN has played in
auto_run14, whose state has 0x84 = 1 and every other counter 0 - just after the first
manor visit. Its maps were fld1/stg/tni and the resource loaded was `gakusha2.mca`, the
scholar sprite, so **12MRS is a scene that plays on another area's map**, not a place the
player travels to. That is why only the world map appeared to lead there.

Two cautions. The autoplayer starts from a save state and walks into whatever zones are
open, so check the run's ancestry before trusting it (auto_run14 descends from
r03_after_mercenary, a played route, not from a teleport - `tools/area_states.py` states
carry the counters of wherever they teleported *from*). And "reachable" is not "belongs
here": the tower plays at 0x84 = 2 in auto_run25, while 25TOU00C is what sets 0x84 to 6,
so story_order only uses a playtest for an area no counter dates at all.

## Ordering from a recorded playthrough (2026-09-22)

sqpat's Twitch VODs of the PC-98 version (collection i9PxK6i5nRamtQ, four parts, ~20h)
are a human route through the game, which is the one thing neither the scripts nor the
autoplayer can give. Reading them does not need the video downloaded:

* open the VOD in the browser pane and seek by setting `video.currentTime`;
* the stream frames the game beside box art, so draw the video into a full-viewport
  canvas with a crop (`drawImage(v, 272,0,1008,720, 0,0,1280,720)`) - then a screenshot
  shows the game screen large enough to read;
* read the Japanese off the frame and grep the dump for it: that names the script, and
  the script names the area.

docs/video_anchors.json holds what was found (27 frames). Sampling is cheap now that the
page finds the frames worth looking at: read the canvas back with `getImageData` (the
stream is not cross-origin-tainted) and call it a text box when one flat mid-grey fills
over a third of the bottom strip. Seeking with the video *paused*, then probing, walks a
range at ~3s a sample and only the hits are screenshotted.

It corrected two placements the scripts had wrong - both areas the only-counter-write
problem hits, where the write is a *late* event:

* **12MRS (the Isle of Forests)** plays at part 2, 1:40, right after Albein's stage 2 sends
  the player there. A playtest had put it at 0x84 = 1, which only showed the autoplayer
  could walk in.
* **23SOH** plays at part 3, 5:50, after the castle's stage 4. Reachability had put it far
  earlier.

It no longer places **06BLK** or **17DRL**: their hubs' jump tables (see "Every area has
its own stage counter") date each visit from the game itself, and the video now only
confirms them - 06BLK01B at part 1 1:10 is stage 0, 06BLK04O at part 3 0:40 is stage 3,
07CSL01A at part 2 0:45 is the castle's stage 1, 07CSL04B at part 3 1:20 its stage 4.
Of 27 anchors, the only ones that read "out of order" against the script placements are
revisits (this player walked back into Albein and the castle early), which is what a single
route looks like: **a frame is an upper bound on when content becomes available, not a
lower one.** Two that are worth a second look: 03YSK69A and 16MKI61 play at part 4 0:50
and 0:20, ahead of 27KKI02A/03A at 5:33 - the placements put them after.

It also settled the three areas nothing else could reach, from the game's own text rather
than from a frame: Albein's 02OLB02A says the Isle of Forests has "a cave leading to the
bottom of the sea", and 12MRS says "when the Sleeping Princess awakens, the entrance
opens". So 12MRS -> 13SLP -> 21KTI -> 22MZI is one quest chain, early, right after the
first Albein/manor stretch. That is recorded in story_order.OVERRIDES as inferred, not
observed.

All 30 areas are now placed (see "The last four" below). 99CMN, the common script, is put
at the *front* with the intro and the world map: it is prompts and shop lines used from the
first menu onwards, so it is always-there text rather than a point in the story.

### The last four, and what settled them (2026-09-22)

* **29KNT (Chaos Cloister)** is the final dungeon: 29KNT.SCN and 29KNT99B.SCN lines play
  from part 4 8:03 right through the finale ("シノブは《黒の剣》を抜き、カイエスに手渡した"),
  and the END screen follows at 9:00 - so **31END** is last.
* **30IZM (Fountain of Sacred Waters)** opens with its own place name and a line about the
  great battle still ahead, and its map leads to 29KNT: the calm scene before the end.
* **09HIK (the Abandoned Mine)** resisted everything. No counter mentions it, its dialogue
  is an old miner with no story hook, and its flags are the shared kind (0xc8 pairs it with
  seven areas in both directions). It is placed after 08CKD, the only place that leads
  there, and the basis says exactly that.

Note for anyone repeating the frame sampling: the canvas draw loop must use `setInterval`,
not `requestAnimationFrame` - rAF stops when the pane is not being painted, and screenshots
then silently return the last frame drawn while `currentTime` keeps moving.

### A second playthrough, read by the game's own font (2026-09-24)

WERDNAちゃんねる's YouTube stream of the PC-98 version (#01 g2wng1XNxsk, #02 gPpYHBBKXm4,
#03 bJq1wCJ6Qqg, #04 MLnXexuEITM; 13.8 h against the Twitch run's 26 h) is a second
route, and it was read without a browser or a human in the loop:

* `yt-dlp -f 298` (720p60, video only, 11 GB for the four) to a scratch folder, since
  Twitch's page policy blocks the page from talking to anything local, and a file can be
  sampled by ffmpeg at its keyframes (one every 5 s) at ~170x real time.
* **The dialogue is on the text layer, so it is the kanji ROM.** `tools/vod_ocr.py` crops
  the game screen out of the frame (this stream: 960x600 at (-2, 60), i.e. 1.5x), resamples
  it to 640x400, finds the box (one flat dark navy, `text_box`), and at every 8-px cell of
  each 16-px text row picks the FONT.ROM glyph that correlates best with the pixels.
  Templates are softened with a 3x3 mean to match the stream's blur, twelve sub-pixel
  shifts of the crop are tried per cell because the stream's scale is not exactly 1.5,
  and both half-cell phases are scored because the speaker's name sits 4 px left of the
  text grid. A right glyph scores ~0.6-0.8; below 0.5 the cell is written `?`.
* What comes out is most of every line with gaps and a wrong kanji here and there
  (`じ＝あ、せめて、その剣の名を教えて??れよ`), so `vod_read.Fuzzy` matches it by the
  longest common substring with a dump row, candidates nominated by shared 4-grams
  (6 characters shared, or the whole row when it is shorter). Ties between scripts
  are settled as before, by the story order after the previous anchor.
* FONT.ROM's kanji are at `0x1800 + ((j1-0x21)*0x60 + (j2-0x20))*32`, sixteen bytes of
  left half then sixteen of right (np21w's `fontv98.c` and `cgrom.c`).

Anchors carry a `series` ("twitch" or "werdna"); each series has its own `at` axis and
becomes its own `video <series>` sequence in tools/play_order.json, since two players'
routes are two orders and only agree where the game forces them to. WERDNA's four parts
gave 1,289 readings and 431 anchors (a third of readings are battle text or too broken
to share six characters with a row), folding to a 97-item sequence. The Twitch VODs were
then downloaded too (`yt-dlp -f 720p`, 21 GB, keyframes 2 s apart; game screen at 1.5625x
from (274, 47)) and read the same way: 11,400 readings, 10,800 anchors, a 164-item
sequence, which replaced the 320 anchors read by eye. The machine readings are kept in
docs/vod_samples/{twitch,werdna}_part*.json.

The fold ignores two kinds of sighting: a lone anchor inside another script's run (the
same line in a sibling script), and any line of a hub that loads scenes at several
stages (03YSK, 06BLK, ...), since a hub's own lines - the place name - play on every
visit. With both routes folded, v22 keeps 3,626 play-order edges and drops 216 that
contradict a causal need or the other route; script by script, 20 of 141 first
sightings in the Twitch run and 19 of 101 in WERDNA's sit above the one before them.

One thing both routes settle that the scripts could not: the Abandoned Mine (09HIK01A)
is played after the castle's stage 4 - WERDNA #02 0:59, before the Sleeping Princess
cave; Twitch part 3 3:15, after 06BLK05 and before 07CSL06E. The hand reading of the
Twitch run had missed it.

## The map's objects: who speaks each conversation (2026-09-23)

A scene script (02OLB01A.SCN) is dialogue and nothing else. The people are objects, built
by the *stage* script (02OLB01.SCN) as a run of field writes - `88 <field> <byte>` and
`89 <field> <word>`, both fixed length:

    88 00 02        field 0x00 = 2      kind: 2 is a person you can talk to
    88 02 04        field 0x02 = 4      sprite, an index into the map's own set
    89 04 00d2      field 0x04 = 210    x in pixels - tile 13
    89 06 00e2      field 0x06 = 226    y             tile 14
    88 0d 20
    89 1c 00c4 ...  the box it stands in
    89 2a 1a67      field 0x2a          -> its talk script

`89 2a` is the field that holds an address (script_decode.OBJECT_SCRIPT_FIELDS), and it
points at a stub of two or three instructions ending in `b0 <address>`:

    04 90 27        (some have a call first - turn to face the player)
    b0 00 00 3d     run the block at 0x3d00
    09 63 1a        then back to the next object

**0x3d00 is the scene slot**, and a scene script opens with a table of 3-byte jumps, so
`(addr - 0x3d00) / 3` is its entry number - the conversation. Smaller maps skip the scene
script and point `b0` at a block of the stage script itself. Either way the chain closes:
object -> stub -> block -> the lines the dump already has. `tools/npcs.py` walks it and
writes docs/npcs.json; 650 of the game's conversations get a speaker with a sprite and a
place on the map, which is what names the townspeople the game never names.

Two things it needs that are not in the object:

* **Which scene script is in the slot.** A town hub loads the pair together (`39 ... 18 02
  "02olb01"` then `39 ... 3d 02 "02olb01a"`), so that pairing is the default; a bigger
  town's stage script swaps scene scripts as the player walks between sub-maps, with
  `04 <block>` calling a one-line block that loads the next one, so an object takes the
  scene script of the most recent such call before it. An entry number past that file's
  entry count rejects the match.
* **Reading the objects at all.** The interpreter's own walk reaches only the blocks it can
  follow, and in the capital that left 38 of 39 objects unseen - the field writes sit in
  blocks nothing jumps to from the entry table. Because `88`/`89` are fixed length, a plain
  byte scan parses a run without decoding the file around it; requiring at least three
  fields, an in-range `89 2a`, and no overlap with a printed string keeps text from faking
  one. That took the count from 258 to 650.

The sprite number is per map (`02OLB 4` and `06BLK 4` are different people), so it is an
appearance, not an identity: 121 of them over 18 areas, listed in docs/sprites.md with a
line each one says, to be named by hand in tools/npc_names.json.

## A scene is gated where it is *called*, not where its text is (2026-09-23)

02OLB01.SCN is loaded twice - Albein's hub loads it at stage 0 with 02OLB01A and again at
stage 1 with 02OLB01B - so placing the file at the earliest stage that loads it put the
scene where Innes admits she took the gem *before* the manor visit she took it during.

The script says otherwise, in the object's talk stub rather than in the block:

    10 84 00 00 00 <else>   if Albein's counter is not 0, go to <else>
    b0 00 18 3d             (counter 0) the first-meeting conversation, in 02OLB01A
    <else>
    0c 66 00 <done>         if flag 0x66 is set, skip
    1d 66 00                set it
    b0 00 29 1c             -> the block where Innes admits the theft

So that block needs `0x84 != 0` (after the manor) and plays once. Neither fact is anywhere
near the text: the block itself has no test in it.

`translator_context.block_conditions` now reads them - for every `b0 <block>` it collects
the compares and flag tests whose span covers the *call*, and hands them to the block it
lands on (snapped to the containing block start, which is the unit the dump groups by).
Two things follow:

* **the Shown when column** gains the "first time only" it could not see, and names the
  visit the scene really belongs to rather than its file's first;
* **the reading order** moves those rows: `story_order.STAGE_AT` records where each
  (counter, value) falls, and a gated block is placed there when that is later than its
  script. 167 rows over 18 blocks move, the largest being 02OLB01's 125-row theft scene.

The variable is only trusted when it is a real counter - a whole-game clock or an area's
own 0x82+N. The hubs' scratch registers 0x7e/0x7f are compared constantly and mean nothing
across scripts; `stage_place` returns None for them, so those blocks stay where they were.

## Photographing the sprites (2026-09-23)

An object's x/y are **map units of 8 screen pixels**, not pixels and not tiles: the player
object sits at camera + (0x28, 0x1c) and is drawn in the middle of the 640x400 screen, so
0x28 units = 320 px. A tile is 16 px, i.e. two units. Measured in the emulator, by writing
the player's position and watching where the sprite lands - the first guess (pixels, tile =
/16) was out by a factor of eight and had been written into the workbook.

Two cheap tricks follow from it, both in `tools/sprite_shots.py`:

* **Panning.** The camera follows the player (camera = player - (0x28,0x1c)), so *writing*
  the player's position moves the view anywhere on the loaded map without walking.
* **A mannequin.** Borrow a live NPC's object slot, write a sprite number into its field
  0x02 and it is drawn as that sprite on the next frame. Take one frame with it there and
  one with it moved out of the world, and the pixels that differ are exactly the sprite -
  no need to know where a sprite is drawn relative to its anchor, and the background comes
  out as transparency. An *empty* slot is not enough: the draw routine reads other fields
  (facing, animation frame) that are zero there, and almost nothing is drawn.

What it cannot do is invent the map. Only the sub-map the player is standing in is loaded;
pan past it and the screen is either black or one tile repeated, which is what
`_is_a_place` rejects (a real corner of a town has 60-120 distinct 16x16 tiles, an
unloaded one a dozen). So sprites can be photographed from any state on the right map, but
a *place* can only be photographed where the game has really been.

**The teleport states cannot stand in for that.** `states/area_NN` change the map without
the map's own script running, so the tilemap is garbage and no object is drawn at all -
though panning to a region the game happens to have loaded does give real ground (that is
how the capital's sprites were taken from `area_06`). And the world map at
`r01_world_map` cannot reach the capital: walking all 25 of its step zones reaches the
manor, Old Town, Tini, Albein and four battles, but not Walkreuz, which is behind the
travel permit.

## Grouping the dump into conversations, and 31END (2026-09-22)

**Conversations.** A conversation is a **script block**: everything the game plays from
one trigger. Within a block, one line continues the same text box 0-7 bytes after the
last (`5c 6e 00 40 02`), and the *next speech* starts 13 bytes after it - the
` 00 09 15 30 04 06 30 40 02` that closes one box and opens the next.

That 13 is what the first version of this got wrong (2026-09-22). Measuring gaps alone
said "8 or more is a new conversation", which is true of a new *speech* and false of a new
conversation, so every back-and-forth came out as one scene per line: the Shinobu/Innes
exchange at the start of 02OLB01 was five scenes, 02OLB01A's 28 conversations were 40-odd,
and the whole dump had 3714 "scenes" instead of 1541. Sorting by story order then looked
broken - the order was right, the grouping was not. Group by block; fall back to the gap
(>= 0x40, a real run of code) only for the 31 files whose blocks cannot be decoded (00IPL,
12MRS, 28KDI, 29KNT, 25TOU00C...), which is what gets those ~1100 rows any context at all.

**31END.SCN has no text.** Its four dump rows are the only case in the game where *not one*
of a file's rows falls inside a `40 02 <string> 00` print. The file is x86 code - `e8 22 00`
(call), `eb 05` (jmp short), `2e` (segment prefix) - and the "strings" are stray bytes, one
of them `ab ab ab ab` filler. The ending is a program, not a script. Rows outside a print
elsewhere are *not* a reliable sign of this: menu choices (05SKS04 「全てを賭ける！」,
「重装備を渡す」) are drawn another way and are real text. Only the whole-file case is.
**Those rows are now out of the dump** (2026-09-22). Marking them was the half measure:
they are not text, so they do not belong in the translator's sheet at all.
`script_decode.is_code_row` is the shared test - the row overlaps bytes the decoder proves
are an instruction, or the file prints nothing - and it runs in two places, because the
workbook goes round a loop through the translator's Google Sheet:

* `dump.py` drops them when dumping, so a fresh dump never writes them;
* `tools/merge_dump.py` drops them when merging her sheet back, *after* step 1 has turned
  every formula into its value - so no `=E14` can be left pointing at a row that moved.

Seven rows went (06BLK05J 0x1ad, two in 06BLK07, 31END's four), none of them translated.
Checked rather than assumed: replaying reinsert's own page accounting (`page_rows` /
`cell_ends_page` / `typeset`) over the workbook before and after gives byte-identical
output for every translated row - an untranslated row still counts towards the text box it
sits in, so a removal *can* move a page break, and here it does not.
`reinsert.file_shows_no_text` stays as the last-ditch guard.

A second file joins 31END under the "prints nothing" test: **06BLK07.SCN**, a stage hub
that only loads other scripts. It has no `40 02` print anywhere, and its two "strings" are
bytes of those load instructions.

## The reading order has one rule, and a test for it (2026-09-23)

Everything above about ranks, places and steps is heuristic: each reads one kind of
evidence, and where two disagree a scene could land above the one that unlocks it. The
rule the sheet actually has to keep is simpler than any of them - **no conversation above
anything it causally depends on** - and it can be checked mechanically, so now it is.

`story_order.dependencies()` lists every need per script, block and entry point, read off
the scripts: *load* (a hub loads the script while counter var == n, or a script that is
loaded that way loads it - so it plays after the block that set var to n), *stage* (an
entry gated by `var >= n`), *flag* (an entry gated by `flag set`), *step* (a block that
needs the script's own progress counter), *chain* (a milestone block after the milestone
before it). A need is met by *any one* of its satisfiers. `story_order.causal_order` is a
topological sort that breaks ties by the order it is given, so only a scene that sits
above a need moves, and only to just below it; `translator_context.causal_pass` runs it
over the sorted rows at scene granularity, and prints what it moved and why. That list is
the measure of what the heuristics still get wrong. `tools/check_story_order.py` reads a
finished workbook back and reports every broken need (it must say 0), plus the softer
signals: an area's visit below the one before, the recorded playthrough's anchors out of
order (a route choice, not a fault: a frame is an upper bound on when content is
available), and "before X" lines placed below X.

Three details decide whether a need can be verified at all:

* **A satisfier with no text of its own** (a stage script that only sets flags) has no
  row. The first scene it loads stands for it (`stand_ins`), failing that the hub that
  loads it (11STG01 prints nothing and loads nothing) - early, never late, which is the
  safe side. A need is met as soon as any satisfier *with* text is above the row; only a
  need that nothing with text can meet is reported unverifiable, and there are none left.
* **A hub's write sits in a stage branch.** `10 <var> <n> <next>` skips to <next> unless
  the counter is n, so a write before <next> happens at stage n only (`hub_regions`).
  05SKS sets the manor's 0x85 to 7 inside its case for Skus stage 6, so it follows
  03YSK70, which starts that stage - which the hub as one block could never say, and
  which is what put the manor's stage 7 above its stage 6. A hub's case block also
  follows whatever started its stage (`stage_chain`).
* **A script has two ranks.** When it becomes *available* is the stage it is loaded at or
  the availability of what loads it; when its latest *milestone* fires can be much later,
  and passing that down to the scripts it loads was a cycle (17DRL04's late block starts
  the ruins' stage 6; 17DRL04A, which it loads, starts Blackfort's stage 7 long before).
  Blocks inherit availability; a scene follows its loader's milestone only when it holds
  no earlier milestone of its own (07CSL02A/B go with 07CSL02's five-counter advance).

What the check found in the sheet as it was (v19), all fixed at the source:

* **25TOU00C**, which advances four counters, has no block table, so `stage_writers`
  skipped it: the tower's whole moment was missing from the network, the tower sat at the
  end of the game and the 3,500 rows of scenes it unlocks (Sohei's second visit, Albein's
  stage 6, Skus's stage 5, McCulloch's stage 8) sat above it.
* **15MKR02G** took the playthrough's guess for its area over the stage it is loaded at.
  Every piece of evidence now raises a rank and none lowers it.
* **22MZI** was placed early by hand as part of the Isle of Forests chain, but it sets
  the ruins' 0x9c to 4 after 27KKI01 sets it to 3, and its text agrees ("three ruins
  left", back across the lake to McCulloch). A hub that is its whole area now takes its
  milestone's rank; the OVERRIDES entry stays for the place and says so.
* A stage-0 load needs nothing, a need met by the scene's own block is met, and a hub's
  arrival text (06BLK's name plate, in the block that starts Skus's stage 7) is not a
  milestone - three false dependencies that would have dragged the opening apart.
* A gate of "counter == 0" is the state the game starts in, not a need. `stage_starts`
  read a floor of 0 as "the first block that writes the counter" and put Innes's first
  meeting (02OLB01A #9, `10 84 00 00 00` in its talk stub) after the manor visit that
  advances Albein to 1 - the one row order a player would notice at once, since it is the
  first conversation of the game after the opening.

The check proves nothing is too *early*; the Innes case was a scene too *late*, which it
cannot see. Looking for more of those (every block the placer nudges past its script,
every script whose scenes end up in two places) found these, all fixed at the source:

* **A block that advances several counters** was one need with every predecessor as an
  alternative, so any one of them satisfied it. Each counter's predecessor is its own
  need (`chain_groups`); flattened, 18KSK's need was met by two of its three counters
  while the one that mattered - 17DRL04A's block that starts Blackfort's stage 7 - went
  unchecked.
* **A milestone block sorts at its own rank**, not its script's (`rank_of`). A script
  sorts at its latest milestone, and a block that has to precede something earlier than
  that would otherwise sort below it: 17DRL04A's stage-7 block now goes before 18KSK
  and its stage-9 block and chatter after. Hubs with scripts of their own are excluded
  (their text is the arrival).
* **The playthrough dated City McCulloch (16MKI) at part 4**, from a frame of a later
  return there; its exit block sets McCulloch's counter to 4, and Kikuichi's first visit
  takes it to 6. A weak rank on a script that holds a milestone now yields to the
  milestone: no earlier than its predecessors, and just before its successor. The
  area's other scripts follow (weak scripts never rank later than the counters date
  their area), and so does the area it is reached through: `FROM_BASIS` now actually
  matches "first reachable from X" (it lacked the space after "from" and only ever
  matched the hand-written mine entry), so McCulloch's first visit is no later than
  16MKI. Result: castle visit 2, Dragon's Lair, McCulloch 1-5, 16MKI, Kikuichi - the
  order the video shows, with 16MKI61's part-4 frame the one anchor left disagreeing.
* **Block places pushed past satisfiers of an earlier rank**, which the rank already
  orders. The push cascaded (27KKI01 past 16MKI01B's late place, then everything after
  it in three chains) and put a castle scene 1,200 rows below its visit; now a block is
  nudged only past a satisfier of its own rank or later. 7 blocks are nudged, down
  from 28, each by a flag or gate in its own script.
* **A satisfier with no block table** (25TOU00C) stood for "the first row of the
  script", so the scenes it unlocked were emitted between its own two scenes; it now
  means "after the whole script".
* **The rank fixpoint iterated a set** for a fixed twelve rounds, so the visiting order
  changed with Python's hash seed and the deepest chain (seventeen) sometimes did not
  settle - a different sheet from one run to the next. Nodes are visited in a fixed
  order, for as many rounds as it takes; the basis file is now byte-identical across
  seeds.

Not changed, and worth knowing: a script sorts as one piece at its latest milestone, so
chatter available at the start of a visit sorts with the milestone that ends it
(03YSK01B's 33 ordinary rows, 03YSK70's 41, 20NNP93's 104). The counters cannot say
whether a milestone is the arrival or the end of the visit, and keeping the file together
is the better default for a reader; none of it is causally wrong.

**Inside a visit, the scripts leave the order open** and the sheet fell back to file
order, which put Innes's conversation after the whole town (the player starts in her
house) and the manor's jewel scene first (it is in the basement, behind a man asleep in
the doorway until the rest has been explored). Nothing in the game data settles this:
the routes in `routes/` are test drives (noclip straight to the jewel), the recorded
playthrough has one frame per area, and the map positions the Who column shows cover
276 of the 1,541 scenes - talk objects only, not walk-on events like the jewel, and in
one coordinate space per sub-map with no connectivity between them. What does settle it
is a player: `tools/play_order.json` lists scenes in the order they are likely met, and
`translator_context.causal_pass` adds each consecutive pair as a soft need. The hard
needs are sorted alone first, so an entry that contradicts one shows up as a cycle only
the soft edges create; it is dropped and named. A spatial rule (nearest scene from the
spawn point, which the `area_NN` states give) is possible for the positioned scenes
later, if the file grows tiresome.
* Weak evidence never contradicts the counters: a visit dated from the video cannot come
  later than the next visit of the same area (23SOH), an area cannot come later than one
  reached only through it (08CKD before 09HIK, whose scene advances the castle), and the
  hand-pinned ending outranks everything.

## Order inside a visit, from the game and from the playthrough (2026-09-24)

Two automatic sources feed `tools/play_order.json` now, both on the record so a human
can overrule them:

**`tools/play_tour.py` - a nearest-first player in the emulator.** From a real state it
picks the nearest untried target by *walking distance*, walks there, does what a player
does (talk, step in), reads what plays, and goes on from there; what it cannot reach is
retried after everything else, which is how a doorway that only opens later comes later.
Walking distance is real: `tools/walkgrid.py` learns a map's walkable tiles by asking the
game - a tap in a direction either moves the player exactly one tile (two map units) or
slides it along a wall, so a move counts only when the delta is the direction's own
vector - breadth-first from the arrival tile with compressed states on the frontier (8 ms
a probe, 3 ms a reload; a few hundred to a few thousand tiles a map, up to five minutes).
Three things it had to learn the hard way: talking chases NPCs with tiny taps and leaves
the player off the two-unit lattice (a one-frame tap moves one unit, so it snaps back);
the scripts in RAM have relocated entry tables, so matching loaded scripts by header
finds nothing (a page's scene is taken from the dump row its text matched, and a page that
is only a name plate and a word is ignored - "Innes / Hmm?" is in a dozen rows); and a
scene's arrival zone is the door just come through, which a player does not turn round
and take. Output: `docs/play_tour/<name>.json`, folded in with `--to-play-order`.

**The Twitch VODs, sampled densely.** The browser method above, run as a loop over each
VOD: every 5-6 s, seek, draw the game crop, and call the frame a text box when over half
of the strip x150-1270 y455-640 is the box's dark navy (it is not mid-grey as the earlier
note says; that was a status panel). Each hit keeps a fingerprint (a thresholded 64x12
downsample), so consecutive identical boxes collapse and a run of distinct boxes with
gaps under 20 s is one conversation. `docs/vod_samples/partN.json` is that list; the
sampler runs in the page (one tab per VOD, in parallel) at ~2.5 s a sample, so a
20-hour playthrough is a few hours of background work. Identification is still by eye:
five text strips at a time are drawn on the page's canvas, screenshotted, read, and the
readings go through `tools/vod_read.py`, which finds each fragment's dump row (the same
line in two visits' scripts is settled by time - the script nearest after the previous
anchor in the story order) and appends it to `docs/video_anchors.json`. Screenshots of
the pane fail whenever another tab is seeking video, so the samplers are paused while
reading. What was tried and dropped: matching the frame's text rows against MS Gothic
renderings of every dump line in the page, which would have made the reading automatic -
the page cannot fetch the lines (Twitch's page policy blocks it), and the stream's
scaling of the game screen is not the clean 1.8 the crop assumed, so it needs its own
calibration before it is worth the effort.

What Part 1 of the playthrough says about the two visits that started this: Innes is
talked to first (t=1245), then the town; at the manor the household is met first
(the chancellor at 2440, the sleeping man at 2375 and 2775), the jewel scene comes at
2875, the guards at 3005. The hand-written entries were right, and now they are backed.
