# Kuro no Ken: what the autoplayer has mapped

Merged from 7 run(s): auto_run13, auto_run14, auto_run16, auto_run18, auto_run19, auto_run20, auto_run21.

Each entry is an NPC or trigger zone that was tried, where it led, and the
dump rows its text came from (`file offset`, English or Japanese column).
docs/script_map.md covers the same ground statically, for the whole game.

## ?

- bump  0  2 page(s)  text: 99CMN.SCN 0x007ea
- bump  1  -> stg  3 page(s)  [blocked: zone 1 did nothing within 20s]
- bump  2  1 page(s)  [blocked: x did not converge on 0x1e3, at 0x10e]  text: 99CMN.SCN 0x007ea
- bump  3  1 page(s)  [blocked: y did not converge on 0x15b, at 0x135]  text: 99CMN.SCN 0x007ea
- bump  4  1 page(s)  [blocked: y did not converge on 0x22b, at 0x135]  text: 99CMN.SCN 0x007ea
- bump  5  1 page(s)  [blocked: y did not converge on 0x215, at 0x135]  text: 99CMN.SCN 0x007ea
- bump  6  1 page(s)  [blocked: x did not converge on 0x172, at 0x10e]  text: 99CMN.SCN 0x007ea
- npc   1  1 page(s)  text: 99CMN.SCN 0x007ea
- npc   2  1 page(s)  text: 99CMN.SCN 0x007ea
- npc   3  1 page(s)  text: 99CMN.SCN 0x007ea
- npc   4  1 page(s)  text: 99CMN.SCN 0x007ea
- step  0  2 page(s)  [blocked: x stuck at 0x1e (target 0x32) - no moveme]  text: 99CMN.SCN 0x007ea
- step  1  1 page(s)  [blocked: zone 1 did nothing within 20s]  text: 99CMN.SCN 0x007ea
- step  2  1 page(s)  [blocked: zone 2 did nothing within 20s]  text: 99CMN.SCN 0x007ea
- step  3  1 page(s)  [blocked: zone 3 did nothing within 20s]  text: 99CMN.SCN 0x007ea
- step  4  1 page(s)  [blocked: x did not converge on 0x16f, at 0x10e]  text: 99CMN.SCN 0x007ea
- step  5  1 page(s)  [blocked: y did not converge on 0x18b, at 0x135]  text: 99CMN.SCN 0x007ea
- step  6  1 page(s)  [blocked: x did not converge on 0x147, at 0x10e]  text: 99CMN.SCN 0x007ea
- step  7  1 page(s)  [blocked: zone 7 did nothing within 20s]  text: 99CMN.SCN 0x007ea
- step  8  1 page(s)  [blocked: x did not converge on 0x20a, at 0x10e]  text: 99CMN.SCN 0x007ea

## fld1

