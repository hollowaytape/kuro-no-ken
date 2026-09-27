# Building the game yourself (Windows)

Edit the English in the workbook, double-click `build.bat`, play the result. First-time
setup is about 15 minutes.

## One-time setup

1. **Install Python 3.11** from python.org. On the first installer screen, tick
   **"Add python.exe to PATH"**.
2. **Put the two folders side by side**, for example:

       C:\kuro\KuroNoKen\     <- this project
       C:\kuro\romtools\      <- the shared tools (contains bin\NDC.EXE)

   The build finds `romtools` and `NDC.EXE` by itself when they sit like this, so you
   don't need to change PATH or PYTHONPATH.
3. **Install the Python packages.** Open a Command Prompt in `KuroNoKen` and run:

       pip install -r requirements.txt

4. **Add the game files** (you receive these separately, not through git):
   - `original\` - the unpacked game files, including `original\decompressed\`
   - `original\Blade of Darkness (Kuro no Ken).hdi` - your copy of the game
   - `KuroNoKen_dump.xlsx` (the translation) and `KuroNoKen_pointer_dump.xlsx`, in the
     `KuroNoKen` folder
5. **Install an emulator** to play the result. Neko Project 21/W (np21w) opens `.hdi` disk
   images directly.

`build.bat` checks all of the above before doing anything. If something is missing, it
says exactly what, in plain words.

## Every time

1. Edit the **English** column in `KuroNoKen_dump.xlsx` and **save** (the build reads the
   last saved copy).
2. Double-click **`build.bat`**. It takes about 4 minutes and ends with either
   `BUILD OK` or a short explanation of what went wrong.
3. Open `patched\Blade of Darkness (Kuro no Ken).hdi` in the emulator.

Your save files are carried over from the previous patched disk, so you can keep playing
from where you were.

## Reading the script in story order

The sheet lists every file alphabetically, and within a file by position, which is not
the order the game plays it in. The context workbook adds a column for that:

- **Story order** is a number for every line. Sort by it to read the game in the order
  it plays: the intro, the opening at Innes's, the first manor visit, back to Albein,
  and so on.

The order is built in two steps. First, **which moment of the story** a scene belongs to.
Each area counts its own visits with its own counter, and those counters are advanced from
*other* areas - the castle's third visit is started by a Kikuichi scene, the capital's sixth
by a Skus one. Fourteen of them chain together into 38 facts of the form "this happens
before that", all crossing areas, and they agree with each other; the longest chain through
them is eleven moments deep. Second, **where inside that moment** a scene sits, which is the
area-by-area order. That is why the capital's six visits are spread through the sheet
instead of sitting in one block.

Inside one file there is a third step. A script can cover a whole visit - 03YSK01A is the
entire first time at the manor, from arriving to seeing the jewel to being called a thief
to escaping - and it tracks where in that sequence the player is with a counter of its own.
The file's *first* block is the scene for walking back in after the escape, so file order
opened the manor with its ending; reading that counter puts it last, where it belongs. 56
scripts have one.

Checked against a recorded playthrough of the Japanese game (24 scenes with a timestamp
that the sheet still holds), 4 sort earlier than they were played; before the counters
were read together it was 10 and 1330 rows. Three are scenes the game makes available
before the player happens to walk into them (two towns in the opening, one room of the
last dungeon), and the fourth is City McCulloch, which that player returned to late in
the game while the counters put its story visit before Kikuichi. None is an error - the
sheet is in the order the game *offers* the scenes, and a player can pick up a town's
optional chatter several visits late.

How each script's position was worked out is kept out of the sheet - it is our debug
detail, in `docs/story_order_basis.txt`. For the record, in order of how solid it is:

- *"… loads it at stage N"* or *"advances story counter …"*: proven from the game's
  own scripts.
- *"… loads it at its stage N (var 0x89), which 27KKI01 starts"*: the same, for an area
  the game revisits. Each area counts its own visits, so the capital's 42 scripts are
  six separate visits and the castle's 28 are eight, spread through the story rather
  than bunched together; the script named is the one that opens that visit.
- *"first reachable from …"*: the area itself isn't dated, but the scripts show the
  earliest point the player can travel there, so it's placed just after that.
- *"seen playing in …"*: the scripts don't date it, but a recorded playtest shows its
  lines actually playing at a known point in the story.
- *"seen in the playthrough at part N …"*: taken from a recorded human playthrough of
  the Japanese game, which is the most direct evidence of all.
- *"the Isle of Forests chain …"*: placed from what the game itself says about the
  quest, rather than from watching it — the least certain of these.
- *"with its area … not placed by the scripts"*: the right area, but only in file
  order within it.
- *"the Fountain of Sacred Waters …"*, *"reached only from …"*: placed from what the
  game says about the place, when nothing else dates it.

Every one of the game's 30 areas now has a position. Three things sit at the very front
because they are not part of the sequence at all: the intro, the world map, and 99CMN,
the common script (yes/no prompts, shop lines) that the game uses from the first menu
onwards.

**You will see the same place more than once, and that is right.** The story sends the
player back to the capital six times, the castle eight, Albein and the manor seven each;
every return has its own scripts and its own text, and sorting by Story order interleaves
them the way the game does. The capital's text is no longer one 42-script block.

Inside one conversation the order is always right. Optional chatter (townspeople you can
talk to in any order) has no single true order; it stays in file order unless someone
who has played the game says otherwise in `tools/play_order.json` - a short list of
"these scenes, in this order" for the visits where file order misleads (in Albein you
start in Innes's house, so her conversation comes before the rest of the town; in the
manor the jewel is behind a sleeping man who only moves once you have explored). Add to
it freely: an entry never overrides what the scripts require, and the build says so if
one tries.

One rule holds everywhere, whatever the steps above decided: **no conversation sits above
anything it depends on**. If a line only plays after a counter has been advanced, a flag
set, or a script loaded on a later visit, the conversation that does that is above it.
The sheet is checked for this mechanically before it is handed over
(`tools/check_story_order.py`), and where the steps above got it wrong the builder moves
the conversation down to just below what it needs. So when a scene seems to come out of
nowhere, look *up*: what it depends on is there.

**In Google Sheets, sort with a Filter view** (Data → Filter views → Create new filter
view, then sort the Story order column). Don't sort the sheet itself. Google Sheets
stores some repeated English as formulas that point at other rows (`=E14`), and sorting
the rows makes those formulas point at the wrong line. A filter view only changes what
you see. Row order makes no difference to the build either way.

## The colours on the English column

Two of them, both the translator's own, and both carried through every rebuild of the
sheet - the scene shading deliberately stops at the English column so it can never paint
over them.

**Green is a name plate that fills itself in.** Those cells hold a formula reading the
name out of **Names + Places**, so a character's English name is written down once and
appears on all the rows that say it: `='Names + Places'!C2` on every シノブ. Change the
name in the glossary and every plate follows. 956 cells carry it.

The formulas had been flattened - somewhere in the round trip a workbook was loaded for
its values and saved again, which keeps what a cell displayed and throws away how it got
there, and for the rows a spreadsheet had never calculated it kept nothing, so 785 of
them came back empty. They are back now, restored from the glossary for every green cell
whose English was blank or already said what the glossary says. A green cell saying
something else is the translator overriding the glossary on purpose and keeps its own
wording.

A few lines appear twice in the dump, and both rows have to agree - the build refuses a
file where one row says `Keiuss` and its twin says the formula - so the choice is made per
line of the game, not per row of the sheet.

**Pink is "not sure about this, come back to it"**, on 24 lines. Nothing touches it: it
stays on the line it was put on, wherever that line moves to in the order.

**The build never sees a formula.** `reinsert.py` resolves one to the name it points at as
it reads the sheet, so the game gets `Shinobu`, and a formula that names nothing in the
glossary is treated as an empty cell - the row keeps its Japanese. It is never written
into the game as text, which is what would otherwise happen: romtools reads the workbook
without asking a spreadsheet to calculate it.

## What the columns mean

The sheet is laid out in reading order, and **the rows are already in story order** - row
2 is the first line of the game, and there is nothing to sort:

| | |
|---|---|
| A **Area** | the place, from the Names + Places glossary |
| B **Scene** | the conversation this line belongs to |
| C **Who** | who is speaking, and to whom |
| D **Shown when** | what has to be true for the line to play |
| E **Japanese** | the game's line |
| F **JP_Len** | its length |
| G **English** | **your column** |
| H **EN_Len** | its length |
| I **Comments** | yours |
| J **Filename**, K **Offset** | which script the line lives in, for the build |

Where we have a photograph of the spot a scene happens on, it is the **tooltip on the Who
cell** - hover and the picture appears. It used to be a column of its own and cost 240
pixels of width on every row for something you want once.

- **Scene** is one continuous conversation — every line the game shows in an unbroken run
  of text boxes, from one trigger. `17DRL01B #5` is the fifth conversation in that file.
  You can see where a scene starts and ends without reading the column:

  each scene has its own **background shade**, alternating pale blue and white, so one
  conversation reads as one block and the change of colour is the boundary. It is a fill
  rather than a ruled line on purpose: Excel carries a fill with the row when you sort but
  leaves borders behind, so lines ended up in the middle of conversations.

