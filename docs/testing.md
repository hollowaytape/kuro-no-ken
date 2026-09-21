# Testing the translation

Four checks, cheapest first. All of them run headless on np2core (`kuro_core.CoreEmu`);
none needs a GUI emulator.

## 1. After every reinsert: are the pointers still sane?

```
python tools/check_pointers.py
```

Static, a second or two, exit code 1 if anything is wrong. It decompresses each patched
script and checks that entry *i* of its `09 <addr>` table still points at the same block
it did in the original. This catches the crash class that has cost the most time here -
English of a different length shifts a file, and any address not in the pointer sheet
stays behind. See "The entry table is a pointer table too" in `engine_notes.md`.

## 2. Does every line fit the text box?

```
python tools/verify_text.py --workers 6            # ~30 min for the whole workbook
python tools/verify_text.py --files 02OLB02A.SCN   # or one file
```

Renders each workbook cell - as `reinsert.typeset()` would write it - through the game's
own text routine and reads the text layer back, so the wrapping, page breaks and glyphs
are the real ones. Reports rows/columns used, text that never reached the screen, and
anything drawn that the script didn't ask for. The box is 50 columns x 5 rows; a 6th
line is silently dropped.

For one string, without the workbook, use the bench directly:

```
python tools/bench.py r03_manor_inside
```

## 3. Verify scripts without playing to them

Reaching a line in game is the slow way to test it, and much of a script is behind story
flags. Two facts remove the need:

* a trigger zone names its block through a word table (`[16d8:0932]`), and that table is
  writable, so any address can be made to run;
* a script does not have to be loaded by its map - `bench.load_script()` writes a patched
  file straight into a slot, and the routines it calls (0x3006 open window, 0x3015 close)
  are always resident.

So every block of every script can be run from one save state:

```
python tools/verify_blocks.py ysk2_final              # the scripts this state has loaded
python tools/verify_blocks.py ysk2_final --inject     # every translated script, injected
python tools/verify_blocks.py ysk2_final --inject 02OLB02A.SCN
```

Each block is wrapped in the frame a real caller would provide (open, call, close), only
blocks the decoder proves contain a print are run, and every page is attributed to its
dump row. The report lists issues and a block -> dump row map, which is also the answer
to "where does this line appear".

**This catches what `verify_text.py` cannot.** That renders each workbook cell alone on a
fresh page; the game shows consecutive cells in one box, so a cell that starts halfway
down a page can overflow. Six pages in the translated scripts end early this way - the
rest of the sentence is never drawn - and all of them pass a per-cell check.

Related, `tools/split_sentences.py` lists the 73 places where the English runs on
from one cell into the next. The game breaks lines where the *Japanese* did, so the tail
of the first cell gets a line to itself:

```
I was prepared to receive the full wrath of
the                     <- the cell ended here
Grand Duke's over the loss of the Starlight
```

That is an editorial fix (end each cell at a natural break), not a reinsert bug.

### What this covers, and what it does not

| dump rows | | verified by |
|---|---|---|
| `.SCN` | 9960 (94%) | `verify_blocks.py --inject --all-scripts` - 2098 blocks in ~17 min |
| `.BSD` (battle scripts) | 589 (6%) | **nothing yet** - a different format, loaded only when its battle starts |

The BSDs are barely translated (1 row), so the gap is not urgent, but it is real: their
text has to be checked by fighting the battle (`tools/merc_fight.py` is the worked
example) until something like the block runner exists for them.

Of the 2098 blocks, 373 print text. The rest are movement, flags and setup - and some
dialogue that only speaks when its map's objects exist, which injection does not
reproduce. So a clean run means "nothing broken in what played", not "every line seen".

Two categories in the report are *not* defects, and both fooled me first time round:

* **awaiting-reinsert** - the workbook has English but the file is not in
  `FILES_TO_REINSERT`, so the game shows Japanese by definition. All 18 of these were
  speaker names in untranslated areas.
