# The game's sprites, to name

Every person on a map is an object with a sprite number - an index into that
map's own set, so `02OLB 4` and `06BLK 4` are different people. Put a name in
`tools/npc_names.json` and the context workbook shows it in the **Who** column
instead of the number, with the place they stand (`@13,14`, in tiles) after it.

`count` is how many people in that area use the sprite; the line is one of
theirs, to recognise them by.

## Photographs of the speakers in place (2026-09-24)

`docs/npc_img/<scene script>_<block>.png` is the corner of the map a conversation
happens in, with the person who says it standing there; tools/translator_context.py
hangs it on the scene's **Who** cell, so hovering shows who is talking. They are taken
by `python tools/npc_photos.py`, which walks the game's own zone graph from a real-play
save state: the game builds the people of one region at a time (four or so) and rebuilds
them when the player *walks* into a step zone or through a door (standing in one, or
being written there, fires nothing), so the tool stands the player just outside each
zone, steps in with no-clip, reads through any scene, and photographs whoever is live.
A live person's talk stub (`+0x2a` of its object) is the address docs/npcs.json records,
so the picture is named after the scene it opens, whoever the person is and wherever
they have wandered.

One thing limits it, and it is worth knowing on its own: **a save state only works with
the disk image it was saved on.** np2core states hold RAM, and DOS keeps its cached
directory sectors in RAM, so after `load_state` the game reads archives at the cluster
numbers of the disk that was mounted at save time. The `.hdi` in `patched/` moves with
every build, so a state saved on one build reads garbage from the next: a region switch
exits to DOS, a battle freezes on a garbled screen, a sprite fails to load and the game
loops on its size (the world-map gate soldier that looked "frozen"). Found by the np2core
maintainer (romtools/np2core/requests/done/2026-09-24-KuroNoKen-world-map-gate-freeze.md)
after I had blamed the emulator. So: explore from states saved *in this session* after a
fresh boot, on a disk that does not change - the original `.hdi` - which is what the
`fo_*` states are. The old `area_NN`, `auto_run*`, `r01_*` and `jp_*` states are only
good with the disk they were made on, and mostly are not any more.

### Running it now

    set KURO_HDD=original\Blade of Darkness (Kuro no Ken).hdi     (any tool mounts this disk)
    python tools/npc_photos.py                                    (the fo_* states)
    python tools/autoplay.py --start fo_dog_from_sks5 --name x    (play on; +30 for a story counter)
    python tools/npc_photos.py --state x_44 --state x_45 ...      (photograph where it got to)
    python tools/translator_context.py --basis docs/story_order_basis.txt

The autoplayer now scores a move that advances one of the real story counters by a
step above any amount of new text (STORY_BONUS), which is what took it through the
castle audience; and it treats a hang as a crash (`frozen`: the screen stops changing
and the party cannot move). Makrun (15MKR) is reachable from the post-castle world
map long before the recorded players go there, and every shop door on its maps hangs
the game that way - entered by walking, no-clip or not - so the town is a trap at this
stage and the autoplayer now steps back out of it. From there it found Sohagi (23SOH)
instead. The recorded route (rest house, Old Book Cave, capital stage 1) is what a
story-following driver should take next; the autoplayer's "new map" appetite does not.

### Following the recorded route (2026-09-25)

    set KURO_HDD=original\Blade of Darkness (Kuro no Ken).hdi
    python tools/autoplay.py --start fo_dog_from_sks5 --follow twitch --route-from 06BLK01B --name x

`--follow twitch|werdna` turns docs/video_anchors.json into the recorded player's
script sequence (runs of 2+ anchors, consecutive repeats folded: 264 scripts for the
Twitch run) and keeps a pointer into it. Each trial's dialogue is matched to scripts -
by the English when a page matches, else line by line through the workbook's Japanese
(`Script.find_japanese`), since on the original disk every page is Japanese - and a
trial whose dialogue is the next script (or one of the next three) scores ROUTE_BONUS,
above anything else; failing that, landing in the next script's area, or another map
of it, or back in the previous script's area, scores a little. A match is only taken
from a script of the area the trial landed in (a shared line names scripts of other
towns too), and on a map not named yet only from the areas in play. Progress is
logged as `route: n/264 done, next <script>`; a hang reads as a crash (`frozen`), a
status screen read as a battle is closed with one ESC, a battle on the Japanese disk
is fought by menu row, a place where no move brings new text is left by any map
change, and a trap that no move leaves is backtracked out of (the move that entered
it is never taken from there again).

