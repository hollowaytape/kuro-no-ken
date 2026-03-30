# Copilot Instructions — Kuro no Ken Fan Translation

## Project Overview

This is a Python toolchain for fan-translating **Kuro no Ken (Blade of Darkness)**, a PC-98 game. The workflow extracts Japanese text from the game ROM into an Excel spreadsheet, a human translator fills in English translations, then the toolchain reinjects the translated text back into the ROM, updating pointers and repacking archives.

## Commands

```bash
# Full workflow (in order):
python dump.py              # Extract Japanese text → KuroNoKen_dump.xlsx
python find_pointers.py     # Find pointer locations → KuroNoKen_pointer_dump.xlsx
python reinsert.py          # Apply translations from Excel → patched ROM

# Analysis:
python analyze_control_codes.py      # Full BD.BIN dispatch table analysis (256 entries)
python find_pointer_control_codes.py # Focused summary of pointer-related control codes

# Utilities:
python fa1.py               # Unpack FA1 archives from original/
python fetch_memory.py      # Copy memory.bin from emulator debug tools
python slice_memory.py      # Extract a single decompressed file from memory.bin
python mark_duplicates.py   # Find duplicate .SCN files by header
python format_table.py      # Mark duplicate text entries in dump spreadsheet
```

There are no tests, linters, or build systems. Verification is done by running the patched ROM in a PC-98 emulator.

## Architecture

### Translation Pipeline

```
dump.py → KuroNoKen_dump.xlsx → [human translation] → reinsert.py → patched ROM
                                                            ↓
find_pointers.py → KuroNoKen_pointer_dump.xlsx ────────────┘
```

`reinsert.py` is the main workhorse. It:
1. Extracts save files from the patched ROM (to preserve player progress)
2. Copies original files fresh into `patched/`
3. Applies translations block-by-block, updating pointers for size changes
4. Applies binary patches from `asm.py` (ASM fixes, alignment tweaks)
5. Repacks FA1 archives via `fa1.repack()`

### Key Modules

- **`rominfo.py`** — Single source of truth for all ROM metadata (~91KB). Contains the `BODFile` class, master file list (`FILES`, 500+ entries), pointer constants, file block definitions, control codes, and path configuration. Almost every script imports from this.
- **`fa1.py`** — FA1 archive unpacker/repacker. The archive format uses XOR-inverted file tables, word-aligned offsets, and a compressed/uncompressed flag per entry.
- **`asm.py`** — Low-level binary patches (`BYTE_EDITS` dict). Keyed by filename, each entry is a list of `(offset, bytes)` tuples. Also contains cheat/debug code for testing.
- **`dump.py`** — Scans decompressed game files for Shift-JIS text and writes to Excel. Uses `FILE_BLOCKS` to constrain which byte ranges to scan.
- **`find_pointers.py`** — Uses regex patterns (via the `regex` library, not `re`) with overlapping matches to locate pointers. Different regex sets per file type (.BIN, .SCN, .BSD, .SMI).

### Compression Workaround

The game uses an undocumented LZSS/Huffman compression variant that has not been reverse-engineered for re-compression. The workaround:
1. Run the game in an emulator with debug tools
2. Dump RAM (`fetch_memory.py`) after the game decompresses files
3. Slice out individual files from the memory dump (`slice_memory.py`)
4. Store decompressed files in `original/decompressed/`
5. Reinsert as uncompressed — FA1 archives support an uncompressed flag

### Directory Layout

- `original/` — Read-only. Contains the original `.hdi` disk image and `decompressed/` extracted game files.
- `patched/` — Rebuilt from scratch on every `reinsert.py` run. Contains the translated ROM.
- `patched_backup/`, `backup/` — Manual snapshots.

## Conventions

### Bytes Literals for Paths

All file paths and names use Python bytes literals (`b'A.FA1'`, `b'original'`). This is intentional — game files may contain null bytes or non-UTF8 data. Path construction uses `b'%s/%s' % (dir, name)` byte formatting.

### External `romtools` Library

The project depends on a custom `romtools` package (not on PyPI) that provides:
- `romtools.disk.Disk`, `Gamefile`, `Block` — ROM disk image and file manipulation
- `romtools.dump.DumpExcel`, `PointerExcel`, `BorlandPointer` — Excel I/O for translation data

### Text Encoding

- **Shift-JIS (SJIS)** is the primary encoding.
- **Halfwidth kana** uses a game-specific `0x85` prefix encoding (not standard SJIS halfwidth).
- **Control codes** are defined in `rominfo.CONTROL_CODES` — e.g., `[SPLIT]`, `[New]`, `[BLANK]`.
- Typesetting wraps English text to 48 chars/line with 2-space indent. Character names in the `NAMES` dict are preserved verbatim.

### Pointer System

The game has an unusually complex pointer system spanning multiple formats:
- **`POINTER_CONSTANT`** — Per-file offset adjustment (memory-to-disk translation). Most are `0`, some are `-0x1800` or `-0x3d00`.
- **`POINTERS_TO_SKIP`** — Known pointers that crash the game if modified.
- **`POINTERS_TO_ADD`** — Manual pointer entries not discoverable by regex.
- **`LENGTH_SENSITIVE_BLOCKS`** — Blocks that must stay exactly the same size (padded with spaces or nulls).

### File Types

| Extension | Content |
|-----------|---------|
| `.SCN`    | Scene/dialogue scripts (main translation target) |
| `.BSD`    | Battle scripts |
| `.BIN`    | Binary code (BD.BIN is the main game executable) |
| `.SMI`    | Character/item databases |
| `.FA1`    | Archive containers |
| `.DAT`    | Save/flag data |
| `.MP1`/`.MPC` | Map data |

### Excel Spreadsheet Format

The dump spreadsheet (`KuroNoKen_dump.xlsx`) has sheets for `SCNs`, `BSDs`, and per-file tabs. Columns: Filename, Offset (hex), Japanese, JP_len, English, EN_len, Typeset, Comments.