* **truncated** - `check_page` sees one page at a time, so a cell that `typeset` split
  across two pages looks cut off. It is only real when the tail never appears in the
  block at all; the runner now checks that before reporting it.

## 4. Flags: reach the parts of the script that are gated

Progression flags are a bit array at 16d8:08d2, and the interpreter's flag instructions
(`0c` branch if clear, `0d` branch if set, `1d` set) make them readable statically:

```
python tools/flag_map.py                    # docs/flag_map.md: what each of 227 flags gates
python tools/flags.py A B       # which flags an event set, by diffing two states
python tools/flag_demo.py STATE BLOCK FLAG   # run a block with the flag both ways
```

Setting one changes which branch a block takes - the manor Chancellor gives his three
page introduction with flag 0x73 clear and a single line once it is set - so both sides
of a gated conversation can be checked without reaching that point in the story.

## 5. Every area, in context

Injection runs a script without its map. To test one *with* its objects, NPCs and zone
tables, teleport there instead (see engine_notes.md - the destination is global word
variable 3):

```
python tools/area_states.py                  # a save state in each of the game's 30 areas
python tools/sweep_areas.py                  # every NPC and trigger zone, all of them, ~15 min
```

Two things to keep in mind when reading the result:

* **An area whose scripts are untranslated tells you nothing about the patch.** Arriving
  out of story order means the flags its scripts expect were never set, so a trigger can
  branch into an invalid state and quit. mkr1 and isk1 do exactly that, and every script
  they load is byte-identical to the original. Use these sweeps as a before/after
  comparison once an area is translated.
* **A teleport only reloads the slots the new area needs.** isk2 kept the manor's script
  in slot 1 and reported 19 crashes that were the state's fault. `area_states.py` now
  detects a foreign script and labels the state.

The full run on the current build: 30 areas, 27 clean, 3 explained, none attributable to
the translation.

## 6. The whole pass

```
python tools/check_pointers.py               # stale pointers                    seconds
python tools/stale_report.py     # decoder-verified, every script     ~1 min
python tools/verify_text.py --workers 6      # all 1922 cells rendered           ~25 min
python tools/verify_blocks.py S --inject     # every block of every script       ~17 min
python tools/sweep_areas.py                  # every NPC and zone, 30 areas      ~15 min
```

About an hour, unattended, from any save state - and it does not need the story played
in order, which is what made this worth building.

## 7. Play it

```
python tools/autoplay.py --start auto_run26_06 --steps 120 --workers 4
```

From a save state it forks a trial per NPC and per trigger zone, runs them in parallel,
reads every page through the same checks, and commits to whatever showed the most new
text. Writes `routes/<run>.json`, `test_reports/<run>_report.txt` (issues, deduplicated,
plus the transcript) and `states/<run>_NN.np2core`.

Issue kinds worth acting on: **crash**, **not-inserted** (the workbook has English but
the game shows Japanese), **truncated**, **overflow**, **garbage**. **untranslated** is
expected for most of the game. Shop and status panels are filtered out; a Japanese line
that matches many workbook rows is reported without a source rather than blamed on an
arbitrary file.

Starting states matter: `python tools/rate_states.py NAME...` says which are on a
real map and playable. A state saved just after a lost fight cannot be recovered from,
and the run will say so.

## 8. Where is the text?

```
python tools/script_map.py     # docs/script_map.md - every dump row -> the block that prints it
python tools/map_report.py     # docs/game_map.md  - what the autoplayer reached, merged
```

`script_map.md` is static and covers the whole game (8858 of 8910 rows placed) plus a
translation-progress table by area. `game_map.md` covers only what has been played, but
knows which map each script is loaded on, and what each NPC and zone actually does.

## 9. Battle scripts (.BSD)

589 dump rows live in 47 battle scripts, and until now nothing checked them: a `.SCN`
block can be called (section 3), but a battle is run by the battle engine, and no script
opcode appeared to say "start this battle". Two things closed the gap.

**Statically**, `verify_bsd.py` round-trips every file, grows every line and checks that
all 1621 absolute offsets still point at the same bytes, and that every dump row lands
inside a text region reinsert can reach:

```
python tools/verify_bsd.py            # 47 files with text
python tools/verify_bsd.py --all -v   # all 219
```

It found two real problems. `bsd_tool.reassemble` wrote a NUL after every text region,
but two of the 215 regions are not NUL-terminated - `C042_X10` ends one with `0x01` and
`D031_S10`'s last region runs to the end of the file - so translating either would have
destroyed a byte of script or added one. And six dump rows (five in `DL30_Z10`, one in
`C051_S10`) are not text at all but x86 code that happens to decode as Shift-JIS
(`1e 50 53 8c c8 8e d8 bb` -> the dumper's "己借ｻ"); they must never be translated.

**At runtime**, three scripts name a BSD inline - `28KDI`, `29KNT`, `20NNP93` - and the
bytes around the name give the convention:

```
8c 02 "dac_11" 00      set the battle background
b6 02 "d\DL21_O10" 00    fight this battle script
83                       end of block
```

So opcode `0xb6` starts a battle by name, and a battle can be run from anywhere with the
same synthetic-block trick `bench.render()` uses for dialogue - no route, no map, no
staged disk:

```
python tools/bsd_play.py D010_X10.BSD          # run one battle and read its text back
python tools/bsd_play.py --all --seconds 45    # every battle script with text
```

One more thing is needed to make the lines actually appear. A battle script gates its
dialogue on bytes of itself: sites of the form `cmp cs:[var], imm` test the phase of the
fight - an enemy having transformed, the boss below half health - and skip the lines
after them otherwise. A fight that ends in two turns never reaches most of its script.
`bsd_play.guard_sites()` reads every such comparison out of the file, and `phases()`
enumerates the assignments, because the same byte is usually compared to 0 at one site
and 1 at another, so no single setting reaches everything. Each combination gets one
short fight and the lines are merged:

```
on stg.mpc: running D010_X10.BSD (25 byte block at 0x380)
forced 2 guard(s): 0x302=1, 0xc60=1
                      ゼフュードル
                      「お前・・・
                      　変わった魔法を使いやがるな。
                      　だがよ、その程度じゃ、おれには
                      　勝てねえな！」
```

**What this reaches today, and what it does not.** Two limits are worth knowing before
trusting a sweep:

* *Archive mounting.* The game keeps one `.FA1` open at a time, so a battle can only be
  started from a map whose area has its archive. A sweep over six area states started 16
  of the 47 files; `--states` takes the list to try, and `tools/bsd_area_probe.py`
  is a first pass at working out which area mounts what (its per-area column is wrong -
  it reports the map it is on *after* the probe, mid-battle).
* *How far the fight gets.* With the player's stats as the test states have them, one
  Attack ends the fight, and defending does not help - these are scripted battles that
  end on their own. So what comes back is a boss's opening exchange, not its whole
  script: `C021_X10` has 96 dumped rows and shows 6. Reaching the rest means following
  the battle script's own control flow, which is the .BSD equivalent of what
  `script_decode.py` does for .SCN and has not been done.

`bsd_stage.py` is the earlier, slower route: it substitutes a BSD's contents into another
member of an archive and rebuilds the disk, so a normal encounter plays it. `bsd_play.py`
supersedes it, but staging is still the way to test a file *as the game would load it*,
resources and all. Note that a save state carries the game's cached archive directory, so
a state made on the normal build desyncs on a staged disk - `tools/boot_staged.py`
cold-boots one and teleports to the world map in about 20 seconds.

## When a run finds a crash

```
python tools/repro_crash.py STATE step 3                  # reproduce it
python tools/reinsert_without.py 03YSK01B.SCN             # build a disk without one file
python tools/repro_crash.py STATE step 3 --disk=v_wo_03YSK01B.SCN.hdi
```

If it crashes translated and not untranslated, it is ours. `tools/ptr_audit.py`
and `tools/crash_watch.py` then show which offsets the interpreter reads as
addresses, which is usually enough to name the bad pointer.