- **Who** is who is speaking, and who they are speaking to: `Shinobu -> Innes`,
  `市長 -> Keiuss`. Three sources, in this order:
  1. the game's own **name plate**, held for the rest of that conversation, so a
     continuation line still says who is talking;
  2. a short **note you left in column G** (`Innkeep`, `Girl with dog`, `Snotty
     aristocrat`) — still the best way to name someone, and it now covers the whole
     conversation rather than the one row;
  3. the **person on the map**. Every NPC is an object in the game's data with a sprite
     and a position, and the object says which conversation it speaks — so an unnamed
     townsperson shows as `sprite 8 @19,15`: sprite number 8, standing on tile 19,15.
     The position is what tells two people with the same sprite apart.

  Sprites can be given names in `tools/npc_names.json` — open `docs/sprites.html`, which
  lists all 114 of them **with a picture of each one** (taken out of the running game) and
  a line they say, and type the names straight into the page. Once named, `sprite 8 @19,15`
  reads `Scholar @19,15` instead. **Blank means nothing in the game names them**, not that
  nobody is speaking.

- **Where it happens** (the last column) is a photograph of the spot, taken out of the
  running game, with the NPC standing where the game puts them. It sits on the row the
  scene starts on, and that row is made tall to hold it — so a tall row *is* the start of
  a scene.

  There are only six of these so far, and that is deliberate. A sprite *number* is an
  index into whichever set of graphics the game had loaded at that moment, not a name, so
  a picture is only trustworthy for the part of the map the game was actually standing in.
  Pictures are now taken only for NPCs within a screen of that spot; the rest wait until
  the game has been walked there. **If a face ever looks wrong for the words, trust the
  words** — and tell us, because it means the picture was taken too far away.

