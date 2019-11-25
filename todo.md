## Reinserter
* Crash when changing length of first Shinobu/Innes conversation, still.
	* This file has a bunch of code at the end responsible for scrolling the images. 
	* 0x653	0x673
	* 0x676	0x87b
	* I wonder if this would go better after the pointer code improvements?

* A handful of odd pointer issues in the menus. Save is "e", "        Silk Scarf" (with no description), etc
	* Item names are fixed. Should investigate system text next
## Dump
* Need to re-dump a bunch of files, they were extracted from the wrong location
	* Really difficult to dump 02OLB01.SCN - wonder what is in there, or what's going wrong
* What are the control codes?
	* \i0
	* \i2
	* \f
	* ;@
	* [22 5c 66 00 3b] (\f[00];[3b]) = [WAIT] at the end of a 
* The auto-FILE_BLOCKS filling code should just set a single block for all .SCN files, consisting of the entire file.
	* Otherwise pointers get skipped.

## Text Formatting
* The newline character indents each character by 2. Solution would be to put an extra " " in front of every initial quote character, and maybe every nametag.
* No attempt at typesetting yet, what are the length limits?

## Images
* What file is the logo image?
	* Something that gets loaded between 27252 and 27264...
		* 43 00 01 00 46 00 01 00 01
			* 01 01 01 01: Nothing renders, but no crash
			* 01 00 01 00: Crash
			* 00 02 00 02: Freeze
			* 00 00 00 01: Nothing renders, but no crash
			* 00 01 00 00: Crash
			* This is split into:
				* 43
				* 00
				* 01 00
				* 46 00
				* 01 00
				* 01 00