- bump  0  1 page(s)
- bump  1  1 page(s)
- bump  2  [blocked: y did not converge on 0x111, at 0xfc]
- bump  3  [blocked: y did not converge on 0x15b, at 0x101]
- bump  4  [blocked: y did not converge on 0x22b, at 0x101]
- bump  5  [blocked: x did not converge on 0x20a, at 0x1cf]
- bump  6
- npc   1  [blocked: could not reach slot 1]
- npc   2  [blocked: could not reach slot 2]
- npc   3  [blocked: could not reach slot 3]
- npc   4  [blocked: could not reach slot 4]
- step  0  [blocked: zone 0 did nothing within 20s]
- step  1  [blocked: zone 1 did nothing within 20s]
- step  2  [blocked: zone 2 did nothing within 20s]
- step  3  [blocked: zone 3 did nothing within 20s]
- step  4  [blocked: y did not converge on 0x1d9, at 0x101]
- step  5  [blocked: y did not converge on 0x185, at 0x101]
- step  6  [blocked: y did not converge on 0x168, at 0x101]
- step  7  [blocked: zone 7 did nothing within 20s]
- step  8  [blocked: x did not converge on 0x20a, at 0x1cf]
- step  9  2 page(s)  [blocked: y did not converge on 0x7f, at 0xc9]
- step 10  2 page(s)  [blocked: y stuck at 0x87 (target 0x15) - no moveme]
- step 11  2 page(s)  [blocked: y did not converge on 0xaf, at 0xc9]
- step 12  2 page(s)  [blocked: y stuck at 0x49 (target 0x5d) - no moveme]  text: 99CMN.SCN 0x007ea
- step 13  2 page(s)  [blocked: y did not converge on 0x9f, at 0xc9]
- step 14  -> map_a942  2 page(s)  text: 99CMN.SCN 0x007ea
- step 15  2 page(s)  [blocked: y did not converge on 0xaf, at 0xc9]
- step 16  2 page(s)  [blocked: x stuck at 0x121 (target 0x119) - no move]
- step 17  2 page(s)  [blocked: x stuck at 0x142 (target 0xbe) - no movem]
- step 18  2 page(s)  [blocked: y stuck at 0xfd (target 0x1a5) - no movem]
- step 19  2 page(s)  [blocked: y stuck at 0xfd (target 0x18f) - no movem]
- step 20  2 page(s)  [blocked: x stuck at 0x11a (target 0xee) - no movem]
- step 21  2 page(s)  [blocked: x stuck at 0x11a (target 0xec) - no movem]
- step 22  2 page(s)  [blocked: y did not converge on 0x72, at 0xc9]
- step 23  2 page(s)  [blocked: y did not converge on 0x70, at 0xc9]
- step 24  2 page(s)  [blocked: y did not converge on 0x91, at 0xc9]

## map_2c3f

Scripts loaded here: 02OLB.SCN, 02OLB02.SCN (docs/script_map.md lists their dump rows)

