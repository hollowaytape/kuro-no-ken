# The flaming 黒の剣 title logo

How the opening's title card is built, and how to put English text into it.

Everything below was established by running the game under `romtools/np2core`
(headless, in-process) and reading VRAM, registers and DOS calls directly —
`title_logo.py` reproduces all of it.

## Short answer

Yes: it is a **transparency stencil over a flaming background**, done with a
palette trick rather than with any per-pixel blending.

```
plane I   (0xE0000)  = the calligraphy stencil, INVERTED (1 = hide)
planes B/R/G         = a 3-bit fire image, blitted from a static texture
palette 8..15        = all (68,0,0), the background maroon
palette 0..7         = the fire ramp
```

Because every palette entry with bit 3 set is the same maroon, any pixel whose
I bit is 1 is invisible *whatever the fire underneath it says*. The fire is
blitted as three plain rectangles — no masking in the blit at all — and only
shows where the stencil has holes.

## The layers

`img/title/layer_fire.png` and `img/title/layer_mask.png` are the two layers
pulled apart. The fire layer is three flat rectangles plus a full-width band
along the bottom; the stencil layer is the clean calligraphy.

### Palette (read back from the running game)

| idx | colour | | idx | colour |
|----|----------------|---|------|--------|
| 0 | (68, 0, 0) | | 8 | (68, 0, 0) |
| 1 | (0, 0, 0) | | 9 | (68, 0, 0) |
| 2 | (119, 0, 0) ↔ (136, 0, 0) | | 10 | (68, 0, 0) |
| 3 | (221/238/255, 0, 0) | | 11 | (68, 0, 0) |
| 4 | (255, 119, 0) | | 12 | (68, 0, 0) |
| 5 | (255, 221, 68) | | 13 | (68, 0, 0) |
| 6 | unused | | 14 | (68, 0, 0) |
| 7 | (255, 255, 255) | | 15 | (68, 0, 0) |

**Correction:** an earlier version of this doc said the flames animate by
palette alone. That came from a 12-frame sample that happened to catch the
texture still. Over a few seconds, 63% of kanji pixels change their plane data.
There are three animations layered together, all driven from code in
**00IPL.SCN** (see `ipl_sprites.py`):

