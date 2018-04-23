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


# Compression
RAM ~0x268b0
\common.bca[00]d\shinobu.bca[00]d\shinobu.smi[00]d\kies.smi[00]d\item.smi[00]d\unity.sml[00]99cmn.scn

System disk ~0xb07c0
\common[FE FA].bca[00][0C]shinobu[4e][61][06]smi[21][7f][06]kies[05][84][3c]item[05][cb][d4]un[0c]y[05]99[3f][d7]cm[47][73]

[fafe] = 1111 1010 1111 1110
         1111 1  010                                            1111111  0
         .bca 0 [0c] (copies 2 bytes from d bytes ago)          shinobu  END

[0c] is a pointer that reads 2 bytes. Look back (0c+1) bytes in the buffer, and copy 2 of them.
	The 2 bytes thing comes from the flag. 010 = 2...?

[614e] = 0110 0001 0100 1110
         011000010100 111 0
         [06]         smi END

[06] looks 14 back, copies 15 bytes.

[7f21] = 0111 1111 0010 0001
         011
         [06] (copies 3 bytes from E bytes ago)


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


0bcb:
add bp, bp
jnb 0bed

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
sub si, ax        ; Go back ax (0d) amount
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