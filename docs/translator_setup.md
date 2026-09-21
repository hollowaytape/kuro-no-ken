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

## Writing lines that fit

- **Line wrapping is automatic.** Write each cell as one sentence or paragraph. The
  build wraps it to the text box (48 characters, 4 lines plus the speaker's name) and
  starts a new page when the box fills.
- **Speaker names** (column **Kind** = `name` in the context workbook) are labels,
  so keep them short and consistent. Use the Names + Places sheet.
- **Column Continues = "-> next cell"** means the game keeps the same box open and the
  next row follows straight on. The game breaks lines where the *Japanese* cell ended,
  so end the English cell at a natural pause, not mid-sentence.
- **Shown when = "first time only"** means the player sees this line once: the first
  conversation, before the scene's flag is set. Repeat visits show something else.

### Scripts that can't grow yet

A few scripts have a format that isn't fully understood. In these, every English line
must be **no longer than the Japanese** (count bytes: an English letter is 1 and a
Japanese character is 2):

`07CSLI00`, `07CSLI01`, `07CSLI02`, `07CSLI04`, `09HIKI01`, `12MRS`, `25TOU00A`, `25TOU00C`

If a line there is too long, the build still succeeds but leaves that script in Japanese
and names the line: `WARNING: 07CSLI00.SCN left in Japanese - ... 'Shinobu' (max 6)`.
Names are the usual problem: シノブ is 6 bytes, and "Shinobu" is 7.

## When the build stops

- **"setup is incomplete"**: follow the listed fixes.
- **"reinsertion failed ... @0x...":** the message names the script and the row's
  offset (the Filename and Offset columns). Usually the row is too long for a fixed-length
  script, or a Japanese cell was edited by accident. Only edit the English column.
- **"A POINTER CHECK FAILED"**: the build finished, but the game may crash in the
  named script. Don't spend time testing there. Send `patched\build_*.log` to the
  project lead.