1. **A 3-frame flipbook.** Every 6 frames, `cs:0x0eb1` rewrites the
   texture-segment immediate at `[0xf34]` to `[0xc2c] + 0x69c * ((frame/6) % 3)`,
   cycling three textures that sit 0x69c0 bytes apart (one per 192px column
   of DS_T2's artwork — not one per kanji, as I first assumed).
2. **A vertical wobble.** Every 9 frames, `cs:0x0e45` adds a value from the
   small table at `cs:0x0e60` to the progress word `[0xc32]`, which keeps
   hovering around −51..−54 instead of settling. The source row is
   `y_top − progress`, so the texture shifts a row or two up and down.
3. **Palette pulse** on entries 2 and 3, on a ~12-frame cycle.

Anything drawn through the sprite routine `0x0efd` gets the first two for
free, which is how the English subtitle is animated.

### The flame texture

A single static **192 × 376**, 3-bit-per-pixel texture, living at segment
`0x38a8` as three consecutive planes of `0x2340` bytes (24 bytes/row × 376
rows). It is a vertical fire ramp: dark red at the top, white at the bottom —
`img/title/fire_texture.png`.

All three kanji sample the *same* texture column, at the same vertical
alignment; the stencil is what makes them look different.

### The sprite table

The blitter at `0x27cb8` (called from `0x27c7d`) walks an 8-byte table. At the
title card its three entries live at `cs:0x0ee5`, `0x0eed`, `0x0ef5` with
`cs = 0x26d8`:

```c
struct sprite {
    uint16 x_bytes;       // x / 8
    uint16 width_words;   // 12 = 192px (unrolled path), 7 = 112px
    uint16 y_top;
    uint16 y_bottom;
};
```

| entry | x | width | y_top | y_bottom | glyph |
|-------|-----|-------|-------|----------|-------|
| `0x0ee5` | 48 | 192 | 72 | 261 | 黒 |
| `0x0eed` | 256 | 112 | 111 | 237 | の |
| `0x0ef5` | 400 | 192 | 26 | 314 | 剣 |

The caller computes the source offset from a single global **burn-in progress**
variable at `cs:0x0c32`:

```
si = (y_top - progress) * 24        ; 24 bytes per texture row
di = y_top * 80 + x_bytes
bp = y_bottom - y_top               ; rows to copy
```

`progress` sweeps down during the burn-in (which is what makes the flames
appear to rise through the letters) and comes to rest at **−53**. So in the
steady state the texture is sampled at `screen_row + 53`, and the texture's 376
rows are sized exactly to cover the tallest sprite: 剣 needs rows
`26+53 = 79` through `314+53 = 367`.

The blitter writes planes B, R and G only (`es` steps `0xa800 → 0xb000 →
0xb800`), then `si += 0x2340` for the next plane. It never touches plane I —
that is why the stencil survives.

## Where the data comes from

The **entire opening loads exactly one asset**: `DS_T2.AS2`, `0x6444` bytes at
offset `0x2b7fe` of `A.FA1`. A full INT 21h trace of the opening shows one
`OPEN A.FA1` and one `READ`, nothing else. So the flame texture, the stencil
and the burn-in script all live in that file.

`AS2` files have their own container header and a **second layer of
compression inside the FA1 compression** — the payload is high-entropy after
FA1 decompression:

```
0x00  "AS2\0"
0x04  uint32  file size (matches exactly, all 96 AS2 files)
0x08  uint32  ? (0x5000 for DS_T2 and the BAC_* backgrounds)
0x0C  uint16  0x190 = 400 for full-screen scenes, 0x120/0xc8/0x80 for others
0x0E  uint16  0x180 or 0x80
0x10+ payload
```

**This inner codec has not been cracked.** That is the one blocker for shipping
a modified title — see below.

## Adding "Blade of Darkness"

`img/title/title_new.png` (and `title_new.gif`) is the generated result:
the original calligraphy untouched, with an English subtitle below it lit by
the game's own flame texture and palette. `title_new_ingame.png` is the same
thing pushed into the live game's VRAM and screenshotted, so it has been
through the real display pipeline.

Composition (all in `title_logo.py`):

* **Type**: Goudy Old Style Bold, 50px caps, no extra tracking. Chosen over
  Cambria/Bookman because the roman caps sit well under brush calligraphy and
  the stems are thick enough to carry visible flame through a 1-bit stencil.
  Spans x 54–583, which is within a pixel or two of the Japanese logo's own
  x 50–583.
* **Position**: rows 330–364, in the ground-glow band below the calligraphy.
* **Fire**: three engine-shaped 192px sprites at x = 48, 240, 432, sampling
  texture rows 230+. Rows around 230 are deliberately *not* the brightest part
  of the texture — sampling lower makes the subtitle go near-white and compete
  with the Japanese, which should stay dominant.
* **Stencil**: the ground-glow dither is cleared across the text's rows so the
  three sprite rectangles do not show through it as bright blocks, then the
  letterforms are punched in.

### What shipping this would actually take

1. **Crack the AS2 inner codec** (decode *and* encode) to rewrite the stencil
   inside `DS_T2.AS2`. This is the real work. Per `../CLAUDE.md`, the way to do
   it is to hook the load and follow the caller's return address into the
   decoder — in RAM the code is already relocated, so `capstone` in 16-bit mode
   over `m.read()` disassembles it directly. The same method cracked
   Possessioner's CGX format in one session.
2. **Add three sprite-table entries** for the subtitle band. This is pure data
   in the code segment and needs no new code — the blitter already handles
   arbitrary x/width/y_top/y_bottom.
3. **Extend the flame texture.** This is the one genuine obstacle: `si` is
   derived from `y_top`, so a sprite at `y_top = 330` wants texture row
   `330 + 53 = 383`, and the texture only has 376. Either grow the texture in
   `DS_T2.AS2` by ~60 rows, or patch the four-instruction `si` computation at
   `0x27c8c` to take a per-sprite source row from a new table field.

## Related: the patched build's opening is broken

On `original/…hdi` the opening plays through and the logo burns in. On
`patched/…hdi` it **hangs**: the crawl plays, the fire band rises, and then the
screen freezes completely — byte-identical frames for 600+ emulated seconds,
with the logo never appearing. Reproduce with `title_logo.py` pointed at the
patched disk, or:

```
CoreEmu()                      # defaults to the patched disk
-> title menu -> "Watch Opening" -> run ~60s -> frozen
```

This is unrelated to the logo work but worth fixing; the opening is reachable
from the title menu, so players will hit it.
