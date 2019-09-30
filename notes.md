kuoushi:
   Could be, yeah. The FA1 files appear to be a bunch of different files packed into a larger file in general
   The structure appears to be some stuff in the first x1000 bytes, then the file system starts at around x7d8c, then there's what looks like a table at the end of the FA1 itself
   It's a ridiculously held together set of files
   Like, there's no space buffer between each of them, it's all just read in the table I think
   One file ends, another immediately starts in the next byte
   If you open them in madedit and search for .bca (one of the file types) you'll see the name of the file and then the content, and before that filename there's no space, just more other file
   It is probably compressed (LZSS is an okay guess) as well, which makes it look even weirder
   BCA files appear to be the script though
   Very messy in there
   Disassembling BOD.COM and seeing what it's doing might be one way to tackle that. It's a tiny file for the most part


Compression
RAM ~0x268b0
\common.bca[00]d\shinobu.bca[00]d\shinobu.smi[00]d\kies.smi[00]d\item.smi[00]d\unity.sml[00]99cmn.scn
System disk ~0xb07c0
\common[FE FA].bca[00][0C]shinobu[4e][61][06]smi[21][7f][06]kies[05][84][3c]item[05][cb][d4]un[0c]y[05]99[3f][d7]cm[47][73]

[fafe] = 1111 1010 1111 1110
         1111 1  010                                           1111111  0
         .bca 0 [0c](copies 2 bytes from d bytes ago)          shinobu  END

[0c] is a pointer that reads 2 bytes. Look back (0c+1) bytes in the buffer, and copy 2 of them.
	The 2 bytes thing comes from the flag. 010 = 2...?

[614e] = 0110 0001 0100 1110
         011000010100 111 0
         [06]         smi END

         [06] looks 14 back, copies 15 bytes.

[7f21] = 0111 1111 0010 0001
         011
         [06] (copies 3 bytes from E bytes ago)


[5fff] = 0101 1111 1111 1111


It's checking multiple bits in the flag to determine what to do with a pointer... There's a branch for every bit.
	Some kind of Huffman coding tree here?
	This seems like something to tackle with IDA. So many jumps...

0 - End
010 - Look (x+1) bytes back, copy 2
011000010100 - Look (2(x+1)) bytes back, copy (2(x+1))+1


That [4e][61][06] probably codes for "Look ~13 back, copy 14 bytes (.bca[00]d\shinobu.)
[21][7f][06] = .smi[00]d\ = "Look 11 back, copy 7 bytes"
1111111 ? 11111 ? 11111110
Pretty weird, stuff tends to get interrupted with 2-byte things then resume normally. Maybe the flags are 2 bytes this time?
There's another section where [FF][FF]09 9f 09 ae 09 d\kies.bca[00] appears. FF FF = 16 1's, so 16 raw bytes
[FF][5F] = 1111 1111 0101 1111
[0a]bd_flagh.dat[00]
I dunno!!
Maybe flip it around? 0101 1111 1111 1111 1111
stosb = store AL at address ES:DI. Store 6b at 16d8:9dd.
AL comes from mov al, [bx]. [bx] is the contents of DS:BX, which appears to be the compressed disk segment. Cool!

mov dl, 10
mov bp, [bx]    <- loads a two-byte flag? bp is now 5fff
add bx, +02
cmp bx, 2000
jb 0bcb
call 0f2e
jmp 0bcb
;
;
0bcb:
add bp, bp
jnb 0bed
;
0bed:
dec dx
jz 0d8e
add bp, bp   -> bffe + bffe = 7ffc      
jnb 0c6a             ; jnb = jnc, so jump if  it didn't carry.
mov ah, 00
dec dx

bx is a cursor for the compressed source file.
di is a cursor for the uncompressed destination file.


Loading the "FE FA" flag:
mov bp, [bx]     ; BP: fafe
add bx, +02      
cmp bx, 2000
jb 0bcb

0bcb:
add bp, bp
jnb 0bed

add bp, bp is a way of checking all the bits of a flag. FF FF will overflow/not jump every time, since the leftmost bit is always 1.

0bed:    ; The thing that gets jumped to when it encounters a 0 bit in the flag
dec dx
jz 0b8e
add bp, bp
jnb 0c6a
mov ah, 00
dec dx
jz 0ba0
add bp, bp
mov al, [bx]      ; the 0c part of the pointer(?)
inc bx
jb 0c11
cmp bx, 2000
jz 0bbc
inc ax            ; now it's 0d
mov si, di        ; Here we go, it's about to look at the previously written stuff
sub si, ax        ; Go back ax (0d) amount  ("copy 2 bytes from d bytes ago")
movsb es:
movsb es:
jmp 0bc8

0bc8:
dx:

0c6a:
dec dx
jz 0cc2

# File Structure
A.FA1 appears at 0xab40 in RAM decompressed. It starts with a big list of filenames and and offset twice.
FAD.BIN - d3 0f
BD_FLAG0.DAT - aa 0d
BD_FLAG1.DAT - aa 0d
BD_FLAG2.DAT - aa 0d
...BD_FLAG7.DAT - aa 0d
BD_FLAGH.DAT - 5b 00
...
_MG_SR.BCA - 01 20 06   f3 0f
...
SHINOBU.BCA - 01 81 7c   d4 e7
I guess that is probably not just an offset...

# BOD.COM
* File is loaded at 0x79f0. And at least the beginning of it at 0x5328 too. (That might just be a dos thing)
* オープニングから is loaded at 0x216f1. Appears to be a list, each entry having e1 preprended to them
   * (This word is mostly also in A.FA1 at 0xb3758.)
   * [FF FE]オープニングから 82 f2 bf 17 96 60...

* Disassembly
193h is the dx location where the "Memory insufficient" string is claimed to be. It's at 0x93
What string is at 1c7?
   * One of those "1b[>5h1b[>1h1b*$*" type strings.



* When it reads the a.fa1 filename:
   * Checks if the second char in the string is ':' (to see if it's a drive letter or not)
   * Checks if it's a "/" or below (punctuation chars)
   * Checks if it's a "\", then returns and switches the two bytes and runs this again (to check the second byte)
   * "." is indeed below "/", so do something special to it



* More debugging
lodsb: load byte at DS:SI into AL. 16d8:a971 loads 83, it's not 0
(Oh wait, that's just the text display routine. Let's set a breakpoint for the compressed data instead)


It's at 0xa9c6

bx value when it reads fe ff: 1e86.
   The location in the comp'd file is 0xb3756. (b18d0 is where bx would be 0)

Reading the flag:
mov bp, [bx]
add bx, +02   ; Increment the compressed-data cursor to start reading real data
cmp bx, 2000  ; Something about the compressed data being split into 2000-chunks
jb 0bcb
->
add bp, bp    ; fffe -> fffc
jnb 0bed (not taken)
mov al, [bx]
inc bx
cmp bx, 2000
jz 0bb7 (not taken)
stosb
jmp 0bc8
->
"Load and store literals"
07bf:0bc8 dec dx
jz 0b7c (not taken)
add bp, bp    ; fffc -> fff8
jnb 0bed (not taken)
mov al, [bx]  ; 49 (second byte of text)
cmp bx, 2000
jz 0bb7 (not taken)
stosb
jmp 0bc8 ("Load and store literals")

Loops the "load and store literals" until either:
   1. EDX == 0 (after 16 bytes are written?)
   2. Leftmost bit of BP (the flag) is 0
   3. BX == 2000 (get next chunk?)

0bed "Just hit a 0 in the flag":
dec dx  ; 1 -> 0
jz 0b8e
->
mov dl, 10
mov bp, [bx]
add bx, +02
cmp bx, 2000
jb 0bf0
call 0f2e
jmp 0bf0

...Where does the decompression code come from? Is it in BOD.COM?


# Disk Structure
* System Disk.hdm
A.FA1 is at 0x2c00, estends until 0x108ddf
Weird stuff from 0x108de0 onwards
System text starting around 0x109a50
* Probably not useful, since this will have a lot of DOS stuff in it


# A.FA1 again
* "FilenameExta:" (RAM 0x7c40) is a field where the filename and ext get filled in.
   * They are filled in a LODSB, etc, STOSB loop.
      lodsb: load  DS:SI into AL
      stosb: store AL in ES:DI
      * Loading from 078f:191 into 07bf:5d
         * Hey, that's the BOD.COM segment
      *  Next string: 16d8:9eb "bd_flagh.dat", floating in the middle with some other files
      * Another: 16d8:fbb1 "d\gaiji.bin"
   * The actual file it gets loaded from is named at 7ca3. (A.FA1, B.FA1, etc)
   * Anything interesting about 0x7c09-onward?
      * 02OLB00ASCN, in its table, has values 01 e0 04 00 00 9f 08 00 00 after it.
      * DS01A.AS2 has                         00 de 61 00 00 de 61 00 00 
         * the de 61's go in slots 7c0c and 7c10.

* Dialogue
* なにこれ！？
* File seems to begin at 2aa80 in RAM
   * A mention of d\ds_01a, d\ds_01b, etc before the dialogue begins
   * Loading stuff into 2aa80: seems to be following the decomp routine. 
      * It's getting decomped from 0x8b40. The matching string is in B.FA1, at 0xfb0fe
         * The file is 02OLB01A.SCN
         * And yes, the file is marked as coming from B.FA1
         * Any interesting bytes in that header thing?
            * 3d d8 26 83 10 00 00 44 09 00 00 00 00 00 00 fe b0 0f 00 b4 08 00 00 01 03 00 00...
               * Right there, "fe b0 0f" = fb0fe offset in B.FA1.
                  * bx gets moved into the first 2 bytes [0028], then dx gets moved into the next ones [002a]

         * Its entry in the table:
            * 01 44 09 00 00 83 10 00 00 6c 0e 00 00
               * Well, the 44 09 is there at least.
         * Wild guess: the first byte is which file. 00 = A.FA1, 01 = B.FA1, etc
            * Incorrect

* Decomping from 8b40 -> 2aa80

* How can we go from a table entry's value to the location of that compressed file in the FA1 archive?

O20LB01.SCN offset: 0f a5 84
   * Initial EAX: ed (number of entires in table)
   * Initial EBX: c  (that's where the first table entry is)
   * Initial EDX: 0
O20LB01A.SCN offset:0f b0 fe
   * Both of those files "end" with a FF byte... that's not much of a hint to the file structure

02OLB01A.SCN 01 44 09 00 00 83 10 00 00
                            ^[001c-d]

And yes, it's loading from the table itself.
[0028-a]: 84 a5 0f 00
Need to figure out how bx and dx get calculated.
add bx, [si+0c]  ; 94c2 + 011f = 95e1   ; +0c is the word (bytes 2-3) of the data section
adc dx, [si+0e]  ; 0b + 0 = 0           ; +0e is the word (bytes 4-5) of the data section
   DX gets incremented whenever BX has overflowed in the previous instruction. (when is there )

It does this process a LOT. Adds c/e values to bx/dx, increments di by 0x14 (looks at a new entry in the table), decrements ax, checks if ax is zero yet.
   So! the initial value of EAX probably comes from part of the table header, at 0xab48
      FA1[00][78 48 10 00][18 01]
                           ^ Number of entries in the table
             [d8 ea 10 00][ed 00][01 80]
ac, c0, d4, e8, fc... adding 0x14 each time
   It's not just until it gets to 0. The 02OLB01A quits when EAX == 51.
      02OLB01A happens to be the ed - 51 = 9cth entry in the table.


02OLB01B.SCN 01 86 08 00 00 6c 0e 00 00


118 file = A.FA1?

So, the first thing on the breakpoint is that it is looking for the 02OLB01.SCN file in the 118 file. It looks at every entry in the table (until EAX == 0), and the final EDX-EBX value is 0x104878.
   * 104878 is the end of the A.FA1 file's data - as in, right before a big blank spot and a large pattern-like thing at the end.
   * So, it's looking for 02OLB01 and it's not found in this file. Then it loads B.FA1 and looks for it there
   * Another part of this process:
      push si
      mov di, 53
      mov cx, b
      repe cmpsb
      pop si
      jz 0afe   ; (clc, ret), which leaves successfully
      * This checks to see if the filename being searched for is the one in the table, probably

The table still has 0x118 entries in it when switching over to 0xed. It probably just doesn't overwrite the leftovers, since it won't be searching them anyway

The file table appears to just be a not'd version of the big pattern table at the end of the FA1. Binary one's complement

## FA1 header
00-02: "FA1"
03: 00
04-06: Offset of the end of the compressed data
07: 00
08-09: Number of entries in the file table
0a-0b: 00 80?

# BOD.COM again
* After loading files, it jumps to 0x7bf:0f50. This is 0f50 in A.FA1 (FAD.BIN).


# Important segments
* 2aa8: First dialogue (02OLB00A.SCN)
* 216f: Options menu
   * 16d8: BD.BIN
* 07c4: Filename of file getting loaded
* 08b4: Where the compressed file is loaded

* BD.BIN - the file with the options in it. It is very big (0xfd70 long).
   * Begins at 16d80? So, ranges from 16d80-26af0
   * This might be a good file to look at decompression for - it starts with a bunch of FF FF flags, and it is probably the first file decompressed... maybe?
   * Crashes on the Status screen when the decompressed file is reinserted with no changes.
      * Let's see if I can re-dump it when it's fresh as possible.
      * Yep, it works now. Gotta be careful with that

# Pointers
* Pointer to 0xbb44 ("   シノブ・リュード") is 0xbb44
   * 00 74 03 be 44 bb 83 06 92 a5 14
   *          be 2d bb 80
   *          be 8f bb
   * Yep, it's just the offset with a prefix of 'be'. Pointer constant is 0. (The file is less than 0xffff)

# .SCN
* Can't alter the length or the gam crashes?
   * Can't even expand it with 00s. Haven't ruled out a flaw in the filesystem reinserter though.
      * Fixed it, now I can expand it with 00s. Still probably shouldn't interfere with the code blocks though.
      * It doesn't seem to like where I ended the blocks. Maybe space them with 20's instead?
51 00 9c 34
   51 01: Fades from weird lighter palette instead of black
52 00 01 00
53 49 03 4c 03
62 43 03 46 03
61 00 03 00 01

The 02 before \i0Shinobu:
   00: Loads image, then crashes
   01: " "
   03: Writes the first Ennis line instead
   ff: " "

The 40 before that:
   41: Upper window instead of lower, very glitchy
00 53 04 before that:
   51: Fucked up palette, whole image instead of bars
   52: Loads the whole image instead of the black bars
   50: " "

00 52 00 before that:
   third is 01: Instant load instead of fade in

3b 01 ee 44 4f 01 ac 44: control code to scroll the image to the left

* Series of offsets(?) at the beginning of 020LB01A.SCN:
09 54 3d
09 9e 3d
09 14 3e
09 44 3e
09 68 3e
09 bf 3f
09 e7 3f
09 15 40
09 4b 40 <- this is the "where's my sword?" Ennis dialogue thing
09 21 43
09 aa 43
09 ce 43
09 3c 44
09 90 44
09 f4 44
09 56 45
09 94 45
09 c9 45
09 09 46
09 61 46
09 a5 46
09 31 47
09 60 48
09 26 49
09 58 49
09 91 4c
09 df 4c
09 2f 4d

04 30 40
02 5c 69

Text is between 5c-1080

When talking to Ennis and starting the dialog at 35c, the first breakpoint hit is 358 (0c 30 40 02).
   * lodsb es: (ES:SI (26d8:404b)
      * 404b is one of the values in that table. 404b - 358 = 3cf3. (some constant?)
      * Is there always a consistent number of bytes between the first control code and the first thing of dialgoue?
         * 404b points to 358, or 4 before 35c
         * 4321 points to 62e, or 4 before 632
      * Let's try another file - 02OLB01B.
         * "gurururu" is at 0x1a0ish
         * Breakpoint triggers at 0x19a (8 before the dialogue in the dump)
            * ES:SI: 26d8:3e44
         * Oops, This is a different "woof". And it's in the same file (01A).
         * Breakpoint is at 0x144, text begins at 0x14c (diff is 8)
         * Pointer constant would be: 3e44 - 144 = 3d00
            * Why are these different?? Let's check the other one again
            * Actually 404b points to 34b, which is a full 17 before the text begins.
            * 404b - 34b = 3d00
               * That's better.
      * Northern gate (「北の門を出ると湿原に行けるんだが、) text:
         * 432a points to  0x62a, or 8 before text at 0x632
         * PC would be: 432a - 62a = 3d00

* Why is there a crash when reading Ennis's final line of dialogue?
   * In original, it ends with 5c 66 00 09 27 43 b4 00 23 34 04 0c 30 0c 64 00 a9 42 1d 64 00
   * In patched, it ends with: 5c 66 00 09 27 43 b4 00 23 34 04 0c 30 0c 64 00 a9 42 1d 64 00
   * No difference.
   * There are also no pointers that would point in that range...
   * Maybe it's an even-odd thing?
      * Not length of the string - I can make the previous one shorter and this one longer. So something to do with the ending position?
      * The last thing read from the last good string: 00 09 27
      * THe first thing read from the next string, which crashes: 43 b4 00
      * It reads 27 43 as a word. Let's see what it does with it
         * Reads 4327, puts SI into AX, then returns. (SI is equal to AX)

         * Is 27 43 a meaningful pointer to somewhere? 4327 - 3d00 = 627. That is slightly before "the north gate" thing
            * Maybe it's some kind of variable-setting code?
            * What is 3015? 3015 - 3d00 = ... no
            * What is the pointer to read the "b4" location (4c3)? 4c3 + 3d00 = 41c3
               * "01 c3 41 1d" right before this dialogue begins.
               * So, 09 pointers and 01 pointers both need to be looked for in the text blocks.


KIES.SMI = 32940-3377a

# Good dumping strategy
* Open save state #8, replace 03YSK with the desired filename, and dump from 0x26d00 with slice_memory.py.


## Cheat Saves
* Stats in 2nd file:
   * HP: 93 / 192
   * MP: 225 / 225
   * 42 gold
   * Level: 1
   * EXP: 39
   * Next: 50
   * Attack: 27 + 40
   * Defense: 20 + 12
   * MA: 24 + 24
   * MD: 20 + 1
   * Acc: 15
   * Eva: 50 + 2
   * Speed: 5
   * Jutsu: Bird's Blade