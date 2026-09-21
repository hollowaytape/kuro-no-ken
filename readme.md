## Kuro no Ken (Blade of the Darkness)
* Tools and documentation for the Kuro no Ken fan translation project.

### Progress
* TBD

### Building
`python build.py` (or double-click `build.bat`) builds `patched/` from the workbook: every script with English in it is reinserted, pointer sheets are generated for the ones without a hand-made sheet, and the result is checked for stale pointers. See [docs/translator_setup.md](docs/translator_setup.md) for setup on a fresh Windows machine, and [docs/testing.md](docs/testing.md) for the deeper checks.

`python tools/translator_context.py --out KuroNoKen_dump_context.xlsx` adds per-line context (area, scene, speaker, what gates the line) to a copy of the workbook.

### Usage (original workflow)
Place your dump of `Kuro no Ken (Blade of Darkness).hdi` in the subfolder `original`. Then run these scripts to dump the text and pointers:

```python dump.py
python find_pointers.py```

This will dump the text into `KuroNoKen_dump.xlsx`. When you're done translating, run the reinserter:

```python reinsert.py```

The copy of `Kuro no Ken (Blade of Darkness).hdi` in the subfolder `patched` will be translated according to your translation dump.

### Overview
* Game files are all packed into several `.FA1` archives. See `fa1.py` for documentation and an unpacker/repacker.
* Images (`.AS2`, and probably the other art types) use a *second* compression inside the FA1 one: an LZ77 bitstream with a per-file Huffman tree. `as2.py` decodes and re-encodes it; see `docs/as2_format_findings.md`.
* Most meaningful game files are all compressed. The compression technique has not been documented, but it looks horribly complicated - it's an LZSS variant that uses an extremely large Huffman tree to determine what mathematical operations to perform on the window. 
	* As a result, all the files that need changes have been manifested in memory in their decompressed form and then sliced out. (See `fetch_memory.py` and `slice_memory.py` for these tools).
	* No attempt has been made to re-compress the files after editing. FA1 archives have a flag that lets you repack uncompressed files, so we just use that.
* This game has the messiest pointer system I've ever seen - pointers exist in tables, hard-coded into the code
* Yes, there's a PSX version of this game. It features voice acting and some graphical updates. A few reasons I think this version is better:
	* The graphical updates are very uneven, so you have improved sprites over the same backgrounds and it looks really incoherent.
	* Battles are twice as slow for some reason.
	* Voice acting makes all the dialogue take way longer, since it doesn't display instantly. That takes away from the zippiness of the game that I find really appealing.

### License
This project is licensed under the Creative Commons A-NC License - see the [LICENSE.md](LICENSE.md) file for details...