- **Shown when** is what has to be true for the line to play:
  - *"visit 4 of 6"* — which visit to this area the line belongs to. The story returns to
    the capital six times and to the castle eight, and each visit has its own scripts.
  - *"first time only"* — the player sees this once; later visits get something else.
  - *"after 06BLK02A #4"* — this line waits on something that happens in that scene.
    **The cell is a link**: click it to jump to that scene, or hover to read its first
    lines without leaving your place.
  - *"before 06BLK04J #18"* — the opposite: it plays only until that scene happens.
  - *"after something the scripts never name"* — the condition is real but nothing we can
    decode sets it. Three flags in the game.
  - *"always"* — no condition at all.
  - **Blank** means "not known" (about 30 files can't be decoded), not "no condition".

  Rows that were never text at all are gone: the dumper read bytes, so a few jump
  addresses came out looking like Japanese. Seven such rows have been removed (none was
  translated), and the build still refuses English in one if it ever reappears.

## Writing lines that fit

- **Line wrapping is automatic.** Write each cell as one sentence or paragraph. The
  build wraps it to the text box (48 characters, 4 lines plus the speaker's name) and
  starts a new page when the box fills.
- **Speaker names** - a row whose Japanese is just a name is the game's name plate, and
  the **Who** column repeats it for the rest of the conversation. Keep them short and
  consistent; use the Names + Places sheet.
- **Rows between two hairline rules share one text box**, so the game breaks the line
  where the *Japanese* cell ended: end the English cell at a natural pause, not
  mid-sentence.
- **Shown when = "first time only"** means the player sees this line once: the first
  conversation, before the scene's flag is set. Repeat visits show something else.

### Scripts that can't grow yet

A few scripts have a format that isn't fully understood. In these, every English line
must be **no longer than the Japanese** (count bytes: an English letter is 1 and a
Japanese character is 2). As of September 2026 these are:

`07CSLI00`–`07CSLI04`, `09HIKI01`, `12MRS`, `13SLP`, `18KSK`, `22MZI`, `25TOU00A`,
`25TOU00C`, `28KDI`, `29KNT`, `30IZM`

If a line there is too long, the build still succeeds but leaves that script in Japanese
and names the line: `WARNING: 07CSLI00.SCN left in Japanese - ... 'Shinobu' (max 6)`.
Names are the usual problem: シノブ is 6 bytes, and "Shinobu" is 7.

### Scripts with a size budget

Every script must fit the memory slot the game loads it into, and a few also contain a
section that can't grow at all. When the English for a script is too long overall, the
build leaves **that script** in Japanese and says by how much:

`WARNING: 02OLB02A.SCN left in Japanese - the English does not fit: it is 324 bytes over its 0x1400-byte RAM slot.`

Shorten that script's lines by at least that many characters (use the **Scene**
column to find its conversations) and build again. As of the September 2026 merge:
02OLB01 (662 over), 02OLB02A (324), 03YSK69 (320), 03YSK01A (201).

## When the build stops

- **"setup is incomplete"**: follow the listed fixes.
- **"reinsertion failed ... @0x...":** the message names the script and the row's
  offset (the Filename and Offset columns). Usually the row is too long for a fixed-length
  script, or a Japanese cell was edited by accident. Only edit the English column.
- **"… is not text: the dumper read script code as Japanese"**: that row is really game
  code that happens to look like a Japanese character. Clear its English.
- **"… appears twice in the workbook with different English"**: the same line exists in
  two rows (02OLB03A is in the sheet twice) and the two English versions differ. Keep one
  and clear the other.
- **"A POINTER CHECK FAILED"**: the build finished, but the game may crash in the
  named script. Don't spend time testing there. Send `patched\build_*.log` to the
  project lead.