- bump  0  [blocked: zone 0 did nothing within 20s]
- bump  1  1 page(s)  text: 02OLB02A.SCN 0x00b67
- bump  2  [blocked: y stuck at 0x1c1 (target 0x163) - no move]
- bump  3  [blocked: zone 3 did nothing within 20s]
- bump  4  [blocked: y did not converge on 0xbf, at 0xdd]
- bump  5  [blocked: y stuck at 0x1c1 (target 0x175) - no move]
- bump  6  [blocked: y did not converge on 0x8b, at 0xdd]
- bump  7  37 page(s)  [blocked: battle made no progress for 90 s (no menu]  text: 02OLB01.SCN 0x0150c, None シノブ・リュード
- bump  8  [blocked: x did not converge on 0x1ce, at 0x1ac]
- bump  9  [blocked: x did not converge on 0x1ce, at 0x1ac]
- bump 10  [blocked: x did not converge on 0x1ba, at 0x1ac]
- bump 11  -> olb1
- bump 12  [blocked: y stuck at 0x1c1 (target 0xbf) - no movem]
- npc   1  1 page(s)  text: 02OLB01.SCN 0x01449
- npc   2  [blocked: could not reach slot 2]
- npc   3  1 page(s)  text: 02OLB02A.SCN 0x00d8d
- npc   4  1 page(s)  text: 02OLB01.SCN 0x01449
- step  0  -> olb1
- step  1  1 page(s)  text: 02OLB02A.SCN 0x00b67
- step  2  [blocked: y did not converge on 0x170, at 0x169]
- step  3  [blocked: y stuck at 0x1c1 (target 0x192) - no move]
- step  4  [blocked: y stuck at 0x1c1 (target 0x126) - no move]
- step  5  [blocked: y did not converge on 0xa8, at 0xdd]
- step  6  [blocked: y did not converge on 0xac, at 0xdd]
- step  7  8 page(s)  [blocked: zone 7 did nothing within 20s]  text: 02OLB02A.SCN 0x00d18
- step  8  -> olb1
- step  9  [blocked: y did not converge on 0x4c, at 0xdd]
- step 10  [blocked: x did not converge on 0x1c7, at 0x1ac]

## map_a942

- bump  0  1 page(s)  text: 99CMN.SCN 0x007ea
- bump  5  1 page(s)
- bump  6
- npc   1  [blocked: could not reach slot 1]
- npc   2  [blocked: could not reach slot 2]
- npc   3  [blocked: could not reach slot 3]
- npc   4  [blocked: could not reach slot 4]
- step  0  [blocked: y did not converge on 0x5a, at 0xac]
- step  1  [blocked: y did not converge on 0x4d, at 0xac]
- step  2  [blocked: y did not converge on 0x93, at 0xac]
- step  3  [blocked: x did not converge on 0x7d, at 0x11a]
- step  4  [blocked: zone 4 did nothing within 20s]
- step  5  [blocked: zone 5 did nothing within 20s]
- step  6  [blocked: zone 6 did nothing within 20s]
- step  7  [blocked: x did not converge on 0x10f, at 0x11a]
- step  8  [blocked: y did not converge on 0x7d, at 0xac]

## olb1

Scripts loaded here: 02OLB.SCN, 02OLB02.SCN (docs/script_map.md lists their dump rows)

- bump  0  -> gakusha2
- bump  1  -> madosi2
- bump  2  8 page(s)  [blocked: zone 2 did nothing within 20s]  text: 02OLB02A.SCN 0x003a4
- bump  3  -> olb2
- bump  4  -> olb2
- bump  5  -> olb2
- bump  6  -> olb2
- bump  7  -> olb2
- bump  8  [blocked: zone 8 did nothing within 20s]
- bump 10  1 page(s)  text: 02OLB02.SCN 0x00613
- npc   1  [blocked: could not reach slot 1]
- npc   2  [blocked: could not reach slot 2]
- npc   3  1 page(s)  text: 02OLB02A.SCN 0x00289
- npc   4  [blocked: could not reach slot 4]
- step  0  -> gakusha2
- step  1  -> madosi2
- step  2  8 page(s)  [blocked: zone 2 did nothing within 20s]  text: 02OLB02A.SCN 0x003a4
- step  3  -> olb2
- step  4  -> olb2
- step  5  -> olb2
- step  6  -> olb2
- step  7  -> olb2
- step  8  -> olb2  1 page(s)  text: 02OLB02A.SCN 0x00289
- step  9  -> stg
- step 10  -> fld1

## stg

- bump  0  3 page(s)
- bump  1  4 page(s)
- bump  2  3 page(s)
- bump  3  3 page(s)
- bump  4  3 page(s)
- bump  6  3 page(s)
- npc   1  [blocked: could not reach slot 1]
- npc   2  [blocked: could not reach slot 2]
- npc   3  [blocked: could not reach slot 3]
- npc   4  [blocked: could not reach slot 4]
- step  0  3 page(s)
- step  1  3 page(s)
- step  2  3 page(s)

## tni1

- bump  0  -> tni2
- npc   1  -> fld1  [blocked: could not reach slot 1]
- npc   2  -> fld1  [blocked: could not reach slot 2]
- npc   3  [blocked: could not reach slot 3]
- npc   4  [blocked: could not reach slot 4]
- step  0  -> fld1
- step  1  -> tni2

## tni2

- npc   1  [blocked: could not reach slot 1]
- npc   2  [blocked: could not reach slot 2]
- npc   3  [blocked: could not reach slot 3]
- npc   4  [blocked: could not reach slot 4]
- step  0  -> tni1
- step  1  [blocked: zone 1 did nothing within 20s]
- step  2  [blocked: zone 2 did nothing within 20s]
- step  3  -> tni1

## Dump coverage

How much of each file has been seen on screen. "translated" counts rows with
English in the workbook, so a file at 0/N translated but seen in play is text
that still needs translating.

| file | rows seen | rows in workbook | translated |
|---|---|---|---|
| 02OLB01.SCN | 2 | 140 | 12 |
| 02OLB02.SCN | 1 | 11 | 9 |
| 02OLB02A.SCN | 5 | 96 | 61 |
| 99CMN.SCN | 1 | 8 | 0 |
| null | 1 | 0 | 0 |

10 rows seen across 5 files; the workbook has 10950 rows in 658 files.

### Files never reached yet (654)

`00IPL.SCN`, `02OLB`, `02OLB.SCN`, `02OLB00A.SCN`, `02OLB01A.SCN`, `02OLB01B.SCN`, `02OLB03.SCN`, `02OLB03A.SCN`, `02OLB04.SCN`, `02OLB05.SCN`, `02OLB06.SCN`, `03YSK`, `03YSK.SCN`, `03YSK00.SCN`, `03YSK01A.SCN`, `03YSK01B.SCN`, `03YSK01C.SCN`, `03YSK65.SCN`, `03YSK69.SCN`, `03YSK690.SCN`, `03YSK69A.SCN`, `03YSK69B.SCN`, `03YSK69C.SCN`, `03YSK69D.SCN`, `03YSK70.SCN`, `04OLD`, `04OLD.SCN`, `04OLD01A.SCN`, `04OLD01B.SCN`, `04OLD01C.SCN`, `04OLD01D.SCN`, `05SKS`, `05SKS.SCN`, `05SKS01.SCN`, `05SKS02.SCN`, `05SKS03.SCN`, `05SKS04.SCN`, `05SKS05.SCN`, `05SKS06.SCN`, `05SKS07.SCN`, `05SKS08.SCN`, `06BLK`, `06BLK.SCN`, `06BLK00A.SCN`, `06BLK00B.SCN`, `06BLK01A.SCN`, `06BLK01B.SCN`, `06BLK01C.SCN`, `06BLK01D.SCN`, `06BLK02A.SCN`, `06BLK02B.SCN`, `06BLK02C.SCN`, `06BLK02D.SCN`, `06BLK02E.SCN`, `06BLK02I.SCN`, `06BLK02O.SCN`, `06BLK03A.SCN`, `06BLK03I.SCN`, `06BLK03O.SCN`, `06BLK04A.SCN`, `06BLK04B.SCN`, `06BLK04I.SCN`, `06BLK04J.SCN`, `06BLK04K.SCN`, `06BLK04O.SCN`, `06BLK05I.SCN`, `06BLK05J.SCN`, `06BLK05K.SCN`, `06BLK05O.SCN`, `06BLK06K.SCN`, `06BLK07.SCN`, `06BLK07I.SCN`, `06BLK07J.SCN`, `06BLK07K.SCN`, `06BLK07L.SCN`, `06BLK07O.SCN`, `06BLK08I.SCN`, `06BLK09I.SCN`, `06BLK10I.SCN`, `06BLK11I.SCN`, `06BLK12E.SCN`, `06BLK12I.SCN`, `07CSL`, `07CSL.SCN`, `07CSL01.SCN`, `07CSL01A.SCN`, `07CSL01B.SCN`, `07CSL02.SCN`, `07CSL02A.SCN`, `07CSL02B.SCN`, `07CSL04.SCN`, `07CSL04A.SCN`, `07CSL04B.SCN`, `07CSL05.SCN`, `07CSL05A.SCN`, `07CSL05B.SCN`, `07CSL05C.SCN`, `07CSL05D.SCN`, `07CSL05E.SCN`, `07CSL06.SCN`, `07CSL06E.SCN`, `07CSL07.SCN`, `07CSL07A.SCN`, `07CSL08.SCN`, `07CSL08A.SCN`, `07CSLI00.SCN`, `07CSLI01.SCN`, `07CSLI02.SCN`, `07CSLI03.SCN`, `07CSLI04.SCN`, `08CKD`, `08CKD.SCN`, `08CKD01A.SCN`, `08CKD02A.SCN`, `09HIK`, `09HIK.SCN`, `09HIK01A.SCN`, `09HIKI01.SCN`, `0x00de1`, `0x00de8`, `0x00ded`, `0x00df2`, `0x00df7`, `0x00dfc`, `0x00e01`, `0x00e06`, `0x00e0e`, `0x00e13`, `0x00e18`, `0x00e1d`, `0x00e22`, `0x010ce`, `0x010e1`, `0x010e8`, `0x010ef`, `0x010f6`, `0x01105`, `0x01116`, `0x01129`, `0x01130`, `0x0113f`, `0x01144`, `0x0114b`, `0x01158`, `0x01165`, `0x01174`, `0x01183`, `0x0118a`, `0x01197`, `0x011ac`, `0x011b5`, `0x011bc`, `0x011c9`, `0x011d0`, `0x011db`, `0x011e4`, `0x011f1`, `0x01202`, `0x01225`, `0x0123c`, `0x01253`, `0x01266`, `0x01291`, `0x012be`, `0x02bfc`, `0x02c07`, `0x02c0c`, `0x02c17`, `0x02c26`, `0x02c31`, `0x02c38`, `0x02c3f`, `0x02c4e`, `0x02c5b`, `0x02c64`, `0x02c6b`, `0x02c74`, `0x02c83`, `0x02c8e`, `0x02c99`, `0x02ca2`, `0x02cab`, `0x02cb4`, `0x02cbd`, `0x02cc6`, `0x02ccf`, `0x02cd8`, `0x02cdf`, `0x02ce6`, `0x02cef`, `0x02cfc`, `0x02d0b`, `0x02d1c`, `0x02d23`, `0x02d2c`, `0x02d43`, `0x02d56`, `0x02d67`, `0x02d70`, `0x02d77`, `0x02d8c`, `0x02d9b`, `0x02da4`, `0x02db1`, `0x02db8`, `0x02dbf`, `0x02dc6`, `0x02dd9`, `0x02de8`, `0x02df7`, `0x02e06`, `0x02e19`, `0x02e20`, `0x02e2b`, `0x02e3c`, `0x02e49`, `0x02e56`, `0x02e61`, `0x02e70`, `0x02e81`, `0x02e92`, `0x02e9b`, `0x02ea4`, `0x02ead`, `0x02eb8`, `0x02ec7`, `0x02eda`, `0x02eeb`, `0x02ef8`, `0x02f05`, `0x02f18`, `0x02f21`, `0x02f2c`, `0x02f39`, `0x02f44`, `0x02f51`, `0x02f62`, `0x02f75`, `0x02f7e`, `0x02f89`, `0x02f94`, `0x02fa5`, `0x02fb2`, `0x02fbd`, `0x02fc8`, `0x02fd7`, `0x02fe4`, `0x02feb`, `0x02ff8`, `0x03001`, `0x03010`, `0x03021`, `0x0302c`, `0x0303d`, `0x03046`, `0x03053`, `0x03064`, `0x03075`, `0x0307e`, `0x03089`, `0x03096`, `0x030a5`, `0x030b6`, `0x030c5`, `0x030d0`, `0x030d7`, `0x030de`, `0x030eb`, `0x030f6`, `0x030ff`, `0x03110`, `0x03119`, `0x0312a`, `0x03133`, `0x0313e`, `0x03149`, `0x03154`, `0x0315f`, `0x03168`, `0x03173`, `0x03180`, `0x03189`, `0x03192`, `0x031a2`, `0x031af`, `0x031bc`, `0x031c9`, `0x031d4`, `0x031de`, `0x031f5`, `0x0320c`, `0x03225`, `0x0323e`, `0x0324d`, `0x03254`, `0x03265`, `0x03290`, `0x032b5`, `0x032ce`, `0x032e3`, `0x032fa`, `0x0331f`, `0x03340`, `0x03361`, `0x03378`, `0x0338f`, `0x033a6`, `0x033bd`, `0x033d8`, `0x033f1`, `0x03412`, `0x03431`, `0x03458`, `0x03473`, `0x0348a`, `0x034bb`, `0x034ea`, `0x0350f`, `0x0354a`, `0x03569`, `0x0359c`, `0x035bb`, `0x035dc`, `0x035f5`, `0x03612`, `0x0363b`, `0x0364e`, `0x0366b`, `0x0368e`, `0x036af`, `0x036c8`, `0x036e5`, `0x03706`, `0x03729`, `0x0375a`, `0x03781`, `0x037b8`, `0x037d7`, `0x03802`, `0x0382b`, `0x03842`, `0x03861`, `0x0388e`, `0x038c3`, `0x038f2`, `0x03929`, `0x03950`, `0x0396b`, `0x03988`, `0x039a5`, `0x039ca`, `0x039e3`, `0x03a18`, `0x03a31`, `0x03a5a`, `0x03a8b`, `0x03abc`, `0x03ad3`, `0x03ae4`, `0x03b11`, `0x03b4a`, `0x03b71`, `0x03b90`, `0x03bab`, `0x03bc4`, `0x03be9`, `0x03c18`, `0x03c3b`, `0x03c6e`, `0x03ca9`, `0x03cdc`, `0x03cf7`, `0x03d18`, `0x03d35`, `0x03d6e`, `0x03d8b`, `0x03db2`, `0x03dcf`, `0x03dfa`, `0x03e13`, `0x03e2a`, `0x03e49`, `0x03e7c`, `0x03e9d`, `0x03ecb`, `0x03ef6`, `0x03f2f`, `0x03f48`, `0x03f6b`, `0x03f84`, `0x03f95`, `0x03fa6`, `0x03fb7`, `0x03fc8`, `0x03fe5`, `0x04000`, `0x0401d`, `0x0404c`, `0x0405f`, `0x0406c`, `0x04079`, `0x04086`, `0x09e01`, `0x09e33`, `0x09e3d`, `0x09e51`, `0x09ed2`, `0x09ed5`, `0x09f2c`, `0x09f6b`, `0x0b1e0`, `0x0b1e9`, `0x0b1f0`, `0x0ba4a`, `0x0ba55`, `0x0ba5a`, `0x0ba5f`, `0x0ba64`, `0x0ba6e`, `0x0ba79`, `0x0ba7e`, `0x0ba83`, `0x0ba8d`, `0x0ba96`, `0x0ba9e`, `0x0baa3`, `0x0baab`, `0x0bab0`, `0x0baba`, `0x0bac1`, `0x0bac8`, `0x0bad2`, `0x0bad9`, `0x0bae1`, `0x0baea`, `0x0baf5`, `0x0bafe`, `0x0bb07`, `0x0bb0c`, `0x0bb11`, `0x0bb16`, `0x0bb1c`, `0x0bb2d`, `0x0bb44`, `0x0bb58`, `0x0bb5d`, `0x0bb64`, `0x0bb6b`, `0x0bb76`, `0x0bb81`, `0x0bb88`, `0x0bb8f`, `0x0bb96`, `0x0bb9b`, `0x0bba0`, `0x0bbac`, `0x0bbbe`, `0x0bbc9`, `0x0bbd4`, `0x0bbeb`, `0x0bbfc`, `0x0bc0d`, `0x0bc1c`, `0x0bc2d`, `0x0d240`, `0x0d245`, `0x0d24d`, `0x0d252`, `0x0d25c`, `0x0d261`, `0x0d26b`, `0x0d27c`, `0x0d8bc`, `0x0d8c1`, `0x0d8c6`, `0x0d8cb`, `0x0d8d0`, `0x0d8d5`, `0x0d8db`, `0x0d8e0`, `0x0d8e5`, `0x0d8ea`, `0x0d8ef`, `0x0d8f4`, `0x0e6f0`, `0x0e701`, `0x0e710`, `0x0e71f`, `0x0e72e`, `0x0e73c`, `0x0e74d`, `0x0e75c`, `0x0e76b`, `0x0e77b`, `0x0e78a`, `10TNI`, `10TNI.SCN`, `10TNI01A.SCN`, `10TNI02A.SCN`, `10TNI03A.SCN`, `10TNI04A.SCN`, `10TNII00.SCN`, `10TNII01.SCN`, `10TNII02.SCN`, `11STG`, `11STG.SCN`, `12MRS`, `12MRS.SCN`, `13SLP`, `13SLP.SCN`, `14YMM`, `14YMM.SCN`, `14YMM53.SCN`, `15MKR`, `15MKR.SCN`, `15MKR01A.SCN`, `15MKR01B.SCN`, `15MKR01C.SCN`, `15MKR01D.SCN`, `15MKR01E.SCN`, `15MKR02A.SCN`, `15MKR02B.SCN`, `15MKR02C.SCN`, `15MKR02D.SCN`, `15MKR02E.SCN`, `15MKR02F.SCN`, `15MKR02G.SCN`, `15MKR02H.SCN`, `15MKR61.SCN`, `16MKI`, `16MKI.SCN`, `16MKI01A.SCN`, `16MKI01B.SCN`, `16MKI01C.SCN`, `16MKI01D.SCN`, `16MKI61.SCN`, `17DRL`, `17DRL.SCN`, `17DRL01A.SCN`, `17DRL01B.SCN`, `17DRL02A.SCN`, `17DRL03A.SCN`, `17DRL04A.SCN`, `17DRL08A.SCN`, `18KSK`, `18KSK.SCN`, `19IRE`, `19IRE.SCN`, `19IRE27.SCN`, `19IRE36.SCN`, `19IRE92.SCN`, `19IRE94.SCN`, `20NNP`, `20NNP.SCN`, `20NNP93.SCN`, `21KTI`, `21KTI.SCN`, `22MZI`, `22MZI.SCN`, `23SOH`, `23SOH.SCN`, `23SOH01A.SCN`, `23SOH01B.SCN`, `23SOH01I.SCN`, `23SOH02A.SCN`, `23SOH02B.SCN`, `24UMB`, `24UMB.SCN`, `24UMB54.SCN`, `24UMB56.SCN`, `24UMB57.SCN`, `25TOU`, `25TOU.SCN`, `25TOU00A.SCN`, `25TOU00B.SCN`, `25TOU00C.SCN`, `25TOU00D.SCN`, `25TOU00E.SCN`, `26KKR`, `26KKR.SCN`, `26KKR01A.SCN`, `26KKR02.SCN`, `26KKR02A.SCN`, `26KKR03.SCN`, `26KKR04.SCN`, `26KKR04A.SCN`, `26KKR05.SCN`, `26KKR05A.SCN`, `26KKR06.SCN`, `26KKR06A.SCN`, `26KKRI00.SCN`, `27KKI`, `27KKI.SCN`, `27KKI01.SCN`, `27KKI01A.SCN`, `27KKI02A.SCN`, `27KKI03A.SCN`, `27KKI04A.SCN`, `27KKII00.SCN`, `27KKII01.SCN`, `28KDI`, `28KDI.SCN`, `29KNT`, `29KNT.SCN`, `29KNT99B.SCN`, `30IZM`, `30IZM.SCN`, `C020_X10.BSD`, `C021_X10.BSD`, `C022_S10.BSD`, `C022_S20.BSD`, `C022_T10.BSD`, `C042_X10.BSD`, `C051_S10.BSD`, `C051_X10.BSD`, `D010_S20.BSD`, `D010_X10.BSD`, `D011_S20.BSD`, `D011_T20.BSD`, `D011_U20.BSD`, `D031_S10.BSD`, `D040_S10.BSD`, `D050_S10.BSD`, `D050_T01.BSD`, `D050_T02.BSD`, `D051_X10.BSD`, `D052_S10.BSD`, `D060_S21.BSD`, `D061_X10.BSD`, `D080_T10.BSD`, `D090_X32.BSD`, `D100_X01.BSD`, `D100_X02.BSD`, `D100_ZA1.BSD`, `D100_ZA2.BSD`, `D100_ZA3.BSD`, `D100_ZA4.BSD`, `D100_ZA5.BSD`, `D100_ZA6.BSD`, `D100_ZA7.BSD`, `D110_S10.BSD`, `D130_T32.BSD`, `D130_X10.BSD`, `DL20_T12.BSD`, `DL21_O10.BSD`, `DL21_P10.BSD`, `DL21_Q10.BSD`, `DL21_R10.BSD`, `DL21_S12.BSD`, `DL21_X10.BSD`, `DL30_X10.BSD`, `DL30_Y10.BSD`, `DL30_Z10.BSD`, `DS00_E10.BSD`