What it does (2026-09-26, after the planner): from the capital arrival it plays the
route through the capital's first scripts, the castle, the Tanigawa cutscene, Albein,
the manor, the rest house and 12MRS - route script 32 of 264 - in about forty steps,
most of them one trial each. Three pieces made the difference:

- **A map name that comes from RAM.** The last resource name is no map identity (a
  sprite or a script overwrites it, and the castle is one file with several zone
  layouts), so a map is `<area><region>_<zone crc>`: global var 2 (the area number the scripts
  carry as their prefix), global var 4 (the region within it - a house interior reuses
  its map's zone layout, so the layout alone merged shops with the street) and the
  zone table's fingerprint - `0700_0bef` is the castle's hall, `0600_62e9` the capital's
  street, `0609_74ea` a shop off its second map. The same in every run, so knowledge
  accumulates.
- **An atlas, routes/atlas.json.** Every trial of every run teaches it: which move on
  which map leads where (with a count per destination - the same door lands
  differently depending on where the party stood), which move played which script,
  which scene scripts the people of a map open (from their talk stubs, `resolve_live`).
  A planner does a breadth-first search over it for the shortest path to a map that
  plays the next script, and the follower takes the first move of that path - all the
  moves known to lead there, as one small trial set, and only when it lands where the
  atlas said does it count. The world map is walked by standing beside the exit and
  stepping in (no no-clip there), from every side if need be.
- **What the route wants, as a typed window.** Debts first (scripts the pointer skipped
  when a later one matched; paying one moves the pointer back to just after it, since
  the later matches were premature), then the next three route scripts, widened when
  each was already tried where it is known to play. A script whose stage its area has
  not reached (`06BLK02A` needs the capital's counter, var 0x82+6, at 2 - the hub's
  table at 06BLK.SCN 0x18) is replaced by the scripts that write that counter value
  (`20 <var> 00 <value> 00`, found by scanning the decompressed scripts: 07CSL02 and its
  scenes for 2, 11STG01 for 1), and one of those only counts once a counter moved.
  A wanted script of the area the party stands in disables the shortcut: every move of
  that map is tried, because the pass's scene is a step zone none of the exits' walks
  crossed.

Two things it learned to see: a hang (`frozen`, tested on a snapshot that is restored -
a party that has just arrived stands on the way back out, and the movement test itself
walked it back to the rest house every time), and a **reset**: the game restarting from
its save (most story counters back to zero) after a lost battle, a deadly door (the
capital's inner doors after the pass, everything in area 14) or an arrest (the church
at the wrong stage). A single counter going down is not a reset - 11STG01 puts the
manor's back to 1 while raising four others.

Where it stands (2026-09-26, night): route script 65 of 264, Makrun reached. The
stall at 32 was the follower's own mistake - it applied the castle hub's rule (counter
>= stage) to every area, while the capital's hub loads its stage 2 at counter 1
(06BLK.SCN's table at 0x16); `hub_stages` now reads each hub's own table. What followed,
in the order runs 37-41 found it: the capital's stage-2 scripts (32-56, shops included -
a shop's item list read as a battle until `fight` learned to leave it), Genhas
(06BLK02D, in region 11 of the capital's second map - a house that shares its map's
zone layout, which is why the region number is now part of a map's name), the rest
house's stage-2 guard, the dungeon under it (08CKD01A, and on into area 09), the
castle's inner region from the dungeon's far end, the throne room (0701) and back to
the hall, the hall's doorway zone at (88-99, 71) - state 6 - and the audience in
region 23 (37 pages of 07CSL02B, the counters 0x84..0x88 written to 4 3 2 2 2), then
the capital's stage 3, the rest house's, and the world map's exit to Makrun.
Lessons from that stretch: a scene script with many entries (07CSL02A holds the
guards' lines too) is matched by any one of its lines, so a route hit for a scene the
video spent long on now needs several pages (`_pages_needed`); a no-entry zone after
the audience (the hall's (48-55, 131), handler 0x2dd0) pushes the party into a loop of
guard fights that never returns to a map, which the follower treats as a death and
rewinds past; a trial that died lands wherever the save reloads, so it teaches no
edge; and when the wanted area is one the atlas never saw, the way to it starts on the
world map.

Where it stopped for a day: Makrun's doors (2026-09-26). Not the emulator - the game,
in a state it never reaches by itself. Makrun's hub loads a different stage script for
each value of the town's counter (var 0x91: 15mkr01a at 0, 15mkr01b at 1-2, 01c at 3-5,
01d at 6, 01e at 7, 61 at 8), and its door handlers switch on the region into the stage
script's entry table at 0x1809..0x181b, ten entries. 15mkr01a has four, so a door at
counter 0 runs into the middle of its code and a `01` (native far call) lands the CPU in
the interrupt vector table; the two D.FA1 reads before the hang are only the region's
tiles. With the counter poked to 1 from the world map the doors open the shops, an
innkeeper talks and a statue scene plays. The recorded players' first Makrun script is
15MKR01B: they arrived at 1. The follower had arrived at 0 because its stage model took
15MKR01A..E for one stage (the name's digits); it now walks each hub's own head for
every counter value (`autoplay.hub_loads`, `resident_values`), and the counter's writer
is the dungeon's prison sequence (08CKD01 at 0x1ae5, after the monster fight - the fight
the sword cannot win: 4 damage per hit against 500 HP, the sword skills 30-45; god mode
had been healing the monster too, since its stat block sits right after the party's).

Past Makrun's arrival (2026-09-26, runs 44-47): the town's counter goes 1 -> 2 -> 3 on a
sub-counter, var 0x42, that 15MKR01B's region entries and talks take from 0 to 4; the
hub's talk handler at 0x51c then wants item 0x69 (`a8 007f #0069`, Palman's failed
medicine) before it counts 5, 15MKR01B's region entry at 0x1906 plays 15MKR02C at 5 and
writes 0x91 := 2, and the hub writes 0x91 := 3 at 6. The item is Drl village's scene
17DRL01B: in the village's region 5 the stage script's per-frame entry (17DRL01 entry 6,
0x1f8c) starts Palman's arrival when the party's raw object x equals 224 (screen x 184;
`85 var=obj.w 007f 04` reads the object table's x, anchor included). The straight walk
from the entrance is blocked by a villager, so the follower never crossed it; the state
fo_drl_done2 was made by writing that x. The scene's choice menus (which of the two
drinks the poison, YES/NO) stay drawn while its pages go on beneath, so a reader that
keys on the cursor glyph sees forty menus - press on. Two other lessons from those runs:
the "hang" detector wants a silent interpreter (no fetches at 0x33bb for half a second),
since a party wedged in a wall after a failed walk looks frozen otherwise; and a no-clip
walk through scenery can make the game quit to DOS (six zones of Mki's 1601_3de3), so a
walk that ends at the DOS prompt is retried with walls respected.

### The road to the capital, as far as it goes (2026-09-24)

What the scripts and the recorded runs say about getting past the early game, for
whoever picks this up:

* no world-map exit leads to the capital (blk1, teleport destination 6). Destination 6
  is written by the rest house's hub (05SKS.SCN at 0x227) and by the castle, so the
  capital is entered from the rest house; the rest house (destination 5) is world-map
  step zone 4, the gate at (100..114, 368..377) on the west edge, and the recorded
  players walked Albein -> capital in six minutes with no text in between;
* walking up into that gate loads the sprite `heisi` (a soldier appears in the gateway);
  from the old states the game then looped forever on a garbage sprite size (the stale
  directory cache above), which is why the gate looked like a wall for a day. From a
  fresh session it opens: the rest house (sks1, three people, two doors into sks2) has
  step exits 0/1 back to the world map, 4 to the ruins (ckd, 08CKD) and 5 to the
  capital (blk1, resource `dog`, five people live on arrival). `fo_dog_from_sks5` is
  that arrival, at story counters 0x84 = 1, 0x85 = 2. From the capital, step zone 24
  is the castle (csl1, then csl2 inside): the photographer walked in on its own and
  took 07CSL01A's speakers there;
* a talk-stub address is only exact for a record of the stage script resident in RAM
  (the same address in 05SKS02 and 07CSL01A named the wrong person once), so the
  photographer checks the script slots' first 32 bytes against the original scripts.
* **which scene script a person's talk opens is written in the stub itself**: its first
  instruction is `04 <load block>`, the call that swaps that scene script in before `b0`
  runs the entry (the capital: `04 9a 28` is 06BLK01B's load block). tools/npcs.py used
  to guess this from the last `04` switch before the object, which missed everyone the
  town builds before its first switch and all of Sohagi; reading the stub found 790
  people over 95 scene scripts (was 619 over 78), and the photographer resolves a live
  person the same way from the resident scripts, so no record is needed at all.
* the tester's page index (kuro_test.Script) read the workbook by column position and
  stopped matching anything when the context columns went in front of the text; it
  reads by header now, and the autoplayer matches Japanese pages through it, which is
  what lets it follow the recorded route on the original disk.

Coverage on 2026-09-25: 130 pictures on 128 scenes (6 at the start); 301 scenes still
show only a sprite number, 87 in Albein's later visits, 90 in the capital's later
stages, 68 in the castle's - the same towns later in the story.
* world-map exits and what they set: 0 Tanis (a scene, `ds_03`, until later), 1 and 18
  the Stage area, 2 Albein, 3 the manor, 4 the rest house, 5 the Old Book Cave, 12 and
  19 scenes (`mk12`, `gakusha2`), 20-24 fixed encounters, the rest the later areas'
  hubs, which bounce the player until their stage. The whole leg from the manor to the
  capital is scripted in tools/npc_photos.py's neighbour, the fresh_run scripts kept in
  this session's notes: manor -> world map -> Stage area (exit 1) -> pass battle -> world
  map east (exit 2) -> gate (zone 4) -> rest house -> exit 5. Variable 3 is the destination,
  variable 5 the side entered from, variable 1 the map left, variable 2 the map now.

| area | sprite | count | stands at | says | picture |
|---|---|---|---|---|---|
| 02OLB | 2 | 9 | 111,104 193,131 203,78 111,104 | その様子だと、お客さんも港で足留めをくったね？言わなくてもわかるよ、こちとら | ![](sprite_img/02OLB_2.png) |
| 02OLB | 3 | 20 | 143,65 99,35 93,106 217,89 | 看板を読んだか？　まいったぜ  | ![](sprite_img/02OLB_3.png) |
| 02OLB | 4 | 13 | 105,113 115,104 217,78 105,113 | 貴族の屋敷？　町を出て、南にしばらく歩くと見えてくるわよ  | ![](sprite_img/02OLB_4.png) |
| 02OLB | 5 | 11 | 73,105 89,114 73,105 89,114 | ほう、これはめずらしい！　黒い髪に、黒い瞳とはのう・・・この歳まで生きて、初 | ![](sprite_img/02OLB_5.png) |
| 02OLB | 6 | 19 | 143,55 85,106 111,118 126,173 | 船が出せないんじゃ、仕事にならねーよ  | ![](sprite_img/02OLB_6.png) |
| 02OLB | 7 | 9 | 91,43 101,113 91,43 101,113 | あら？　どちら様？  | ![](sprite_img/02OLB_7.png) |
| 02OLB | 8 | 9 | 157,121 157,121 58,53 105,108 | あの奇妙な嵐は何だったんでしょう？私にはとても、ただの自然現象とは思えません | ![](sprite_img/02OLB_8.png) |
| 02OLB | 9 | 6 | 118,66 105,108 118,66 105,108 | こら！　あっちへ行け！  | ![](sprite_img/02OLB_9.png) |
| 02OLB | 10 | 4 | 81,79 81,79 81,79 81,79 | ねえ、ねえ、その髪の毛、病気？  | ![](sprite_img/02OLB_10.png) |
| 02OLB | 11 | 8 | 83,79 83,79 83,79 83,79 | ぐるるるるる・・・  | ![](sprite_img/02OLB_11.png) |
| 02OLB | 12 | 14 | 157,40 91,238 191,209 203,135 | シノブ  | ![](sprite_img/02OLB_12.png) |
| 03YSK | 2 | 21 | 0,247 173,147 179,149 149,247 | 何の用だ？  |  |
| 03YSK | 3 | 16 | 176,143 176,143 136,122 155,121 | 警備隊長  |  |
| 03YSK | 4 | 4 | 58,100 58,100 148,104 177,105 | この国では、貴族の子弟は皆、学問の道を目指すのが習わしです。え？　剣ですって |  |
| 03YSK | 5 | 7 | 148,88 226,88 148,88 226,88 | あの《赤いエニス》の一味が、地下の宝石を狙ってるんですって・・・なんだかワク |  |
| 03YSK | 6 | 5 | 264,246 264,246 153,89 161,89 | わしは、この国の領主ユーバウム公爵の側近を勤める者だ。地下の《緑星晶》は、公 |  |
| 03YSK | 7 | 2 | 116,148 245,259 | 男Ｚｚｚｚ・・・  |  |
| 03YSK | 8 | 1 | 145,67 | メルフィナ  |  |
| 03YSK | 9 | 1 | 132,191 | メルフィナ様、どこで遊んでらっしゃるのかしら？  |  |
| 03YSK | 10 | 10 | 172,209 28,253 86,253 72,210 | まじめに下働きをしてたおかげで、ぼくも人夫として  |  |
| 03YSK | 11 | 6 | 243,250 249,254 243,259 237,254 | ゲンハス  |  |
| 03YSK | 12 | 1 | 264,247 | ユーバウム  |  |
| 04OLD | 2 | 7 | 248,45 60,120 65,120 60,120 | 学者ここは魔物だらけだ。キミみたいな女の子がひとりじゃあ・・・  |  |
| 04OLD | 3 | 2 | 143,79 127,47 | おっと、悪いな、ここのお宝はおれが頂いたぜ  |  |
| 05SKS | 2 | 27 | 101,65 103,65 102,45 113,96 | この先はマッカロックの村へ続く道だ  |  |
| 05SKS | 3 | 10 | 168,98 168,98 168,98 54,65 | こんなとこで、足留めを食わされるとは・・・  |  |
| 05SKS | 4 | 8 | 171,98 171,98 171,98 150,100 | わたしたちはオールバインに、遺跡の調査に行かねば  |  |
| 05SKS | 5 | 9 | 170,101 136,108 160,101 76,52 | この休憩所には、いろんな人が立ち寄るから面白いで  |  |
| 05SKS | 6 | 4 | 116,114 171,98 112,98 112,98 | ちきしょーめ！  |  |
| 05SKS | 7 | 3 | 110,106 105,65 98,65 | ここを追い返されたら、もう行く当てがありません。  |  |
| 05SKS | 8 | 2 | 108,108 92,45 | バルクルーサなら、魔物も襲ってこないだろうと思っ  |  |
| 06BLK | 2 | 14 | 72,54 113,256 105,260 113,256 | 石段を登るとバルクルーサ城だ。  | ![](sprite_img/06BLK_2.png) |
| 06BLK | 3 | 1 | 95,257 | 後ろにいるんで、小さな声で話しますが・・・大きな顔してのさばってるのは、まさ | ![](sprite_img/06BLK_3.png) |
| 06BLK | 4 | 8 | 30,108 181,193 77,205 105,260 | この先にある家は、みんな借家さ。  | ![](sprite_img/06BLK_4.png) |
| 06BLK | 5 | 4 | 182,257 101,59 245,209 101,59 | ねえ、早くお買い物に行こーよぉ！  | ![](sprite_img/06BLK_5.png) |
| 06BLK | 6 | 6 | 186,190 83,259 179,259 95,59 | ・・・どうして、あんなムダなことを！  | ![](sprite_img/06BLK_6.png) |
| 06BLK | 7 | 5 | 175,261 95,257 95,257 66,201 | 私たちはドラールの村から来ました。  | ![](sprite_img/06BLK_7.png) |
| 06BLK | 8 | 2 | 83,259 83,259 | この前、ここで見かけた異国の女・・・  | ![](sprite_img/06BLK_8.png) |
| 06BLK | 10 | 13 | 182,257 191,193 138,194 186,28 | 街へたどり着いたのはいいんじゃが・・・  | ![](sprite_img/06BLK_10.png) |
| 06BLK | 11 | 4 | 278,172 278,172 178,265 83,259 | あら？　その髪の毛、まさかあなた・・・  | ![](sprite_img/06BLK_11.png) |
| 06BLK | 12 | 3 | 238,222 240,169 240,169 | ここから出ると、兵隊がうるさいぞ  | ![](sprite_img/06BLK_12.png) |
| 07CSL | 2 | 23 | 93,161 85,129 53,124 165,75 | 立ち去れ！  |  |
| 07CSL | 3 | 7 | 61,80 204,67 47,123 164,45 | 中庭は気が休まるのう・・・  |  |
| 07CSL | 4 | 9 | 101,92 171,27 169,27 159,27 | 次元牢は、そこへ入りし者をこの世ならざる場所へと  |  |
| 07CSL | 5 | 6 | 263,222 273,31 141,145 25,233 | 警備隊長  |  |
| 07CSL | 6 | 5 | 215,210 228,212 38,185 61,80 | ここは待遇がいいからな、少しぐらい嫌な思いしたっ  |  |
| 07CSL | 7 | 4 | 209,219 204,67 161,29 161,29 | 我々は、この城の下働きをやっております  |  |
| 07CSL | 8 | 11 | 272,179 270,165 101,92 164,26 | あら？　素敵な髪ですわね？  |  |
| 07CSL | 9 | 5 | 165,215 173,220 156,79 146,67 | マルダー様ったら、君の透き通った声が僕の心にに恋  |  |
| 07CSL | 10 | 3 | 173,37 155,37 33,104 | ・・・・・・・・・  |  |
| 07CSL | 11 | 4 | 161,29 173,220 158,70 142,66 | マルダー  |  |
| 07CSL | 12 | 2 | 156,79 146,67 | リールから例の少女のことを？  |  |
| 10TNI | 2 | 1 | 149,261 | 婆さんがひとりで行くって言うから、心配でついてき  |  |
| 10TNI | 3 | 1 | 151,267 | おお！　あんたらは夢に出てきた人たちじゃ！  |  |
| 14YMM | 3 | 1 | 49,72 | クゥ～ン、クゥ～ン  |  |
| 14YMM | 4 | 1 | 176,201 | お前たち、城から来たのか？  |  |
| 14YMM | 5 | 1 | 180,211 | ・・・ま、魔物のせいで、峠を越えられないんです。  |  |
| 15MKR | 2 | 13 | 89,143 92,143 94,143 74,100 | 町へ入ることは許さん！  |  |
| 15MKR | 3 | 6 | 96,63 44,200 141,202 44,200 | 遺跡って何もないのね。  |  |
| 15MKR | 4 | 2 | 113,126 99,67 | 橋の上のゴーレムがいなくなって助かったわ  |  |
| 15MKR | 5 | 6 | 57,78 209,164 231,102 61,105 | ここから温泉が覗けるかと思ったけど・・・  |  |
| 15MKR | 6 | 6 | 113,126 99,64 61,97 96,64 | 町に駐留してた軍は北へ去って行きました  |  |
| 15MKR | 7 | 4 | 61,105 35,165 35,163 140,94 | あ～いいお湯じゃ、極楽、極楽。  |  |
| 15MKR | 8 | 6 | 259,167 253,102 81,52 73,33 | ドラールのパルマンか。  |  |
| 15MKR | 9 | 12 | 251,161 84,58 95,53 81,52 | よろしくお願いします  |  |
| 15MKR | 10 | 12 | 41,165 41,163 256,167 143,99 | しかし、なんじゃの・・・  |  |
| 15MKR | 11 | 6 | 110,84 257,98 41,165 41,163 | カイエスなんだ？　彫像か？  |  |
| 15MKR | 12 | 4 | 143,99 257,98 83,36 135,99 | 町長  |  |
| 16MKI | 2 | 6 | 205,69 205,69 279,43 214,74 | すまんが、その看板を読んでくれんか？  |  |
| 16MKI | 3 | 7 | 221,74 221,74 221,74 279,43 | 一度、遺跡というのを見たくて、この町に来ました  |  |
| 16MKI | 4 | 2 | 253,53 262,57 | おおー！　これが遺跡か！  |  |
| 16MKI | 5 | 2 | 270,40 252,55 | ありがたや、ありがたや・・・  |  |
| 16MKI | 6 | 1 | 255,35 | なんか落ちてないかな・・・  |  |
| 16MKI | 7 | 1 | 252,37 | お姉ちゃん、あっち行こーよぉ！  |  |
| 17DRL | 2 | 3 | 261,61 106,221 80,51 | パルマンには感謝しているけど、薬が効きすぎるから  |  |
| 17DRL | 3 | 3 | 263,33 125,224 125,224 | あいつは若者らしく無茶で、魔物と闘っては負けてく  |  |
| 17DRL | 4 | 1 | 257,31 | パルマンさんは研究一筋の人だからねェ。  |  |
| 17DRL | 6 | 1 | 264,59 | いててて・・・大丈夫だよ、姉さん。  |  |
| 17DRL | 7 | 2 | 93,147 121,228 | 防具を買っていきなされ。役立つぞい  |  |
| 17DRL | 11 | 2 | 113,145 121,220 | 見ろ、おれの鍛えあげたこの体。  |  |
| 19IRE | 2 | 4 | 86,56 195,68 122,99 176,165 | 旅人か？  |  |
| 19IRE | 3 | 7 | 166,63 137,91 187,68 120,66 | 北西にある洞窟は鉱山の名残です。  |  |
| 19IRE | 4 | 3 | 131,99 177,68 100,147 | 入り江にヨソ者は入れんことになっとる。  |  |
| 19IRE | 5 | 1 | 108,66 | わたしたちは南の入り江で漁をして暮らしています  |  |
| 19IRE | 6 | 1 | 98,87 | ほひっ・・・ほっひっひっひっ・・・  |  |
| 19IRE | 7 | 2 | 98,87 97,67 | ふが・・・ふが・・・  |  |
| 19IRE | 8 | 1 | 97,67 | そろそろ、お食事のしたくしなくっちゃ。  |  |
| 19IRE | 9 | 1 | 181,168 | その扉は開かんぞい！  |  |
| 19IRE | 10 | 1 | 163,151 | 黒竜？　はっはっは、そんなものはアンタ、つまらん  |  |
| 20NNP | 2 | 7 | 234,146 154,88 140,74 164,67 | グラウベン  |  |
| 23SOH | 6 | 1 | 191,43 | いや、大丈夫・・・  |  |
| 23SOH | 8 | 1 | 194,43 | ・・・・・・・・・  |  |
| 23SOH | 11 | 1 | 234,125 | 海辺の村には、剣造りの名人が住んでる・・・  |  |
| 24UMB | 2 | 18 | 79,65 71,107 194,181 79,65 | ・・・何者だ？  |  |
| 24UMB | 3 | 3 | 112,64 112,64 105,58 | あんたがた、どこから来たんだね！  |  |
| 24UMB | 4 | 5 | 75,93 82,181 75,93 82,181 | 何しに来たの？  |  |
| 24UMB | 5 | 2 | 90,174 90,174 | サトーの奴は、風邪ひいてる時に魔物になったせいで  |  |
| 24UMB | 6 | 3 | 80,52 80,52 83,175 | ・・・？　誰？  |  |
| 24UMB | 7 | 3 | 69,31 69,31 85,175 | サトー  |  |
| 24UMB | 9 | 2 | 219,80 219,80 | グリンウルド  |  |
| 24UMB | 10 | 2 | 207,80 207,80 | あんたら、移民どもとは違う臭いがする・・・  |  |
| 24UMB | 11 | 4 | 210,85 67,50 210,85 67,50 | 辺境の地酒はいかが？　毒なんか入ってないわよ  |  |
| 24UMB | 12 | 2 | 75,50 75,50 | 移民どもめ、黒竜に食われてしまえばいいわ！  |  |
| 25TOU | 4 | 1 | 57,35 |  |  |
| 25TOU | 5 | 1 | 94,103 |  |  |
| 25TOU | 6 | 1 | 160,69 |  |  |
| 25TOU | 7 | 1 | 134,31 |  |  |
| 25TOU | 8 | 3 | 262,161 114,253 226,191 |  |  |
| 25TOU | 9 | 1 | 98,180 |  |  |
| 25TOU | 11 | 1 | 107,153 |  |  |
| 25TOU | 13 | 7 | 167,101 161,101 119,181 115,99 |  |  |
| 26KKR | 2 | 3 | 104,120 116,120 128,120 | 軍が調査中だ！　関係者以外は入れんぞ！  |  |
| 27KKI | 2 | 4 | 43,173 63,169 55,233 55,217 | し、知らん！　おれたちは何も知らん！  |  |
| 27KKI | 10 | 1 | 45,149 | やめろ！　そいつに話しかけるな！  |  |
