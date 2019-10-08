## Reinserter
* A handful of odd pointer issues in the menus. Save is "e", "        Silk Scarf" (with no description), etc
	* Item names are fixed. Should investigate system text next
## Dump
* What are the control codes?
	* \i0
	* \i2
	* \f
	* ;@
	* [22 5c 66 00 3b] (\f[00];[3b]) = [WAIT] at the end of a 

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
