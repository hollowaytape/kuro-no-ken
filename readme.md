## Kuro no Ken (Blade of the Darkness)
* Tools and documentation for the Kuro no Ken fan translation project.

### Progress
* TBD

### Building
`python build.py` (or double-click `build.bat`) builds `patched/` from the workbook: every script with English in it is reinserted, pointer sheets are generated for the ones without a hand-made sheet, and the result is checked for stale pointers. See [docs/translator_setup.md](docs/translator_setup.md) for setup on a fresh Windows machine, and [docs/testing.md](docs/testing.md) for the deeper checks.

`python tools/npcs.py` reads the maps' object tables into docs/npcs.json - which sprite speaks each conversation, and where it stands (`--names` writes the sprite list to name).

`python tools/sprite_shots.py --state r01_after_opening --area 02OLB --npcs` photographs an area's NPC sprites out of the running game (docs/sprite_img) and the spots they stand on (docs/npc_img), for docs/sprites.html.

`python tools/translator_context.py` rewrites the workbook's context columns in place (`--out` writes a copy instead): area, scene (shaded in bands, ruled where a text box or a scene begins), who is speaking and to whom, what has to have happened first, and the story order. Add `--basis docs/story_order_basis.txt` for how each script was placed - that is debug detail and deliberately not a column. Within a visit, where the scripts force nothing, `tools/play_order.json` says the order a player is likely to meet scenes in. `python tools/check_story_order.py KuroNoKen_dump.xlsx` then checks the one rule the order must keep - no conversation above anything it causally depends on - and reports what the recorded playthrough disagrees with; it must say 0 violations.

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