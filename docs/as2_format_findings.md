# The AS2 image format and its compression

`as2.py` is a working decoder and encoder. Both directions are verified
byte-exact against the game's own decompressor running under `romtools/np2core`.

Method: the one in `../CLAUDE.md` — hook the load, follow the code, read the
game's parser. No byte-layout guessing. `docs/title_logo_findings.md` covers
what the title card does with these images.

## Container

```
0x00  "AS2\0"
0x04  uint32  file size (matches exactly, all 96 AS2 files)
0x08  uint32  ?              0x5000 for full-screen scenes
0x0C  uint16  row stride in bytes: 0x190 = 400 for 640x400
0x0E  uint16  ?              0x180 or 0x80
0x10  24 bytes palette
0x28  bit-packed code table  (see "The per-file code table" below)
 ..   image bitstream, continuing in the same bit-stream as the table
```

The palette is two 4-bit components per byte, **high nibble first**, 16
entries of **(B, R, G)** — unpacked by `0x133fd` (`lodsb / ror ax,4 / stosb /
shr ax,0xc / stosb`, `cx = 0x18`) into `cs:0x8c`. Decoding DS_T1's palette this
way reproduces the measured title-card palette exactly, including the fire ramp
at entries 0–7 and the flat maroon at 8–15.

## Bitstream

MSB-first over **16-bit little-endian words**. `bp` holds the word, `add bp,bp`
shifts a bit into CF, `dl` counts down from 0x10, and a refill is
`mov dl,0x10 / mov bp,es:[bx] / add bx,2` which consumes the new word's top bit
immediately. Exactly 16 bits per word.

Three symbol kinds, selected by a prefix code:

| symbol | meaning |
|--------|---------|
| `LIT b` | emit byte `b` |
| `COPY o` | read a length, copy that many bytes from `o` back |
| `RLE` | read a length, repeat the previous byte |

The decoder tracks a **remaining count per row** (`ax`, initialised from
`[0xd40]` = the stride): a literal decrements it by 1, a copy by the length,
and the row ends when it reaches exactly 0. **Copies never cross a row
boundary** — the encoder must respect this.

Lengths use an Elias-gamma code: k leading zeros then a `1` (or seven zeros for
k=7), then k+1 bits, plus `2**(k+1) - 1`. Constants verified in the code:
1, 3, 7, 0xf, 0x1f, 0x3f, 0x7f, 0xff.

Back-references run against a **0x1900-byte ring buffer** (`cmp si,0x25c0 / jb
-> si += 0x1900`), so offsets reach at most 6400 bytes back. The copy is
`rep movsw` + `rep movsb`, which for any offset >= 2 behaves exactly like a
byte-wise copy; offset 1 is what `RLE` is for.

## Output layout: column-major, bit-interleaved

The decoder emits, per "block", 4 arrays of `stride` bytes at `+0, +0x190,
+0x320, +0x4b0`. The routine at `0x15089` then walks them together, and for
each step takes one byte from each of the four and writes one byte to each of
the four PC-98 VRAM planes at `di`, then does `di += 0x50` — **one scanline
down**. It loops to `di < 0x7d00`.

So a block is **one 8-pixel-wide, 400-pixel-tall screen column**, and 80 blocks
= 640 pixels. The column index lives in the immediate of `mov di,imm` at
`0x13d54`, which the loop self-modifies via `inc word ptr [0xfe4]`.

The byte→plane step is a **pure bit permutation** (verified against 2000 random
inputs): each source byte carries 2 bits for each of the 4 planes.
`as2.transpose` / `as2.untranspose` implement it and its inverse, and
`as2.planes_to_stream` / `as2.stream_to_planes` wrap them.

