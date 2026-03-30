## Reinserter
* Crash when changing length of first Shinobu/Innes conversation, still.
	* This file has a bunch of code at the end responsible for scrolling the images. 
	* 0x653	0x673
	* 0x676	0x87b
	* I wonder if this would go better after the pointer code improvements?

## Archives
* Some .BSD files are duplicated across multiple archives. Need to make sure those are being handled
	* Example: F023_L12.BSD (the one with the pug wizard thing I love)

## Dump
* The latest (2/17/20) dump has spaces that properly indent the strings... should I be putting those into my dump?
	* That would explain the kind of bad approximation that my current typesetting code is making
* What are the control codes?
	* \i0
	* \i2
	* \f
	* ;@
	* [22 5c 66 00 3b] (\f[00];[3b]) = [WAIT] at the end of a 
* The auto-FILE_BLOCKS filling code should just set a single block for all .SCN files, consisting of the entire file.
	* Otherwise pointers get skipped.

## .BSD files
* Haven't tried pointer edits or reinsertion with these yet.

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
