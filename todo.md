## Reinserter
* Crash when changing length of first Shinobu/Innes conversation, still.
	* This file has a bunch of code at the end responsible for scrolling the images. 
	* 0x653	0x673
	* 0x676	0x87b
	* I wonder if this would go better after the pointer code improvements?

* A handful of odd pointer issues in the menus. Save is "e", "        Silk Scarf" (with no description), etc
	* Item names are fixed. Should investigate system text next

## Archives
* Some .BSD files are duplicated across multiple archives. Need to make sure those are being handled
	* Example: F023_L12.BSD (the one with the pug wizard thing I love)

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

## .BSD files
* Battle scenario files.
* A handful of them have the "I can't run" string (げられない) which will need to be translated.
	* C020_X10.BSD
	* C021_X10.BSD
	* C022_S10.BSD
	* C022_S20.BSD
	* C022_T10.BSD
	* C051_X10.BSD
	* D010_X10.BSD
	* D011_S20.BSD
	* D011_T20.BSD
	* D011_U20.BSD
	* D011_X10.BSD
	* D050_S10.BSD
	* D050_T01.BSD
	* D050_T02.BSD
	* D052_S10.BSD
	* D061_X10.BSD
	* D080_T10.BSD
	* D090_X32.BSD
	* D100_ZA3.BSD
	* D100_ZA7.BSD
	* D110_S10.BSD
	* DL20_T12.BSD
	* DL21_O10.BSD
	* DL21_Q10.BSD
	* DL21_R10.BSD
	* DL21_S12.BSD
	* DL30_X10.BSD
* These files are compressed, so they should get extracted.
* They also have attack names in them maybe?

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