Verification: decoding DS_T1 and pushing it through `transpose` reproduces the
game's VRAM **byte-for-byte** for every column that had been drawn when the
capture was taken (the last two columns hadn't been written yet).

## The per-file code table

**The prefix code is different for every file.** The loader reads the table at
0x28 and *generates the unrolled decoder as x86 code* — the tree is literally
compiled into the instruction stream at `0x13d95`–`0x15100`, which is why the
same bit pattern means different things in different files.

This cost a detour worth recording: a tree extracted from a memory snapshot
decoded DS_T2 perfectly and produced pure garbage on DS_T1. Tracing both files
gave two self-consistent but completely different tables.

The generator's entry point is `0x1469a`. The table is **not** a separate
blob — it is the head of the same bitstream the image uses:

```
count-1      5 bits
action map   count x 5 bits     each entry an index into the FIXED action table
R            5 bits             total internal nodes; 0 => tree is a single leaf
tree         pre-order:
    node():  N = read5()        # internal nodes in the LEFT subtree
             left  = node() if N else leaf()
             M = read5()        # internal nodes in the RIGHT subtree
             right = node() if M else leaf()
    leaf():  sym = read5()      # index into the action map
literal sub-tree                # only if some leaf is the literal group
```

`N` and `M` are redundant with the subtree that follows; the generator uses
them to compute the forward branch displacement in one pass. Each internal node
costs 26 bytes of generated code and each leaf 7, so a left subtree with `N`
internal nodes has `N+1` leaves and occupies `33N + 7` bytes — hence the
emitted displacement `33N + 23`. That arithmetic is the tell that `N` is a
subtree **node count**, and it checks out exactly against the generated code.

Every file's tree has exactly **32 leaves**, one per symbol index 0..31.

### The 32 actions are fixed in the executable

`ds:0x0de8` holds 32 four-byte entries (signed offset, handler address) that are
the same for every file — only *which leaf gets which slot* is per-file:

| handler | meaning |
|---------|---------|
| `0x18c0` | copy, with the ring-wrap check (large offsets) |
| `0x18c6` | copy, no wrap check (offsets −2, −3, −4, −8, −16) |
| `0x18f0` | RLE |
| `0x1432` | literal group — expands into its own sub-tree |

The offsets are −2, −3, −4, −8, −16 and clusters around −400, −800, −1200,
−1600, −3200 (±1..4) — i.e. the pixel above, a few pixels up, and the same
positions one to four planes/columns back. 30 copies + RLE + literal = 32.

`as2table.py` implements this. Verified against DS_T1: all **31 non-literal
codes match the traced tree exactly**, the literal-group code `100` is the
common prefix of all 7 traced literal codes, and re-emitting the parsed table
reproduces the original **640 bits bit-for-bit**.

### Writing tables

`as2table.py` also emits tables: `huffman(freqs)` builds a 32-leaf tree over the
fixed actions, `emit_table(action_path)` serialises it, `pack(bits)` packs it.
Symbol indices are assigned in pre-order and the action map follows, so a
re-emitted table is not bit-identical to the original (the original numbers its
symbols differently) but **resolves to the same code**. Verified:

- re-emitting DS_T1's parsed tree reproduces the original 640 bits exactly when
  its own symbol numbering is kept;
- a re-emitted table with pre-order numbering resolves to an identical
  path→action map;
- a Huffman-reshaped table parses back to the intended actions, e.g. giving
  offset −2 a **1-bit** code where it originally had 4.

### The literal sub-tree

Same recursive grammar as the main tree, continuing in the same bitstream, but
with **4-bit** values:

```
R      = read4()          # total internal nodes; 0 => a single leaf
node():  N = read4(); left  = node() if N else leaf()
         M = read4(); right = node() if M else leaf()
leaf():  V = read4()
```

The twist is what a leaf means. It does not name a byte — it names a
**contribution**, and the decoder runs the tree **twice**:

* the first pass emits `mov al, imm` and contributes `mov(V)`;
* the second emits `or al, imm` and contributes `or(V)`.

`contrib(V)` (from `0x1495f`–`0x14986`) spreads V's four bits into the **even**
bit positions for the `or` form and the **odd** positions for the `mov` form,
with `V = 0` contributing nothing and `V = 1` special-cased to `inc ax` / `2`:

| V | or | mov | | V | or | mov |
|---|------|------|---|---|------|------|
| 0 | 0x00 | 0x00 | | 8 | 0x40 | 0x80 |
| 1 | 0x01 | 0x02 | | 10 | 0x44 | 0x88 |
| 2 | 0x04 | 0x08 | | 12 | 0x50 | 0xa0 |
| 4 | 0x10 | 0x20 | | 15 | 0x55 | 0xaa |

So a literal's code is `<litgroup><code of V1><code of V2>` and its byte is
`mov(V1) | or(V2)`. **A literal tree with L leaves spells exactly L² bytes** —
which is why DS_T1 (leaves `{'0':0, '10':8, '11':2}`) has 9 literals and DS_T2
(9 leaves) has 81. That L² relation was the tell.

Any byte is reachable: split it into its odd bits (→ V1) and even bits (→ V2),
which `as2table.v_for_byte` does. With all 16 V values the alphabet is all 256
bytes.

Verified:

* DS_T1's literal section parses to 3 leaves in exactly its 32 bits, the
  derived 9 codes match **all 7** traced literals, and it predicts the two
  branches the trace never exercised (`0x04`, `0x08`);
* DS_T2's parses to 9 leaves and its derived 81 codes match **all 81** literals
  recovered independently by walking the generated decoder;
* in both files the bitstream position after the literal tree lands exactly
  where the image bitstream begins;
* `emit_literals` reproduces DS_T1's 32 bits bit-for-bit.

## Verified results

| check | result |
|-------|--------|
| DS_T2.AS2 decode (128000 bytes) | byte-identical; bitstream ends exactly at EOF |
| DS_T1.AS2 decode (128000 bytes) | byte-identical; bitstream ends exactly at EOF |
| VRAM transpose | byte-identical for all drawn columns |
| palette | reproduces the measured title palette |
| encoder round-trip on DS_T1 | identical, and **3404 bytes vs the original 3738** |

## What the two title files are

- **DS_T1.AS2** — the title card backdrop. Its **I plane is the calligraphy
  stencil** (inverse: 1 = hide), matching the mask read out of VRAM to 99.98%.
  Its low planes hold only the dithered ground glow along the bottom (palette
  index 2, ~340 rows down).
- **DS_T2.AS2** — the flame artwork: three 192-pixel-wide flame columns plus a
  narrow ember strip, which the engine copies into the 192x376 sprite texture.

So **the English subtitle is an edit to DS_T1's I plane**, and nothing else has
to change to get the letterforms on screen.

## Shipped: the English subtitle, in-game

`make_title_disk.py` runs the whole chain and `patched/test_title.hdi` boots
with it. `img/title/title_subtitle_fire.png` (and `.gif`) is the real thing
under emulation.

    artwork -> as2_author (both trees + bitstream) -> DS_T1.AS2 -> A.FA1 -> .hdi

The file is **authored, not patched**: `as2_author` fits a new main tree *and*
a new literal alphabet to the artwork, so the letters carry the game's own
flame texture across the full fire ramp rather than a flat fill.

| step | result |
|------|--------|
| artwork | 31 distinct bytes -> a 7-leaf literal tree (alphabet of 49) |
| bitstream | 5756 bytes after two fitting passes (6818 on the first) |
| DS_T1.AS2 | 3862 -> 5886 |
| authored file re-parsed with the ordinary reader | decodes to the artwork exactly |
| A.FA1 | 1073632 -> 1075680 |
| archive read back off the disk | byte-identical |
| I plane in the running game vs intent | **99.78%** (the rest is drifting embers) |

### Two things about the archive

`A.FA1` pads its entry table to a 0x400 boundary, leaving **904 bytes** a member
can grow into before the archive's size changes at all. The flat-fill version of
this subtitle fit in that; the fire version does not, so the archive grows —
which is fine, because NDC writes it through the filesystem.

A byte-patch straight into the `.hdi` would *not* be fine: **A.FA1 is stored
non-contiguously**, so replacing its bytes in place silently corrupts it.
`fa1_patch.patch_disk` refuses when it detects that; `make_title_disk.py` uses
NDC (`D` then `P` into `B-DRKNS`) and then reads the archive back and compares.

`ndcpy`'s wrapper rejects the bundled `NDC.EXE` ("Unsupported version: NDC
Ver.0 alpha06b" vs the whitelisted `alpha06`), so the binary is invoked
directly rather than patching shared code.

Growing DS_T1 shifts every later member's offset, and the game took it without
complaint — the FA1 entry table really is authoritative, which the opening
confirms by loading DS_T2 (the very next member) correctly afterwards.

### Animating the subtitle

The first version baked the fire into DS_T1, so the English only got the palette
pulse (~9% of its pixels changed) while the kanji flickered (~82%). It is now
drawn by the kanji's own sprite routine: `ipl_sprites.py` adds three entries to
00IPL.SCN through a code cave, and DS_T1 carries only the stencil holes. From
the recorded GIF: **letters 86% changing, kanji 85%**.

A useful side effect: with the fire no longer baked in, DS_T1 grows only 704
bytes, so A.FA1 goes back to its original size (the 904-byte table pad absorbs it).

**For the translated build:** the opening's code lives *inside* 00IPL.SCN,
which is also the file whose narration gets translated. `patch_ipl` expects
the untranslated layout and refuses otherwise. If the translated SCN shifts
that code (text changing length would do it), both this patch and the
original opening's own absolute references (`[0xc32]`, `[0xf34]`, the table at
`0x0ee5`, …) move with it — plausibly the cause of the patched build's hung
opening.

## A bug worth remembering

Several size measurements in an earlier pass were inflated because an ad-hoc
encode loop wrote a length code after **literals** as well as after copies.
`as2.encode` has always done this correctly; the hand-rolled loops did not.
The symptom was a decode that failed almost immediately ("bad code at 32")
while the sizes merely looked disappointing — the two are the same bug. Always
round-trip an encoded stream through `as2.decode` before trusting its size.
