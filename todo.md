## Reinserter
* A handful of odd pointer issues in the menus. Save is "e", "        Silk Scarf" (with no description), etc

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
		* 40 02 5c 66 20 5c 66 00 3e 43 00 01 00 46 00 01 00 01
			* Changing the last few to 01 01 01 01 makes nothing render.