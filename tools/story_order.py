"""Put every dump row in story order - or as close as the scripts can say.

The dump is in file order: files alphabetically, rows by offset. Inside a conversation that
is already right (a script block is contiguous), but across scenes it is not: `17DRL04`
plays before `17DRL01`, the `15MKR01x` and `02x` scenes interleave, and Port Albein is
revisited between other areas. The translator reads it as a jumble.

Three things in the scripts fix the order, all read off the engine rather than guessed:

**Story counters.** `20 <var> 00 <n> 00` sets variable `var` to `n` (BD.BIN handler 1ded),
and some variables only count up as the story advances - 0x84 is set to 1 in 03YSK01A, 2 in
11STG01, 3 in 03YSK01B ... 8 in 03YSK70. The test that separates a clock from an ordinary
variable is that **each value is set by exactly one script**: 0x91 is set to 1 by three
scripts at three different times, so its values say nothing. Scripts that set several clocks
at once (07CSL02 sets 0x84, 0x85, 0x86 and 0x87 together) tie them into one timeline, which
a topological sort turns into a sequence. The eleven clocks agree with each other - there is
no cycle - which is the main reason to trust them.

**Area hubs.** Each area's hub script (`02OLB.SCN`, ...) is a switch on one variable:
`10 <var> 00 <n> 00 <next case>` then `39 00 00 <slot> 02 "<script>"` - load these scene
scripts while the variable is n (opcode 10 jumps to the next case if var != n, handler 1d62).
A scene loaded at `var == n` plays after the moment that variable became n; where the
variable is the area's own floor number (0x7e, which five hubs reuse), it orders the scenes
within the area instead.

**Where the player can first get to an area.** A map change is `20 <var 3> <destination>`
(tools/teleport.py), and the destination number is the area number, so the scripts say which
area leads where: 05SKS sends the player to 6 (the capital), 08CKD to 9 (the mine), 27KKI to
28. An area the clock does not reach is placed just after the earliest placed script that can
send the player there, repeatedly, so chains resolve. Two cautions, both learned the hard way:
the world map is excluded, because it writes nearly every destination and what gates each one
is the 0x80 bit in its zone table (engine_notes.md) rather than the script; and a *hub* write
is only "after everything else known in that area", since a hub runs on every visit and its
write may sit in a late branch - taking those at face value put the ending in the middle of
the game.

**The counters as one network.** Each of those is one area's list; read together they are
38 statements of "this block runs before that one", all of them crossing areas, with no
cycle between them. The longest path through that network is a **rank** - eleven moments
deep - and it, not the area order, decides which of the game's moments a scene belongs to
(`story_rank`, docs/engine_notes.md). Rows sort by `(rank, place)`: the place still orders
the scenes inside one moment, which is what it is good at. Where the network says nothing -
City McCulloch, Dorral Village and Ruins McCulloch, all reached by a quest no counter
records - the rank comes from where the area appears in the recorded playthrough instead,
and says so.

Every script gets a place from those three, in that order of confidence. What none of them
reaches - 12MRS/13SLP and 21KTI/22MZI, which only lead to each other - goes after everything
placed, in area-number order, and says so: area numbers do not follow the story (27KKI
provably comes before 25TOU), and story flags are shared between areas in both directions,
so neither can place them. Rows then sort by (script's place, file order), and the `basis`
says which rule placed each one, so a proven order can be told from a best guess.

What this does not order: optional chatter. The townspeople of one scene can be talked to
in any sequence, so inside a script the order stays the file's.

**The one rule, and its test.** All of the above is heuristic. What the sheet has to keep
is that no conversation sits above anything it depends on, and that is checkable:
`dependencies` lists every need (loaded at a stage, gated on a counter or a flag, a
script's own progress counter, a milestone's predecessor) with the blocks that satisfy
it, `causal_order` is a topological sort that keeps the given order wherever the needs
allow, and tools/check_story_order.py reads a finished workbook back against the same
list. translator_context runs the sort over its rows as the last step and prints what it
had to move - the measure of what the heuristics still get wrong.

    python tools/story_order.py             # the script sequence, with how each was placed
"""
import collections
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
ORIG = os.path.join(HERE, 'original', 'decompressed')

SET = re.compile(rb'\x20([\x00-\xff])\x00([\x00-\xff])\x00', re.S)
CASE = re.compile(rb'[\x10\x18]([\x00-\xff])\x00([\x00-\xff])\x00..', re.S)
LOAD = re.compile(rb'\x39\x00\x00[\x00\x18\x3d]\x02([0-9a-z]{3,10})\x00')
SAME_MOMENT = 0x14      # writes this close are one instruction run (`20 84 00 04 00 20 85 00 03 00`)
MAX_STAGE = 20          # a "counter" set to 96 is something else (0x7e is reused freely)
DESTINATION = re.compile(re.escape(b'\x20\x03\x00') + rb'(..)', re.S)   # `20 <var 3> <area>`
WORLD_MAP = '01FLD'


def _scripts():
    return {os.path.basename(p)[:-4]: open(p, 'rb').read()
            for p in glob.glob(os.path.join(ORIG, '*.SCN'))}


CASE_REGION = re.compile(rb'[\x10\x18]([\x00-\xff])\x00([\x00-\xff])\x00(..)', re.S)
JUMP = re.compile(rb'\x09(..)', re.S)


def hub_cases(data, base=0):
    """[(var, value, script)] for a hub's stage switch.

    `10 <var> 00 <n> 00 <next>` jumps to <next> unless var == n (`18` unless var <= n), so
    the code between the case and <next> is stage n's. The scripts it loads are either
    right there - `39 00 00 <slot> 02 "<name>"`, several back to back - or in a block it
    jumps to. Hubs that are map scripts (17DRL, 06BLK, ...) pick scenes by trigger zone,
    i.e. by where the player is, and have no such switch: their scenes stay in file order.

    Every hub switches on a scratch copy (`21 7e 00 89 00`: var 0x7e := var 0x89), so the
    variable in the case is not the one that means anything - `resolve_copy` gives the real
    one back. That mattered: the castle's 28 scripts all read as "var 0x7e", the floor
    number five hubs reuse, and sat at one anchor.
    """
    loads = {m.start(): (m.end(), m.group(1).decode().upper()) for m in LOAD.finditer(data)}
    out, seen = [], set()

    def add(var, val, name):
        if (var, val, name) not in seen:
            seen.add((var, val, name))
            out.append((var, val, name))
    for m in CASE_REGION.finditer(data):
        var, val = resolve_copy(data, m.start(), m.group(1)[0]), m.group(2)[0]
        at = m.end()
        while at in loads:                   # loads right after the case
            at, name = loads[at]
            add(var, val, name)
        nxt = int.from_bytes(m.group(3), 'little') - base
        if not (m.end() < nxt <= len(data)) or nxt - m.end() > 0x80:
            continue
        for at in sorted(loads):             # loads inside the case's own code
            if m.end() <= at < nxt:
                add(var, val, loads[at][1])
        for j in JUMP.finditer(data, m.end(), nxt):   # loads in a block it jumps to
            t = int.from_bytes(j.group(1), 'little') - base
            for at in sorted(loads):
                if 0 <= t <= at < t + 0x30:
                    add(var, val, loads[at][1])
    for var, val, name in table_cases(data, base):
        add(var, val, name)
    return out


SWITCH = re.compile(rb'\x0b(..)\x00(..)([\x00-\xff])', re.S)   # 0b <var> <default> <count>
COPY = re.compile(rb'\x21(..)(..)', re.S)                      # var[<w0>] := var[<w1>] (BD.BIN 1df5)
MAX_TABLE = 24
COPY_REACH = 0x200      # how far back a hub's `var := var` copy can sit from its switch


def resolve_copy(data, at, var, reach=COPY_REACH):
    """The variable a hub's switch really reads.

    A hub never switches on its counter directly: it copies it into a scratch variable
    first (`21 7e 00 89 00` then `2c 7e 00 ff 00` - var 0x7e := var 0x89, masked to a
    byte) and switches on that. 0x7e and 0x7f are reused by every hub, so taking them at
    face value merges unrelated areas; the copy just before the switch names the real one.
    The counters turn out to be one per area - 0x82 + the area's number: 06BLK 0x88,
    07CSL 0x89, 08CKD 0x8a, ... 17DRL 0x93, 23SOH 0x99, 26KKR 0x9c, 27KKI 0x9d.
    """
    for _chain in range(3):                  # 01FLD copies twice: 0x7f := 0x83, 0x7e := 0x7f
        for c in COPY.finditer(data, max(0, at - reach), at):
            if int.from_bytes(c.group(1), 'little') == var:
                src = int.from_bytes(c.group(2), 'little')
                if src < 0x100:
                    var = src
    return var


AREA_STAGE = 0x82       # area N's stage counter is variable 0x82 + N (see stage_var)

#   Where each (counter, value) falls in the story, filled by script_places. A scene whose
#   *caller* tests the counter can then be placed by the test rather than by the script it
#   sits in: 02OLB01 is loaded both before and after the manor, and the block where Innes
#   admits the theft is behind `10 84 00 00 00` - Albein's counter must have moved on - so
#   it belongs after the manor, not with the rest of its file.
STAGE_AT = {}


def stage_place(var, value):
    """Where a counter reaching `value` falls, or None when that says nothing.

    None for a value at or below the counter's lowest known stage: "the counter is at
    least 0" is true from the start and would otherwise drag a scene forward to the area's
    first visit. Needs script_places() to have run.
    """
    known = {n: p for (v, n), p in STAGE_AT.items() if v == var}
    if not known or value <= min(known):
        return None
    return min(p for n, p in known.items() if n >= value) if any(
        n >= value for n in known) else None


def stage_var(name):
    """The variable that counts an area's stages, or None for a script with no area.

    Every hub switches on 0x82 + its area number, with no exception in the 30 areas:
    02OLB 0x84, 03YSK 0x85, 06BLK 0x88, 07CSL 0x89, 08CKD 0x8a, 09HIK 0x8b, 10TNI 0x8c,
    11STG 0x8d, 15MKR 0x91, 17DRL 0x93, 23SOH 0x99, 26KKR 0x9c, 27KKI 0x9d. Some of them
    (0x84, 0x88, 0x93) also pass the whole-game clock test in `counters`; the rest count
    only within their area, and what dates *those* is who advances them - `20 89 00 03 00`
    in 27KKI01 says the castle's stage 3 comes after the Kikuichi scene.
    """
    return AREA_STAGE + int(name[:2]) if name[:2].isdigit() else None


def table_cases(data, base=0):
    """[(var, value, script)] for a hub that picks the stage with a jump table.

    Three hubs do it that way instead of a chain of compares. Opcode 0x0b (BD.BIN handler
    0x1cf9) reads a variable, a default target and a count byte, then `count` tagged words,
    and jumps to entry[the variable's value] - so entry i is what plays while the variable
    is i, which is what `10 <var> <n> <next>` says in the hubs that use compares. Until
    this was read, the capital's 42 scripts and Dragon's Lair's all sat at one anchor.

    The switch is on a scratch copy - `21 7f 00 88 00` then `2c 7f 00 ff 00`: var 0x7f :=
    var 0x88, masked to a byte - so the copy just before the table names the real counter
    (06BLK's 0x88, 17DRL's 0x93, 23SOH's 0x99).
    """
    out = []
    for m in SWITCH.finditer(data):
        var = int.from_bytes(m.group(1), 'little')
        n = m.group(2)  # the default target, unused here
        count = m.group(3)[0]
        body = m.end()
        if not 0 < count <= MAX_TABLE or body + 3 * count > len(data) or var >= 0x100:
            continue
        entries = []
        for i in range(count):
            tag = data[body + 3 * i]
            w = int.from_bytes(data[body + 3 * i + 1:body + 3 * i + 3], 'little') - base
            if tag != 0 or not 0 < w < len(data):
                entries = []
                break
            entries.append(w)
        if not entries:
            continue
        var = resolve_copy(data, m.start(), var, 0x20)
        for val, at in enumerate(entries):
            for name in _loads_run(data, at, base):
                out.append((var, val, name))
    return out


def _loads_run(data, at, base=0):
    """The scripts a stage's own block loads: the loads that start right where it does.

    One `09 <target>` jump is followed (a block that is only a jump to the real one), and
    the walk stops at the first byte that is not another `39 ... "<name>"` - otherwise the
    scan runs on into the *next* stage's block and gives every stage the same scripts.
    """
    out = []
    for _hop in range(2):
        while at + 3 <= len(data) and data[at] == 0x04:     # `04 03 02` opens every entry
            at += 3                                          # of 06BLK's arrival table
        while True:
            m = LOAD.match(data, at)
            if not m:
                break
            out.append(m.group(1).decode().upper())
            at = m.end()
        if out or at + 3 > len(data) or data[at] != 0x09:
            break
        at = int.from_bytes(data[at + 1:at + 3], 'little') - base
        if not 0 <= at < len(data):
            break
    return out


def hub_vars(scripts):
    """-> {var: [hubs that switch on it]} (a case directly followed by a load)."""
    out = collections.defaultdict(set)
    for name, d in scripts.items():
        if re.fullmatch(r'\d\d[A-Z]+', name):
            for var, _val, _child in hub_cases(d):
                out[var].add(name)
    return out


def counters(scripts):
    """The story counters that work as a clock for the whole game: a variable whose values
    climb from 1 and where **each value is set by exactly one script**, so the value says
    when. That test is what separates them from the variables that look similar: 0x91 is
    set to 1 by three different scripts at three different times, 0x7f by six, and 0x4 is a
    general-purpose counter every area writes. A hub switching on the variable is not
    required - 0x9a (23SOH01A, 24UMB, 25TOU00C) is a clock no hub reads.
    -> {var: [(value, script, offset)]}"""
    sets = collections.defaultdict(list)
    for name, d in scripts.items():
        for m in SET.finditer(d):
            var, val = m.group(1)[0], m.group(2)[0]
            if 0 < val <= MAX_STAGE:
                sets[var].append((val, name, m.start()))
    clean = {}
    for var, writes in sets.items():
        by_val = collections.defaultdict(set)
        for val, name, _off in writes:
            by_val[val].add(name)
        # keep the run that climbs from 1 (0x95 goes 1, 2, 3, 4 - then 10 and 18, which are
        # something else written to the same variable)
        run, v = set(), 1
        while v in by_val:
            run.add(v)
            v += 1
        names = {n for val, n, _o in writes if val in run}
        if len(run) >= 3 and len(names) >= 2 and all(len(by_val[v]) == 1 for v in run):
            # (a counter written entirely inside one script - 28KDI's 0xb4, a puzzle
            # counter - orders nothing across the game, so it is not a clock)
            clean[var] = [w for w in writes if w[0] in run]
    return clean


def timeline(scripts):
    """-> (moment -> rank, [(var, value, moment)]) where a moment is (script, index)."""
    cnt = counters(scripts)
    # group each script's writes into moments
    moment_of = {}
    for var, writes in cnt.items():
        for val, name, off in writes:
            moment_of[(var, val, name, off)] = None
    by_script = collections.defaultdict(list)
    for (var, val, name, off) in moment_of:
        by_script[name].append((off, var, val))
    events = []                                       # (var, val, moment)
    for name, ws in by_script.items():
        ws.sort()
        k, last = 0, None
        for off, var, val in ws:
            if last is not None and off - last > SAME_MOMENT:
                k += 1
            last = off
            events.append((var, val, (name, k)))
    # value n before value n+1 of the same counter
    edges = collections.defaultdict(set)
    nodes = {m for _v, _n, m in events}
    for var in cnt:
        ev = sorted((val, m) for v, val, m in events if v == var)
        for (a, ma), (b, mb) in zip(ev, ev[1:]):
            if b > a and ma != mb:
                edges[ma].add(mb)
    # Kahn's algorithm; ties go to the lower area number, then the name
    indeg = collections.Counter()
    for a in edges:
        for b in edges[a]:
            indeg[b] += 1
    key = lambda m: (int(m[0][:2]) if m[0][:2].isdigit() else 99, m)
    ready = sorted((m for m in nodes if not indeg[m]), key=key)
    rank, order = {}, []
    while ready:
        m = ready.pop(0)
        rank[m] = len(order)
        order.append(m)
        for b in sorted(edges.get(m, ()), key=key):
            indeg[b] -= 1
            if not indeg[b]:
                ready.append(b)
                ready.sort(key=key)
    cyclic = nodes - set(rank)
    for m in sorted(cyclic, key=key):                 # report, then append after the rest
        rank[m] = len(order)
        order.append(m)
    return rank, events, cyclic


# What the scripts cannot prove, with the evidence. Keep this short: every entry is a
# place the decoding could not reach.
OVERRIDES = {
    # The intro (IPL = initial program load): the first thing the game shows.
    '00IPL': ('start', None, 'the intro, first thing the game shows'),
    # The world map's script, used between areas all game long.
    '01FLD': ('start', None, 'the world map, used throughout'),
    # From sqpat's recorded playthrough (docs/video_anchors.json): frames matched to dump
    # rows give the order a player actually played in, which is what the counters cannot
    # give for an area they only mention late. Each of these was read off a frame.
    #   06BLK (the capital) and 17DRL (Dragon's Lair) used to be pinned here from the video,
    #   with every one of their scripts at the one anchor. They are not any more: their hubs
    #   pick the stage with a jump table (`table_cases`), on the counters 0x88 and 0x93, so
    #   each visit is dated on its own and the video only confirms it - 06BLK01B at part 1
    #   1:10 is stage 0 (before 11STG01 sets 0x88 to 1), 17DRL01A at part 2 4:45 is stage 0
    #   (before 15MKR sets 0x93 to 1), and 06BLK04O at part 3 0:40 is stage 3 (27KKI01).
    #   Part 2 1:40 - the Isle of Forests is played right after Albein's stage 2 (02OLB02A
    #   at part 2 1:25, which is what tells the player about it). A playtest had put it at
    #   0x84 = 1, much earlier, but that only shows the autoplayer could walk in.
    '12MRS': ('after', '02OLB02A', 'seen in the playthrough right after Albein stage 2 sends the player there (part 2, 1:40)'),
    #   The Isle of Forests quest chain, from the game's own text rather than a frame:
    #   02OLB02A (Albein, stage 2) says the isle has "a cave leading to the bottom of the
    #   sea"; 12MRS says "when the Sleeping Princess awakens, the entrance opens". So the
    #   Sleeping Beauty Cave and then the seabed follow the isle. Inferred, not observed.
    '13SLP': ('after', '12MRS', 'the Isle of Forests chain: 12MRS wakes the Sleeping Princess to open the cave (in-game text)'),
    '21KTI': ('after', '13SLP', 'the Isle of Forests chain: the cave leads to the seabed (02OLB02A, in-game text)'),
    #   ... but the ruins themselves are dated by a counter: 22MZI sets the Black Dragon
    #   ruins' 0x9c to 4, after 27KKI01 sets it to 3, so its *rank* (story_rank) puts it
    #   after Kikuichi's first visit whatever this place says - and its text agrees: the
    #   party counts "three ruins left" and heads back across the lake to McCulloch.
    '22MZI': ('after', '21KTI', 'the Isle of Forests chain: the ruins below the seabed (in-game text)'),
    #   Part 3 5:50 - 23SOH01B plays after the castle's stage 4 (part 3 1:20) and long
    #   before the finale. Only reachability placed it before, which put it far too early;
    #   its stage 2 is dated by 25TOU00C and stays where the scripts put it.
    '23SOH': ('after', '07CSL04', 'seen in the playthrough after the castle stage 4 (part 3, 5:50)'),
    #   Part 4 8:03-8:57 - 29KNT is the last dungeon: 29KNT.SCN and 29KNT99B.SCN lines play
    #   right through the finale ("Shinobu drew the Black Sword and handed it to Keiuss"),
    #   and the END screen follows at 9:00.
    '29KNT': ('last', None, 'the final dungeon, seen in the playthrough (part 4, 8:03-8:57)'),
    '31END': ('after', '29KNT', 'the ending - the END screen at part 4, 9:00'),
    #   30IZM opens with the place name \xe8\x81\x96\xe6\xb0\xb4\xe3\x81\xae\xe6\xb3\x89 and a line about the great battle still to
    #   come, and the map leads from it to 29KNT: the calm scene before the last dungeon.
    '30IZM': ('before', '29KNT', 'the Fountain of Sacred Waters, just before the last dungeon (its own text, and it leads to 29KNT)'),
    #   99CMN is the common script - yes/no prompts, shop lines - used from the first menu
    #   onwards, so it belongs at the front with the other always-there text.
    '99CMN': ('start', None, 'the common script (prompts, shops), used all game long'),
    #   09HIK is reached only from the Walkreuz Underground, whose hub sends the player
    #   there; no counter, flag or frame dates it any better than that.
    '09HIK': ('after', '08CKD', 'reached only from the Walkreuz Underground (08CKD)'),
    # Shinobu wakes up at Innes's after the shipwreck - the first scene after the intro
    # (route 01: "New Game -> opening scene -> talk to Innes -> town"). The hub loads it
    # from a block reached through code the decoder cannot follow.
    '02OLB00A': ('before', '02OLB01', 'the opening scene (route 01, and its content)'),
}


def script_places(scripts=None):
    """-> {script: (place, basis)}; place is a float, lower is earlier."""
    scripts = scripts or _scripts()
    cnt = counters(scripts)
    rank, events, _cyclic = timeline(scripts)
    when = {}                                          # (var, value) -> earliest rank
    for var, val, m in events:
        when[(var, val)] = min(rank[m], when.get((var, val), rank[m]))
    places = {}
    STAGE_AT.clear()

    def put(name, p, basis):
        if name not in places or p < places[name][0]:
            places[name] = (p, basis)

    # 1. scripts that advance a story counter: at that moment
    for var, val, m in events:
        put(m[0], float(rank[m]), 'advances story counter %#x to %d' % (var, val))
    # 2. scenes a hub loads for a stage of a story counter: just after that stage began
    hubs = {n: hub_cases(d) for n, d in scripts.items() if re.fullmatch(r'\d\d[A-Z]+', n)}
    local = []
    for hub, cases in hubs.items():
        for i, (var, val, child) in enumerate(cases):
            if var not in cnt:
                local.append((hub, i, var, val, child))
                continue
            start = when.get((var, val))
            if start is None:
                later = [r for (v, n), r in when.items() if v == var and n > val]
                if not later:
                    continue
                start = min(later) - 1
            put(child, start + 0.5 + i / 1000.0, '%s loads it at stage %d (var %#x)' % (hub, val, var))
            STAGE_AT.setdefault((var, val), start + 0.5)
    # 3. every area gets an anchor: just before the first scene the clock places in it.
    #    A hub's own counter writes do not count - a hub runs on every visit, so a write in
    #    one of its late branches (06BLK's `0x87 := 7`) says nothing about the first visit.
    area = lambda n: n[:5] if n[:2].isdigit() else n

    def anchor_areas():
        """-> (area -> anchor, area -> (when, the script that leads there))"""
        first = {}
        for n, (p, _b) in places.items():
            if n not in hubs:
                first[area(n)] = min(p, first.get(area(n), p))
        anchors = {a: p - 0.1 for a, p in first.items()}
        #    ... but if the only thing the clock places in an area is its hub, use that rather
        #    than nothing (18KSK and 24UMB are a single script that is its own hub).
        hub_only = {}
        for n, (p, _b) in places.items():
            if n in hubs and area(n) not in anchors:
                hub_only[area(n)] = min(p, hub_only.get(area(n), p))
        anchors.update({a: p - 0.1 for a, p in hub_only.items()})

        #    Then: an area no counter dates, but whose text was seen playing in a recorded
    #    playtest, is placed by the counters that state had (tools/seen_when.py writes
    #    docs/playtest_clocks.json; 36 lines that only 12MRS.SCN has played in auto_run14
    #    with 0x84 = 1 and every other counter still 0).
        observed = {}
        try:
            with open(os.path.join(HERE, 'docs', 'playtest_clocks.json'), encoding='utf-8') as fh:
                import json
                watched = json.load(fh)
        except OSError:
            watched = {}
        for a, info in sorted(watched.items()):
            at = [when[(int(v, 16), n)] for v, n in info['clocks'].items()
                  if (int(v, 16), n) in when]
            if not at:
                continue
            # Only for an area the counters do not date at all. A playtest shows when an
            # area is *reachable*, which is not the same as where its content belongs: the
            # tower plays at 0x84 = 2 in auto_run25, but 25TOU00C is what sets 0x84 to 6, so
            # the counters put its scenes later and are the better guide for reading order.
            if a not in anchors:
                anchors[a] = max(at) + 0.3
                observed[a] = info

    #    Then: an area the clock does not reach is placed where the player first gets to it.
        #    A map change is `20 <var 3> <destination>` (tools/teleport.py), and the destination
        #    number is the area number, so the scripts say which area leads where - 05SKS sends
        #    the player to 6 (the capital), 08CKD to 9 (the mine), 27KKI to 28. An area is
        #    anchored just after the earliest placed script that can send the player there, and
        #    that repeats so chains resolve (07CSL -> 08CKD -> 09HIK).
        #    The world map is left out on purpose: it writes nearly every destination, and what
        #    gates each one is the 0x80 bit in its zone table (engine_notes.md), not the script,
        #    so counting it would make every area reachable from the start.
        areas = {area(n) for n in scripts}
        leads_to = collections.defaultdict(list)
        for name, d in scripts.items():
            if name == WORLD_MAP:
                continue
            for m in DESTINATION.finditer(d):
                n = int.from_bytes(m.group(1), 'little')
                dest = next((a for a in areas if a[:2].isdigit() and int(a[:2]) == n), None)
                if dest and dest != area(name):
                    leads_to[dest].append(name)
        #    A hub is not evidence of *when*: it runs on every visit, so its write may be in a
        #    late branch (27KKI sends the player to 28KDI, but that dragged the ending into the
        #    middle of the game). From a hub, the most that can be said is "after everything
        #    else known in that area".
        def writer_time(w):
            if w in hubs:
                same = [p for n, (p, _b) in places.items() if area(n) == area(w)]
                return max(same) if same else float('inf')
            return places[w][0] if w in places else float('inf')

        clock_anchor, best_from = dict(anchors), {}
        for _ in range(len(areas)):
            changed = False
            for dest, froms in leads_to.items():
                soonest, who = min((writer_time(w), w) for w in froms)
                if soonest < float('inf') and (dest not in best_from or soonest < best_from[dest][0]):
                    best_from[dest] = (soonest, who)
                    changed = True
            # an area starts at whichever is earlier: what the clock places in it, or the first
            # time the player can get there
            for dest, (soonest, _who) in best_from.items():
                if dest not in clock_anchor or soonest + 0.2 < clock_anchor[dest]:
                    anchors[dest] = soonest + 0.2
            if not changed:
                break
        reached = {d: v for d, v in best_from.items() if anchors.get(d) == v[0] + 0.2}

        return anchors, {d: v for d, v in best_from.items()
                         if anchors.get(d) == v[0] + 0.2}, observed

    areas = {area(n) for n in scripts}
    anchors, reached, observed = anchor_areas()
    #    ... and scenes its hub loads by the area's own floor/stage number go in that order
    def place_local(anchors, reached, unknown, observed):
        for hub, i, var, val, child in local:
            a = area(hub)
            if a not in anchors:
                continue
            note = (' - where the area falls in the story is unknown' if a in unknown else
                    ' - seen playing in %s' % observed[a]['run'] if a in observed else
                    ' - the area is first reachable from %s' % reached[a][1] if a in reached else '')
            p = anchors[a] + 0.01 * val + i / 10000.0
            # Never over a placement by the clock (02OLB's `var 0x1 == 1` case also loads
            # 02OLB01A, and would have moved it before the opening) - except a script that
            # advances the clock in its own area, whose scene starts before that write.
            if child not in places or (area(child) == a and places[child][1].startswith('advances')):
                places[child] = (p, '%s loads it at its own stage %d (var %#x)%s'
                                 % (hub, val, var, note))

    # 3b. an area's own stage counter, dated by whoever advances it from outside the area.
    #     A hub whose counter is not a whole-game clock still orders its own visits, and
    #     `20 89 00 03 00` in 27KKI01 says when stage 3 of the castle begins. Writes from
    #     inside the area say nothing (all eight 07CSLnn set 0x89 back to 1) and the world
    #     map writes nearly everything, so neither counts. Stages an outside script does not
    #     date keep the area's order: each one starts no earlier than the stage before it.
    writes = collections.defaultdict(list)
    for name, d in scripts.items():
        for m in SET.finditer(d):
            writes[(m.group(1)[0], m.group(2)[0])].append(name)

    def place_stages():
        by_hub = collections.defaultdict(dict)
        for hub, i, var, val, child in local:
            if var == stage_var(hub):
                by_hub[hub].setdefault(val, []).append((i, child))
        for hub, stages in by_hub.items():
            a = area(hub)
            floor = anchors.get(a)
            if floor is None:
                continue
            for val in sorted(stages):
                # stage 0 is the state the game starts in, so a write of 0 is a *reset*
                # (17DRL03 sets McCulloch's 0x91 back to 0) and says nothing about when
                # the first visit happens - only values that count up do.
                outside = [w for w in (writes.get((stage_var(hub), val), []) if val else [])
                           if area(w) != a and w != WORLD_MAP and w in places]
                dated = min((places[w][0], w) for w in outside) if outside else None
                p = max(floor + 0.001, dated[0] + 0.05) if dated else floor + 0.01 * val
                STAGE_AT.setdefault((stage_var(hub), val), p)
                for i, child in sorted(stages[val]):
                    q = p + i / 10000.0
                    if child in places and not places[child][1].startswith(
                            ('advances', 'loaded by %s' % hub)) and 'stage' not in places[child][1]:
                        continue                # a clock placed it; that is better evidence
                    places[child] = (q, '%s loads it at its stage %d (var %#x)%s'
                                     % (hub, val, stage_var(hub),
                                        ', which %s starts' % dated[1] if dated else ''))
                floor = max(floor, p)

    # 4. scripts loaded by a placed script (a base script loading its scenes): right after it
    def place_loaded():
        for _ in range(3):
            for name, (p, _b) in sorted(places.items(), key=lambda kv: kv[1][0]):
                if name in hubs:
                    continue
                for k, m in enumerate(LOAD.finditer(scripts.get(name, b''))):
                    child = m.group(1).decode().upper()
                    if child != name and child in scripts:
                        # a scene follows the script that loads it, even when that one moves
                        if places.get(child, (0, ''))[1] == 'loaded by %s' % name:
                            places[child] = (p + (k + 1) / 10000.0, 'loaded by %s' % name)
                        else:
                            put(child, p + (k + 1) / 10000.0, 'loaded by %s' % name)

    # Passes: a scene placed by its area's own stage order can itself be the script that
    # sends the player to another area, so anchoring and placing alternate until settled.
    unknown = set()
    for _pass in range(3):
        place_local(anchors, reached, unknown, observed)
        place_stages()
        place_loaded()
        anchors, reached, observed = anchor_areas()

    #    Whatever is left: the scripts do not say when it happens. Area numbers do not follow
    #    the story (27KKI provably comes before 25TOU) and story flags are shared between
    #    areas in both directions, so neither can place it. These go after everything placed,
    #    in area-number order, and say so.
    last = max(anchors.values()) if anchors else 0
    unknown = set()
    for a in sorted(areas):
        if a not in anchors:
            anchors[a] = last + 1 + (int(a[:2]) if a[:2].isdigit() else 99)
            unknown.add(a)
    for n in [n for n, (p, b) in places.items() if area(n) in unknown]:
        del places[n]                    # re-placed below, against the area's new anchor
    place_local(anchors, reached, unknown, observed)
    place_stages()
    place_loaded()
    # 5. the hand-placed ones
    lowest = min((p for p, _b in places.values()), default=0)

    def where(ref):
        """A script's place, or an area's anchor - whichever the reference names."""
        if ref in places:
            return places[ref][0]
        if ref in anchors:
            return anchors[ref]
        return anchors.get(area(ref))
    for k, (name, (how, ref, why)) in enumerate(OVERRIDES.items()):
        if how == 'last' or (ref in {a for a, (h, _r, _w) in OVERRIDES.items() if h == 'last'}):
            continue                        # handled at the end, once everything is placed
        if how == 'start':
            places[name] = (lowest - 1 + k / 100.0, why)
            continue
        if how == 'before':
            base = where(ref)
            if base is not None:
                places[name] = (base - 0.001, why)
            continue
        # 'after' / 'between' move a whole area, keeping whatever internal order it has
        if how == 'after':
            base, span = where(ref), 0.2
        else:
            lo, hi = where(ref[0]), where(ref[1])
            base, span = (lo, (hi - lo) / 2.0) if None not in (lo, hi) else (None, 0)
        if base is None:
            continue
        anchors[name] = base + span
        unknown.discard(name)
        reached.pop(name, None)
        observed.pop(name, None)
        # Keep the area's internal order, compactly, and leave alone any script the clock
        # dates itself - 06BLK12E advances a counter late in the game even though the
        # capital is first visited early.
        dated = lambda b: ('advances story counter' in b or 'loads it at stage' in b
                           or 'which' in b)      # a stage another area's script starts
        members = sorted((p, n) for n, (p, b) in places.items()
                         if area(n) == name and not dated(places[n][1]))
        for i, (p, n) in enumerate(members):
            places[n] = (anchors[name] + i / 100.0, why)
    # 6. the rest: with its stage siblings when it is named like one (06BLK03A is a
    #    cutscene the capital's hub loads outside its stage switch, so the switch never
    #    dated it; its name says which stage it belongs to), else with its area
    for n in sorted(scripts):
        if n in places:
            continue
        a = area(n)
        m = re.match(r'([0-9A-Z]{5})(\d\d)', n)
        if m and m.group(0) in places and m.group(0) != n:
            hub_stage = m.group(0)
            places[n] = (places[hub_stage][0] + 0.099,
                         'with its stage siblings (%s); not loaded from a stage switch' % hub_stage)
            continue
        if a in anchors:
            note = (' - where the area falls in the story is unknown' if a in unknown else
                    ' - seen playing in %s (counters %s)'
                    % (observed[a]['run'], ' '.join('%s=%d' % kv for kv in sorted(observed[a]['clocks'].items())))
                    if a in observed else
                    ' - first reachable from %s' % reached[a][1] if a in reached else '')
            hand = OVERRIDES.get(a)
            places[n] = (anchors[a] + 0.099,
                         hand[2] if hand and hand[0] in ('after', 'between') else
                         'with its area (%s); not placed by the scripts%s' % (a, note))
        else:
            places[n] = (99.0, 'unplaced')

    # 7. the ones pinned to the very end, once everything else has a place
    ends = [a for a, (how, _r, _w) in OVERRIDES.items() if how == 'last']
    tied = [a for a, (how, ref, _w) in OVERRIDES.items() if how in ('after', 'before') and ref in ends]

    def move_area(a, base, why):
        members = sorted((p, n) for n, (p, b) in places.items() if area(n) == a)
        for i, (p, n) in enumerate(members or [(0.0, a)]):
            places[n] = (base + i / 100.0, why)
    if ends:
        cap = max((p for n, (p, b) in places.items()
                   if p < 90 and area(n) not in set(ends) | set(tied)), default=0)
        for i, a in enumerate(ends):
            move_area(a, cap + 2 + 2 * i, OVERRIDES[a][2])
        for a in tied:
            how, ref, why = OVERRIDES[a]
            at = min((p for n, (p, b) in places.items() if area(n) == ref), default=cap + 2)
            move_area(a, at - 1 if how == 'before' else
                      max(p for n, (p, b) in places.items() if area(n) == ref) + 0.5, why)
    return places


# --- what gates a block ------------------------------------------------------------
#
#   A script block is rarely gated where its text is. The test sits in whatever *runs*
#   it - an object's talk stub, a zone script, the block before it - so reading a block's
#   own bytes says nothing about when it plays. These walk the other way: for every
#   instruction that hands control to a block, collect the conditions in force at that
#   point and give them to the block.
#
#   Handing-over instructions: `04 <addr>` call, `b0/b1 <addr>` run block, `8b` run each
#   block in a table, and `89 2a <addr>` - the object field that names its talk script.
CALL_OPS = {0x04: 0, 0xb0: 0, 0xb1: 0}
STEP = 0.01            # a nudge past whatever a block has to wait for
TALK_FIELD = 0x2a


def after(floor, satisfier):
    """`floor`, or just past `satisfier` when that is not already earlier."""
    return satisfier + STEP if satisfier >= floor else floor
STAGE_JUMPS = {0x10: 'ne', 0x12: 'eq', 0x14: 'le', 0x16: 'lt', 0x18: 'gt', 0x1a: 'ge'}
TEST_CLEAR, TEST_SET, SET_FLAG = 0x0c, 0x0d, 0x1d


def _stage_floor(kind, value, taken):
    """The lowest value a variable can hold on one side of a compare, or None.

    `taken` is the side the jump skips over - the condition's own case - and the other
    side is where control falls when the jump is taken.
    """
    if kind == 'ne':
        return value if taken else (1 if value == 0 else None)
    if kind == 'eq':
        return None if taken else value
    if kind == 'gt':
        return None if taken else value + 1
    if kind == 'ge':
        return None if taken else value
    return None


def _analyse(name):
    """(base, data, block starts, instructions) for a script, or None."""
    import script_decode as sd
    from script_map import slot_base, block_starts
    try:
        r = sd.analyse(name + '.SCN')
    except Exception:
        return None
    if not r or r.get('guessed_base'):
        return None
    data = open(os.path.join(ORIG, name + '.SCN'), 'rb').read()
    base, entries = slot_base(data)
    if base is None:                      # the decoder found one even where slot_base did not
        base, entries = r['base'], r.get('entries', [])
    if base is None:
        return None
    return base, data, sorted(set(block_starts(data, base, entries))), r['insns']


def conditions_of(name):
    """-> {(script, block): {'stage', 'after', 'first_time'}} for what this script runs.

    Conditions are followed through as many hand-overs as it takes, and **across files**:
    most dialogue lives in a scene script whose blocks have no test in them at all, while
    the test sits in the stage script that runs them. `b0 00 <0x3d00 + 3n>` is a call into
    entry n of whichever scene script is loaded in the scene slot, so the gate on that call
    belongs to that entry's block in *that* file - which is why this returns keys naming a
    script, not just an offset.

    Which scene script is in the slot is the same question tools/npcs.py answers: the pair
    a town hub loads together, or the one the nearest preceding `04 <load block>` switched
    to.
    """
    import npcs
    got = _analyse(name)
    if not got:
        return {}
    base, data, starts, insns = got
    sets = [(at, v[0][2]) for at, op, v in insns if op == SET_FLAG and v]
    blocks = npcs.load_blocks(name + '.SCN', data, base)
    switches = sorted((at, blocks[v]) for at, op, vals in insns if op == 0x04
                      for _k, _l, v in vals if v in blocks)
    only = sorted(set(blocks.values()))
    paired = only if len(only) == 1 else npcs.paired_scenes(name + '.SCN')

    def scenes_at(off):
        """The scene script(s) in the slot when the instruction at `off` runs."""
        before = [s for a, s in switches if a < off]
        return [before[-1]] if before else list(paired or ())

    def block_of(off):
        return max([s for s in starts if s <= off], default=None)

    def at_offset(off):
        """The conditions in force at an offset, from the tests that span it."""
        stage, after, once = None, [], False
        for a, op, v in insns:
            if op in STAGE_JUMPS and len(v) >= 3:
                var, value, jump = v[0][2], v[1][2], v[2][2] - base
                end = next((s for s in starts if s > a), len(data))
                if a < off < jump:
                    floor = _stage_floor(STAGE_JUMPS[op], value, True)
                elif a < jump <= off < end:
                    floor = _stage_floor(STAGE_JUMPS[op], value, False)
                else:
                    continue
                if floor is not None and (stage is None or floor > stage[1]):
                    stage = (var, floor)
            elif op in (TEST_CLEAR, TEST_SET) and len(v) >= 2:
                flag, jump = v[0][2], v[1][2] - base
                if not a < off < jump:
                    continue
                # `0c` jumps when the flag is SET, so the code it spans runs while the
                # flag is still clear; `0d` is the other way round (docs/engine_notes.md)
                if op == TEST_CLEAR:
                    if any(f == flag and a < s < jump for s, f in sets):
                        once = True                # tests it clear and sets it: once only
                else:
                    after.append(flag)             # runs once someone else has set it
        return stage, after, once

    edges, inherited = [], {}

    def add_edge(at, word):
        """One hand-over: to a block of this file, or to an entry of the scene script."""
        if word & 0xff00 == npcs.SCENE_SLOT and not (word - npcs.SCENE_SLOT) % 3:
            entry = (word - npcs.SCENE_SLOT) // 3
            for scene in scenes_at(at):
                ents = npcs.scene_entries(scene + '.SCN')
                if entry < len(ents):
                    edges.append((at, (scene + '.SCN', ents[entry])))
            return
        target = word - base
        if 0 <= target < len(data):
            # the exact address, not the block it sits in: one block can hold several
            # entry points and only some of them are gated - snapping them together let
            # an ungated neighbour clear the gate on Innes's theft scene
            edges.append((at, (name + '.SCN', target)))

    for at, op, vals in sorted(insns):
        if op in CALL_OPS and vals:
            add_edge(at, vals[CALL_OPS[op]][2])
        elif op == 0x89 and len(vals) == 2 and vals[0][2] == TALK_FIELD:
            add_edge(at, vals[1][2])
        elif op == 0x8b and len(vals) > 1:
            for _k, _l, v in vals[1:]:
                add_edge(at, v)

    per_call = collections.defaultdict(list)
    for at, key in edges:
        if key[1] is None:
            continue
        stage, after, once = at_offset(at)
        # a gate on the calling block applies to this call as well
        up = inherited.get(block_of(at))
        if up:
            if up[0] and (stage is None or up[0][1] > stage[1]):
                stage = up[0]
            after = sorted(set(after) | set(up[1]))
        per_call[key].append({'stage': stage, 'after': sorted(set(after)),
                              'first_time': once})
        if key[0] == name + '.SCN':
            inherited[key[1]] = (stage, after)
    return {key: weakest(calls) for key, calls in per_call.items()}


def weakest(calls):
    """The condition a block really carries, over every call that reaches it.

    A block is only as gated as the *loosest* way in: if one caller tests the counter and
    another does not, reaching it does not need the counter. So a missing stage wins over
    a stage, the flags are the ones every caller waits on, and "first time only" holds
    only if every caller says so. Taking the tightest instead put Shinobu and Innes's
    first conversation after the manor, because the same block is also what she says when
    you talk to her later.
    """
    stage = None
    if all(c['stage'] for c in calls):
        stage = min((c['stage'] for c in calls), key=lambda s: s[1])
    after = set(calls[0]['after'])
    for c in calls[1:]:
        after &= set(c['after'])
    return {'stage': stage, 'after': sorted(after),
            'first_time': all(c['first_time'] for c in calls)}


_CONDITIONS = {}
_BLOCK_PLACES = {}


def all_conditions(scripts=None):
    """-> {(script, block): conditions}, merged over every script that decodes."""
    if not _CONDITIONS:
        seen = collections.defaultdict(list)
        for name in sorted(scripts or _scripts()):
            for key, cond in conditions_of(name).items():
                seen[key].append(cond)
        _CONDITIONS.update({key: weakest(calls) for key, calls in seen.items()})
    return _CONDITIONS


def flag_setters(scripts=None):
    """-> {flag: [(script, block)]} - every block that sets a flag."""
    import script_decode as sd
    from script_map import slot_base, block_starts
    out = collections.defaultdict(list)
    for name in sorted(scripts or _scripts()):
        got = _analyse(name)
        if not got:
            continue
        _base, _data, starts, insns = got
        for at, op, v in insns:
            if op == SET_FLAG and v:
                block = max([s for s in starts if s <= at], default=None)
                if block is not None:
                    out[v[0][2]].append((name, block))
    return out


_INDEX = {}


def entry_index():
    """{script: [(entry offset, place)]}, sorted - for placing rows in bulk."""
    if not _INDEX:
        for (script, offset), place in block_places().items():
            if offset is not None:          # a milestone in a file with no block table
                _INDEX.setdefault(script, []).append((offset, place))
        for rows in _INDEX.values():
            rows.sort()
    return _INDEX


def place_of(script, offset, block_start=None, places=None):
    """Where a dump row falls: the place of the entry point that leads to it.

    A block is entered at addresses the callers name, and a row belongs to the last such
    address at or before it - within its own block, so a row never inherits a gate from
    the block before. Rows with no entry point above them keep their script's place.
    """
    import bisect
    rows = entry_index().get(script, ())
    i = bisect.bisect_right(rows, (offset, float('inf'))) - 1
    if i >= 0 and (block_start is None or rows[i][0] >= block_start):
        return rows[i][1]
    places = places or script_places()
    return places.get(script[:-4], (float('inf'), ''))[0]


def _blocks_of(name):
    """(base, data, block starts) for a script, without needing it to decode.

    `_analyse` walks the code and stops where it loses the thread, so it misses writes in
    parts it never reached - all five of 11STG01's counter writes sit past that point.
    Block starts come from the slot's own entry table, so they are available either way.
    """
    from script_map import slot_base, block_starts
    path = os.path.join(ORIG, name + '.SCN')
    if not os.path.exists(path):
        return None
    data = open(path, 'rb').read()
    base, entries = slot_base(data)
    if base is None:
        return None
    return base, data, sorted(set(block_starts(data, base, entries)))


_STAGE_WRITERS = {}


def stage_writers():
    """-> {(var, value): [(script, block)]} - the block that advances an area counter.

    The milestone is the *block*, not the file. A hub runs on every visit and writes its
    neighbours' counters from inside whichever stage branch it is in, so `05SKS` as a whole
    means nothing: the write of `20 88 00 06 00` that starts Blackfort's stage 6 belongs to
    one branch of it, and only that branch is late.

    Only values a hub actually switches on count as stages (`STAGE_AT`). Without that test
    a script's other uses of the same variable come in as milestones - 27KKI01 writing
    `0x95 = 18` made area 19's chain contradict area 05's, the one cycle in the whole set.
    Writes from inside the counter's own area are resets on entry (all eight 07CSLnn set
    0x89 back to 1), and the world map writes nearly everything, so neither counts.
    """
    if _STAGE_WRITERS:
        return _STAGE_WRITERS
    script_places()
    real = collections.defaultdict(set)
    for var, val in STAGE_AT:
        if val:
            real[var].add(val)
    scripts = _scripts()
    for name in sorted(scripts):
        if name == WORLD_MAP:
            continue
        got = _blocks_of(name)
        if got:
            _base, data, starts = got
        else:
            # No readable block table (25TOU00C opens with code, not an entry table). Its
            # writes still count - it advances four counters, and dropping it left the
            # tower's whole moment out of the network and put it at the end of the game.
            data, starts = scripts[name], []
        try:
            mine = AREA_STAGE + int(name[:2])
        except ValueError:
            mine = None
        for m in SET.finditer(data):
            var, val = m.group(1)[0], m.group(2)[0]
            if val not in real.get(var, ()) or var == mine:
                continue
            block = block_at(name, data, starts, m.start())
            _STAGE_WRITERS.setdefault((var, val), []).append((name + '.SCN', block))
    return _STAGE_WRITERS


_REGIONS = {}


def hub_regions(name, data=None):
    """[(start, end, var, val)] - the code a hub runs only while its counter == val.

    A hub is one stage switch: `10 <var> 00 <n> 00 <next>` skips to <next> unless the
    counter is n, so the bytes up to <next> are stage n's, and a write there happens at
    stage n and no other time. (For a jump-table hub, entry i's block up to the next
    entry.) That is what dates a hub's writes: 05SKS sets the manor's 0x85 to 7 inside
    its case for Skus stage 6, so that write comes after whatever starts stage 6 -
    03YSK70 - which the file as one block could never say.
    """
    if name in _REGIONS:
        return _REGIONS[name]
    data = data if data is not None else _scripts()[name]
    var_wanted, out = stage_var(name), []
    for m in CASE_REGION.finditer(data):
        var, val = resolve_copy(data, m.start(), m.group(1)[0]), m.group(2)[0]
        nxt = int.from_bytes(m.group(3), 'little')
        if var == var_wanted and m.end() < nxt <= len(data):
            out.append((m.end(), nxt, var, val))
    for m in SWITCH.finditer(data):
        var, count, body = int.from_bytes(m.group(1), 'little'), m.group(3)[0], m.end()
        if not 0 < count <= MAX_TABLE or body + 3 * count > len(data):
            continue
        entries = [int.from_bytes(data[body + 3 * i + 1:body + 3 * i + 3], 'little')
                   for i in range(count) if data[body + 3 * i] == 0]
        if len(entries) != count or resolve_copy(data, m.start(), var, 0x20) != var_wanted:
            continue
        for val, at in enumerate(entries):
            if 0 < at < len(data):
                end = min([e for e in entries if e > at] + [len(data)])
                out.append((at, end, var_wanted, val))
    _REGIONS[name] = sorted(out)
    return _REGIONS[name]


def block_at(name, data, starts, off):
    """The block an offset belongs to: for a hub, its stage case (innermost); else the
    block table's. None outside any."""
    if re.fullmatch(r'\d\d[A-Z]+', name):
        inside = [(e - s, s) for s, e, _v, _n in hub_regions(name, data) if s <= off < e]
        if inside:
            return min(inside)[1]
    return max([b for b in starts if b <= off], default=None)


def hub_case_of(name, block):
    """(var, val) of a hub's stage case that `block_at` named, or None."""
    for s, _e, var, val in hub_regions(name):
        if s == block:
            return var, val
    return None


def stage_chain():
    """-> {(script, block): [(script, block)]} - each milestone's immediate predecessors.

    A counter counts up, so the block that sets it to 4 runs after the one that set it to
    3. Across the fourteen counters the hubs switch on, that is 49 statements about which
    of two scripts in *different* areas happens first, and - once the values are limited to
    real stages - they have no cycle between them: one order satisfies all of them. That is
    the strongest evidence in the game about the shape of the story, and it cuts across the
    area numbering, which does not follow the story at all.

    A script that advances the same counter twice (17DRL04A sets Blackfort to 7 and then to
    9) is not two milestones in a cycle; it simply spans them, so its later appearances in
    a chain are dropped.
    """
    writers = stage_writers()
    out = collections.defaultdict(list)
    _CHAIN_GROUPS.clear()
    for var in sorted({v for v, _n in writers}):
        prev, seen = None, set()
        for val in sorted(n for v, n in writers if v == var):
            here = [k for k in writers[(var, val)] if k not in seen]
            if not here:
                continue
            if prev:
                for key in here:
                    out[key].extend(prev)
                    _CHAIN_GROUPS[key].append(list(prev))   # one counter: any of these
            seen |= set(here)
            prev = here
    #  A hub's stage case runs only once its counter has reached that stage, so a write
    #  inside it also follows whatever started the stage: Skus's case 6 (which advances
    #  the manor to 7) follows 03YSK70, which set Skus to 6.
    for key in set(out) | {p for v in out.values() for p in v}:
        name, block = key[0][:-4], key[1]
        case = hub_case_of(name, block) if re.fullmatch(r'\d\d[A-Z]+', name) and block is not None else None
        if case and case[1]:
            starters = [p for p in writers.get(case, ()) if p != key]
            for p in starters:
                if p not in out[key]:
                    out[key].append(p)
            if starters:
                _CHAIN_GROUPS[key].append(starters)
    return out


#   The same predecessors, kept apart by counter: a block that advances several counters
#   needs the previous value of *each* of them, and it is only within one counter that
#   several writers are alternatives. Flattened, 18KSK's need was met by any of its three
#   counters' predecessors, and the one that mattered (17DRL04A's block that starts
#   Blackfort's stage 7) went unchecked.
_CHAIN_GROUPS = collections.defaultdict(list)


def chain_groups():
    """-> {(script, block): [[alternative predecessors] per counter it advances]}"""
    stage_chain()
    return _CHAIN_GROUPS


def stage_starts(var, floor):
    """The milestone blocks that first make `var >= floor` true, or [].

    A floor of 0 is the state the game starts in and needs nothing: reading it as "the
    first block that writes the counter" put Innes's first meeting (`10 84 00 00 00`,
    the counter still 0) after the manor visit that advances it.
    """
    if floor <= 0:
        return []
    writers = stage_writers()
    have = sorted(n for v, n in writers if v == var and n >= floor)
    return writers[(var, have[0])] if have else []



# --- the counter a single script runs on -------------------------------------------
#
#   An area's counter separates its *visits*. Inside one visit a script can still cover a
#   long sequence - 03YSK01A is the whole of the first time at the manor, from arriving to
#   stealing the jewel to being chased out - and it tracks where in that sequence the
#   player is with a variable of its own:
#
#       @00ed  20 28 00 01 00        var 0x28 := 1
#       @0047  10 28 00 07 00 <t>    unless 0x28 == 7, skip - the scene for coming back
#                                    after being teleported out of the Zerf fight
#       @00e6  10 28 00 00 00 <t>    unless 0x28 == 0 - the manor before any of it happens
#
#   Those two blocks are the file's first and second, so file order puts the end of the
#   sequence before the beginning. Reading the tests puts them back.
COMPARE = re.compile(rb'([\x10-\x1b])(..)(..)(..)', re.S)
LOCAL_SKIP = {0x7e, 0x7f}      # the hubs' scratch registers


def _floor(op, value):
    """The lowest value of the counter the code *after* a test can run at, or None.

    The jump is taken when the test holds, so the code that follows runs on its negation:
    `10` jumps if !=, so what follows needs ==. Tests that only put a ceiling on the
    counter (`18` jumps if >, so what follows runs at or below the value) say nothing
    about how far along the sequence is and are left out.
    """
    return {0x10: value, 0x16: value, 0x14: value + 1}.get(op)


def local_counter(data, base):
    """The variable a script uses to track its own sequence, or None.

    It has to be tested at more than one value - one test is a condition, several are a
    sequence - and it must not be an area counter (those separate visits, and are handled
    a level up) or one of the scratch registers every hub reuses.
    """
    written = {m.group(1)[0] for m in SET.finditer(data)}
    written |= {data[at + 1] for at in range(len(data) - 2)
                if data[at] == 0x22 and not data[at + 2]}      # `22 <var> 00` - counter++
    seen = collections.defaultdict(set)
    for at, var, value, _target in _compares(data, base):
        if var in LOCAL_SKIP or var < 0x08 or AREA_STAGE <= var <= AREA_STAGE + 0x40:
            continue
        if var not in written:        # a script's own counter is one it also advances
            continue
        seen[var].add(value)
    ranked = sorted(((len(v), var) for var, v in seen.items() if len(v) > 1), reverse=True)
    return ranked[0][1] if ranked else None


def _compares(data, base):
    """[(at, var, value, target)] for every compare-with-a-constant in a script.

    Every offset is tried, not `finditer`: matches overlap, and a regex scan drops the
    second of two compares that sit seven bytes apart. That cost the manor its middle step
    - the scene where the guards are called on Shinobu is behind `unless 0x28 == 2`, and
    the test was inside the bytes an earlier match had already eaten.
    """
    out = []
    for at in range(len(data) - 6):
        op = data[at]
        if not 0x10 <= op <= 0x1b or op % 2:         # odd opcodes compare two variables
            continue
        var = int.from_bytes(data[at + 1:at + 3], 'little')
        value = int.from_bytes(data[at + 3:at + 5], 'little')
        target = int.from_bytes(data[at + 5:at + 7], 'little') - base
        if var < 0x100 and value < MAX_STAGE and at < target <= len(data):
            out.append((at, var, value, target))
    return out


def local_steps(name, data=None, base=None):
    """-> (variable, {offset: step}) for one script, or (None, {}).

    `step` is how far along the script's own sequence an offset is: the highest value its
    counter has to have reached for the code there to run. Rows sort by it before their
    offset, so a script's scenes read in the order they happen rather than the order they
    were assembled.
    """
    if data is None:
        got = _blocks_of(name)
        if not got:
            return None, {}
        base, data, _starts = got
    var = local_counter(data, base)
    if var is None:
        return None, {}
    steps = {}
    for at, v, value, target in _compares(data, base):
        step = _floor(data[at], value)
        if v == var and step is not None:
            steps[(at, target)] = step
    return var, steps



#   `09`/`04` carry a bare address; `b0`/`b1` carry a *tagged* one - a tag byte, then the
#   address - so theirs sits one byte further along (script_decode's operand table).
#   Reading them all as bare put every `b0` target thousands of bytes out, and `b0 00 68 18`
#   is exactly what a guarded jump uses: `unless 0x28 == 7, skip` then run the block at
#   0x1868.
GOTO = re.compile(rb'(?:[\x09\x04](..)|[\xb0\xb1].(..))', re.S)


def _target(m, base):
    return int.from_bytes(m.group(1) or m.group(2), 'little') - base


def block_steps(name):
    """-> (variable, {block: step}) - how far along its script's sequence each block is.

    The test itself guards only a jump - `unless 0x28 == 7, skip` then `09 <addr>` - so
    reading the step straight off the bytes it spans finds nothing but the jump. The step
    has to follow the jump into the block it leads to, and on through whatever that block
    calls.

    A block reached from two steps is only as late as the **earliest** way in, the same
    rule as `weakest` uses for scene conditions: the scripts share their "say this line"
    helpers freely, and taking the latest caller dragged ordinary townspeople to the end of
    the sequence with the one scene that also used them.
    """
    got = _blocks_of(name)
    if not got:
        return None, {}
    base, data, starts = got
    var, spans = local_steps(name, data, base)
    if var is None:
        return None, {}

    def block_of(off):
        return max([b for b in starts if b <= off], default=None)

    def extent(block):
        return next((b for b in starts if b > block), len(data))

    step = {}
    for (at, target), s in spans.items():
        here = block_of(at)
        if here is not None and target <= extent(here):
            #  The test guards the rest of its own block: everything from it to the jump
            #  target, which is still inside the block. That is the common shape - the
            #  block is one handler, and it opens by asking how far along the player is.
            step[here] = max(step.get(here, 0), s)
        for m in GOTO.finditer(data, at, target):    # and whatever the guarded jump runs
            b = block_of(_target(m, base))
            if b is not None:
                step[b] = max(step.get(b, 0), s)
    for _round in range(6):
        moved = False
        for block in list(step):
            if not step[block]:
                continue
            for m in GOTO.finditer(data, block, extent(block)):
                b = block_of(_target(m, base))
                if b is None or b == block:
                    continue
                callers = [step.get(block_of(c.start()), 0)
                           for c in GOTO.finditer(data)
                           if _target(c, base) == b]
                want = min(callers) if callers else 0
                if want > step.get(b, 0):
                    step[b] = want
                    moved = True
        if not moved:
            break
    return var, step


def step_at(steps, offset):
    """How far along its script's sequence one offset is."""
    return max([s for (at, target), s in steps.items() if at < offset < target] or [0])


def block_places(rounds=4):
    """-> {(script, block): place} - every block, placed by what has to happen first.

    A block starts where its script does and is then pushed later by whatever gates it:

    * a **stage test** on a real counter - a whole-game clock or an area's own 0x82+N -
      puts it after the block that first sets that counter to that value (`stage_starts`),
      wherever in the game that block turns out to be. The hubs' scratch registers
      0x7e/0x7f are excluded: they are compared constantly and mean nothing between
      scripts.
    * a **milestone it follows in a counter's chain** (`stage_chain`) puts it after the
      block before it in that chain. These are the constraints that cross areas, and they
      are what stops the area numbering from deciding the order: Blackfort's stage 6 is
      started from inside Skus, so that branch of Skus is late however early the town is.
    * a **flag it waits on** puts it no earlier than the first block that sets that flag.
      That block has a place of its own, so this repeats until it settles - a few rounds
      is enough, and a cycle simply stops moving.

    This is what makes the order reliable rather than approximate: 02OLB01 is loaded both
    before and after the manor, and only the gate says which of its scenes is which.
    """
    if _BLOCK_PLACES:
        return _BLOCK_PLACES
    places = script_places()
    conds = all_conditions()
    setters = flag_setters()
    chain = stage_chain()

    def base_of(key):
        return places.get(key[0][:-4], (0.0, ''))[0]

    at = {key: base_of(key) for key in set(conds) | set(chain)
          | {k for v in chain.values() for k in v}}
    #  The place orders rows *within* a rank (translator_context sorts by rank first),
    #  so a satisfier of an earlier rank is already above and there is nothing to push
    #  past. Pushing anyway cascaded: 27KKI01's block was nudged past 16MKI01B's place
    #  (late in place-space, early in rank), and everything after it in three chains
    #  followed, which put a castle scene 1,200 rows below the rest of its visit.
    def rank_key(key):
        return rank_of(key[0], key[1])

    def push(floor, key, satisfiers):
        mine = rank_key(key)
        later = [p for k, p in satisfiers if rank_key(k) >= mine]
        return after(floor, min(later)) if later else floor

    for _round in range(rounds):
        moved = False
        for key in at:
            floor = base_of(key)
            cond = conds.get(key)
            if cond:
                if cond['stage']:
                    starts = stage_starts(*cond['stage'])
                    if starts:
                        # pushed only past a satisfier that is *later*: one already
                        # earlier is satisfied where the block is, and nudging past it
                        # anyway put 06BLK02E's opening scene after the rest of its file
                        floor = push(floor, key, [(k, at.get(k, base_of(k))) for k in starts])
                    else:
                        p = stage_place(*cond['stage'])
                        if p is not None:
                            floor = max(floor, p)
                for flag in cond['after']:
                    setter = [((n + '.SCN', b), at.get((n + '.SCN', b), places.get(n, (float('inf'), ''))[0]))
                              for n, b in setters.get(flag, ())]
                    if setter:
                        floor = push(floor, key, setter)
            preds = [(p, at.get(p, base_of(p))) for p in chain.get(key, ())]
            if preds:
                floor = push(floor, key, preds)
            if floor > at.get(key, 0.0) + 1e-9:
                at[key] = floor
                moved = True
        if not moved:
            break
    _BLOCK_PLACES.update(at)
    return _BLOCK_PLACES


# --- the story rank ----------------------------------------------------------------
#
#   Places (above) are built area by area: a script sits in its area's slot, and the areas
#   are ordered by where the player can first get to them. That is the right shape for a
#   game played area by area, and the wrong one for this game, where a town is revisited at
#   five separate points in the story and its later visits belong next to other areas'
#   later visits, not next to its own first one.
#
#   The counter chains say exactly that, and they say it without reference to any area
#   ordering: `stage_chain` is 38 statements of the form "this block runs before that one",
#   read off counters counting up, and they have no cycle. The longest path through them is
#   a rank - eleven deep - and every stage of every counter inherits the rank of the block
#   that starts it. A script the hub loads at that stage gets that rank, whatever area it
#   is in. That is what puts Kikuichi's second visit after the manor's late scene, which
#   area order had backwards and the recorded playthrough confirms.
#
#   Rank is coarse on purpose: it says which of the game's eleven moments a scene belongs
#   to, and nothing about the order inside one. The place decides that, so rows sort by
#   (rank, place) and everything the areas got right is kept.
_RANK = {}
STAGE_BASIS = re.compile(r'loads it at (?:its )?stage (\d+) \(var (0x[0-9a-f]+)\)')
LOADED_BASIS = re.compile(r'loaded by ([0-9A-Z]+)')
FROM_BASIS = re.compile(r'(?:first reachable from|reached only from [^(]*\()\s*([0-9A-Z]{5})')
AREA_BASIS = re.compile(r'with its area \(([0-9A-Z]{5})\)')


def milestone_ranks():
    """-> {(script, block): rank} - the longest path through the counter chains."""
    chain = stage_chain()
    nodes = set(chain) | {p for v in chain.values() for p in v}
    rank = {n: 0 for n in nodes}
    for _round in range(len(nodes) + 1):
        moved = False
        for n in nodes:
            want = max([rank[p] + 1 for p in chain.get(n, ())] or [0])
            if want > rank[n]:
                rank[n] = want
                moved = True
        if not moved:
            break
    return rank


_STAGE_RANKS = {}


def _stages_from(block_rank, writers):
    """-> {(var, value): rank} - when a counter reaches each of its stages.

    A stage nobody outside the area sets (the castle's own eight scripts all reset 0x89 to
    1) is not evidence of a new moment, so it keeps the rank of the last stage that was -
    the counter never goes backwards.
    """
    out = {}
    for var in sorted({v for v, _n in writers} | {v for v, _n in STAGE_AT}):
        high = 0
        for val in sorted({n for v, n in writers if v == var}
                          | {n for v, n in STAGE_AT if v == var}):
            here = writers.get((var, val))
            if here:
                high = max(high, max(block_rank.get(k, 0) for k in here))
            if high:
                out[(var, val)] = high
    #  A stage nothing in the network reaches is left out entirely rather than given rank
    #  0. The two are not the same thing, and treating them as one put the Black Dragon
    #  Cave - whose first two visits are started by scripts the chains never constrain -
    #  in the first hundred rows of the game, 9700 rows before the rest of it.
    return out


def stage_ranks():
    """-> {(var, value): rank}, as story_rank settled them."""
    story_rank()
    return _STAGE_RANKS


def story_rank():
    """-> {script: (rank, why)} - which moment of the story a script belongs to."""
    if _RANK:
        return _RANK
    places = script_places()
    scripts = _scripts()
    chain, writers = stage_chain(), stage_writers()

    #  Every piece of evidence raises a script's rank and none lowers it: a scene can
    #  only be as early as the *latest* thing it waits for. Taking the first piece found
    #  and keeping it put 15MKR02G at the recorded playthrough's guess for its area,
    #  sixty rows above the Kikuichi scene that starts the stage it is loaded at.
    def raise_to(name, r, why):
        if r is not None and r > _RANK.get(name, (-1, ''))[0]:
            _RANK[name] = (r, why)
            return True
        return False

    area = lambda n: n[:5] if n[:2].isdigit() else n
    hubs = {n for n in scripts if re.fullmatch(r'\d\d[A-Z]+', n)}
    lone = {n for n in hubs if not any(m != n and area(m) == n for m in scripts)}
    loaders, loads_of = collections.defaultdict(set), collections.defaultdict(set)
    for parent, d in scripts.items():
        if parent in hubs:
            continue
        for m in LOAD.finditer(d):
            child = m.group(1).decode().upper()
            if child != parent and child in scripts:
                loaders[child].add(parent)
                loads_of[parent].add(child)
    stage_of = {}                                     # script -> the stage a hub loads it at
    for name, (_p, basis) in places.items():
        m = STAGE_BASIS.search(basis)
        if m:
            stage_of[name] = (int(m.group(2), 16), int(m.group(1)))

    #  Blocks, stages and scripts each take their rank from the others, so this settles
    #  as a fixpoint: a milestone block is one past the milestones before it and no
    #  earlier than the script it is in (06BLK12E's block advances Nanpu, and 06BLK12E
    #  is loaded on the capital's sixth visit - so Nanpu is after that visit, which the
    #  chain alone did not know); a stage is as late as the block that starts it; a
    #  script is as late as the stage it is loaded at, the milestone it holds, or the
    #  script that loads it - from the earliest of its loaders.
    #
    #  Two ranks per script, and the difference matters. When a script becomes
    #  **available** is the stage it is loaded at, or the availability of what loads it;
    #  that is what its blocks can inherit and what it passes down to the scripts it
    #  loads. When its latest **milestone** fires can be much later - 17DRL04 is loaded
    #  at Dragon's Lair stage 3 and a late block of it starts the ruins' stage 6 - and
    #  passing *that* down to 17DRL04A, whose own block starts Blackfort's stage 7
    #  before the ruins get there, was a cycle that climbed without end.
    avail = {}

    def lift(name, r, why):
        if r is not None and r > avail.get(name, (-1, ''))[0]:
            avail[name] = (r, why)
            return True
        return False

    #  Nodes in a fixed order, and enough rounds for the deepest chain: over a set, the
    #  visiting order changed with Python's hash seed, and twelve rounds sometimes fell
    #  short of the seventeen-deep chain - a different sheet from one run to the next.
    nodes = sorted(set(chain) | {p for v in chain.values() for p in v}, key=BLOCK_KEY)
    block_rank = {n: 0 for n in nodes}
    for _round in range(4 * len(nodes) + 12):
        moved = False
        for n in nodes:
            want = max([block_rank[p] + 1 for p in chain.get(n, ())] or [0])
            script = n[0][:-4]
            if script not in hubs or script in lone:
                want = max(want, avail.get(script, (0, ''))[0])
            if want > block_rank[n]:
                block_rank[n] = want
                moved = True
        stages = _stages_from(block_rank, writers)
        for name, key in stage_of.items():
            if key in stages:
                moved |= lift(name, stages[key], 'the %#x stage %d it is loaded at' % key)
        #  A scene goes with what loads it - read off the load instructions themselves,
        #  not the basis text, which names only the earliest loader and may say something
        #  else entirely for a script that is also a milestone. Loaded from several
        #  places, it is available from the earliest of them.
        for _again in range(4):
            for name, parents in sorted(loaders.items()):
                ranked = [(avail[p][0], p) for p in parents if p in avail]
                if ranked:
                    r, p = min(ranked)
                    tail = ' (%s)' % avail[p][1] if weak(avail[p][1]) else ''
                    moved |= lift(name, r, 'it is loaded by %s%s' % (p, tail))
        if not moved:
            break
    else:
        print('story_rank: the counters did not settle - a cycle; '
              'ranks above %d are suspect' % max(block_rank.values()), file=sys.stderr)
    _RANK.update(avail)
    #  A script that is itself a milestone sorts at that milestone - unless it is a hub
    #  with scripts of its own, which runs on every visit and writes from whichever
    #  branch it is in. A hub that is its whole area (22MZI, 18KSK, 24UMB) has no
    #  branches to hide in.
    for n, r in block_rank.items():
        script = n[0][:-4]
        if r and (script not in hubs or script in lone):
            raise_to(script, r, 'it is what advances the story here')
    #  And a scene follows its loader's milestone too, where that contradicts no
    #  milestone of its own: 07CSL02 advances five counters at once on the castle's
    #  second visit, and 07CSL02A/B are that visit's talk, so they go with it (the
    #  recorded playthrough agrees). 17DRL04A does not follow 17DRL04's late block: its
    #  own block starts Blackfort's stage 7, which comes well before it.
    own = collections.defaultdict(list)
    for n, r in block_rank.items():
        if r:
            own[n[0][:-4]].append(r)
    for _again in range(4):
        for name, parents in sorted(loaders.items()):
            ranked = [(_RANK[p][0], p) for p in parents if p in _RANK]
            if not ranked:
                continue
            r, p = min(ranked)
            if r > _RANK.get(name, (0, ''))[0] and not any(b < r for b in own.get(name, ())):
                tail = ' (%s)' % _RANK[p][1] if weak(_RANK[p][1]) else ''
                raise_to(name, r, 'it is loaded by %s%s' % (p, tail))
    _STAGE_RANKS.update(_stages_from(block_rank, writers))
    _BLOCK_RANKS.update(block_rank)

    #  Areas the chains never constrain, dated from the playthrough instead: the anchor's
    #  own scene and everything else in that area that no counter reached.
    seen = video_ranks(_RANK)
    for name in list(_RANK) + [n for n in places if n not in _RANK]:
        if name[:5] in seen and _RANK.get(name, (0, ''))[0] <= 0:
            _RANK[name] = (seen[name[:5]], 'where %s is in the recorded playthrough'
                           % name[:5])
    #  ... unless the script holds a milestone, which the counters date on both sides:
    #  16MKI01B's exit block starts McCulloch's stage 4, and Kikuichi's first visit
    #  takes it on to 6, so that visit of 16MKI is before Kikuichi whatever a frame of
    #  the playthrough (a later return there) said. The block's rank is the script's.
    successors = collections.defaultdict(set)
    for key, preds in chain.items():
        for p in preds:
            successors[p].add(key)
    for (s, b), r in block_rank.items():
        name = s[:-4]
        if name not in _RANK or not weak(_RANK[name][1]) or (name in hubs and name not in lone):
            continue
        # no earlier than the block (its predecessors), no later than the block before
        # what follows it: a block with nothing before it in any chain ranks 0, and it is
        # the successor that dates it - 16MKI01B's is Kikuichi's first visit, rank 4
        after = [block_rank[n] for n in successors.get((s, b), ()) if block_rank.get(n)]
        if r and _RANK[name][0] < r:
            _RANK[name] = (r, 'it is what advances the story here')
        if after and _RANK[name][0] >= min(after):
            # just before what follows it - not a whole moment earlier, which would
            # override the playthrough for no reason the counters give
            _RANK[name] = (max(r, min(after) - 0.1), 'it is what advances the story here')
    #  And what the playthrough dated goes no later than the counters date its area: a
    #  frame is an upper bound on when a scene is available, not a lower one, and a late
    #  frame of a town the counters put early is a later return there.
    strong_by_area = collections.defaultdict(list)
    for n, (r, why) in _RANK.items():
        if not weak(why):
            strong_by_area[area(n)].append(r)
    for n, (r, why) in list(_RANK.items()):
        if weak(why) and strong_by_area.get(area(n)) and r > max(strong_by_area[area(n)]):
            _RANK[n] = (max(strong_by_area[area(n)]), why + ', and no later than the counters date its area')
    #  What is left goes with its area when the area has a ranked script: the ranked
    #  neighbour nearest before it in the area's own order, else the area's earliest.
    #  (The tower's hub and side scenes sit beside 25TOU00C, the one script of it that
    #  the counters date; by the global rule below they landed near the end of the game,
    #  because the tower's place - an index into the counters' topological order - is
    #  late even though its moment is not.)
    by_area = collections.defaultdict(list)
    for n, (r, _w) in _RANK.items():
        if n in places:
            by_area[area(n)].append((places[n][0], r, n))
    for name, (p, _basis) in sorted(places.items()):
        if name in _RANK or area(name) not in by_area:
            continue
        mates = sorted(by_area[area(name)])
        before = [(q, r, n) for q, r, n in mates if q <= p]
        _q, r, n = before[-1] if before else mates[0]
        _RANK[name] = (r, 'with %s, in its area' % n)
    #  Whole areas the counters never mention keep the order the places gave them,
    #  dropped into the band their ranked neighbours are in. Ranking them by what the
    #  player reaches them from instead - the earliest they *can* be seen - was worse:
    #  it pulled Dorral Village and Ruins McCulloch to the very start, because the first scene of
    #  an area is reachable long before the rest of it is written.
    known = sorted((places[n][0], r) for n, (r, _w) in _RANK.items() if n in places)
    for name, (p, _basis) in places.items():
        if name not in _RANK:
            before = [r for q, r in known if q <= p]
            _RANK[name] = (max(before) if before else 0, 'no counter reaches it')
    #  Weak evidence never contradicts the counters. A visit dated from the playthrough
    #  or only by its area cannot come later than the *next* visit of the same area when
    #  the counters date that one: 23SOH's first visit read 6.6 off the video while its
    #  second, which the tower starts, is 6 - and the second cannot come first.
    for hub in sorted(hubs):
        var = stage_var(hub)
        visits = collections.defaultdict(set)
        for v, val, child in hub_cases(scripts[hub]):
            if v == var:
                visits[val].add(child)
        members = {}
        for val, kids in visits.items():
            grp = set(kids)
            for _round in range(3):
                for k in list(grp):
                    grp |= loads_of.get(k, set())
            members[val] = grp
        cap = None
        for val in sorted(visits, reverse=True):
            if cap is not None:
                for n in members[val]:
                    if n in _RANK and weak(_RANK[n][1]) and _RANK[n][0] > cap:
                        _RANK[n] = (cap, _RANK[n][1] + ', and no later than the visit after')
            strong = [_RANK[n][0] for n in members[val]
                      if n in _RANK and not weak(_RANK[n][1])]
            if strong:
                cap = min(strong) if cap is None else min(cap, min(strong))
        if cap is not None and hub in _RANK and weak(_RANK[hub][1]) and _RANK[hub][0] > cap:
            _RANK[hub] = (cap, _RANK[hub][1] + ', and no later than its visits')
    #  Nor can an area come later than one that is only reached through it (the
    #  OVERRIDES that say "after"): the Abandoned Mine's scene advances the castle to
    #  stage 6, and the Walkreuz Underground is the only way in, so the Underground is
    #  no later than that - not the endgame its place-based rank had it at.
    #  The same for every area the scripts say is reached through another (the basis's
    #  "first reachable from"): 16MKI is entered from McCulloch, and its exit block is
    #  dated before Kikuichi by McCulloch's own counter, so McCulloch's first visit -
    #  which a frame of the playthrough had at its fifth - is no later than that.
    through = {}
    for name, (how, ref, _why) in OVERRIDES.items():
        if how == 'after' and ref in hubs:
            through[name] = ref
    for name, (_p, basis) in places.items():
        m = FROM_BASIS.search(basis)
        if m and m.group(1) in hubs and m.group(1) != area(name):
            through.setdefault(area(name), m.group(1))
    for _round in range(4):
        for name, ref in through.items():
            strong = [r for n, (r, why) in _RANK.items() if area(n) == name and not weak(why)]
            if not strong:
                continue
            for n in [n for n in _RANK if area(n) == ref]:
                if weak(_RANK[n][1]) and _RANK[n][0] > min(strong):
                    _RANK[n] = (min(strong), _RANK[n][1] + ', and no later than %s, reached through it' % name)
    #  The ending is pinned by hand (OVERRIDES 'last', and what is tied to it): the
    #  last dungeon after every counter's last stage, the END after that, the calm scene
    #  before the last dungeon just ahead of it. The places already say so; the rank,
    #  which sorts first, has to agree or the final dungeon lands among the last few
    #  areas the counters date.
    ends = [a for a, (how, _r, _w) in OVERRIDES.items() if how == 'last']
    tied = {a: (how, ref) for a, (how, ref, _w) in OVERRIDES.items() if ref in ends}
    if ends:
        top = max((r for n, (r, _w) in _RANK.items() if area(n) not in set(ends) | set(tied)), default=0)
        for n in list(_RANK):
            a = area(n)
            if a in ends:
                _RANK[n] = (top + 1, OVERRIDES[a][2])
            elif a in tied:
                _RANK[n] = (top + (0.5 if tied[a][0] == 'before' else 2), OVERRIDES[a][2])
    return _RANK


_BLOCK_RANKS = {}


def weak(why):
    """Evidence that is a guess - the playthrough, the area, nothing at all - rather
    than a counter. A rank taken from a loader carries the loader's weakness."""
    return why.startswith(('where ', 'with ', 'no counter')) or '(where ' in why \
        or '(with ' in why or '(no counter' in why


ANCHORS = os.path.join(HERE, 'docs', 'video_anchors.json')


def video_ranks(ranks):
    """-> {script: rank} for scenes the chains cannot reach, read off the playthrough.

    A milestone with nothing before it in any chain gets rank 0 from the longest path, and
    that means "no counter constrains it", not "it happens first". Three whole branches of
    the game are like that - City McCulloch, Dorral Village and Ruins McCulloch are reached
    by a quest the counters never mention - and rank 0 threw them to the very start, 2000
    rows before the castle they follow.

    What does date them is that someone played the game on video (docs/video_anchors.json,
    a line of dialogue and the second it appears). The anchors whose scene the chains *do*
    rank calibrate video time against rank; an anchor they do not rank is then read off
    that calibration, and its whole area goes with it. This is weaker evidence than a
    counter and it is kept separate for that reason: it dates four areas, and the rest of
    the order never depends on it.
    """
    import json
    if not os.path.exists(ANCHORS):
        return {}
    anchors = sorted(json.load(open(ANCHORS, encoding='utf-8'))['anchors'],
                     key=lambda a: a['at'])
    known, high = [], 0
    for a in anchors:                      # calibration: only ranks a chain proved
        r = ranks.get(a['script'], (0, ''))[0]
        if r > 0 and a['script'] in ranks:
            high = max(high, r)
            known.append((a['at'], high))
    if len(known) < 2:
        return {}
    out = {}
    for a in anchors:
        if ranks.get(a['script'], (0, ''))[0] > 0:
            continue
        t = a['at']
        before = [(q, r) for q, r in known if q <= t]
        after = [(q, r) for q, r in known if q > t]
        if before and after:
            (q0, r0), (q1, r1) = before[-1], after[0]
            r = r0 + (r1 - r0) * (t - q0) / float(q1 - q0) if q1 > q0 else r0
        elif before:
            r = before[-1][1] + 0.5
        else:
            r = max(0.0, after[0][1] - 0.5)
        out.setdefault(a['script'][:5], r)
    return out


def rank_of(script, block=None):
    """The rank of one block: its script's, or later if its own gate says so - or, for
    a milestone block, exactly its own.

    A script sorts at its latest milestone, and a milestone block that has to come
    *before* something earlier than that sorts on its own: 17DRL04A's block that starts
    Blackfort's stage 7 goes before 18KSK (stage 8), while the file's other block, which
    starts stage 9, and its chatter stay after. Not for a hub with scripts of its own,
    whose milestones sit in its stage branches and whose text is the arrival.
    """
    ranks = story_rank()
    name = script[:-4] if script.endswith('.SCN') else script
    out = ranks.get(name, (0, ''))[0]
    if block is not None:
        own = _BLOCK_RANKS.get((name + '.SCN', block))
        if own and (not re.fullmatch(r'\d\d[A-Z]+', name)
                    or not any(m != name and m[:5] == name for m in _scripts())):
            out = own
        cond = all_conditions().get((script, block))
        if cond and cond['stage']:
            out = max(out, stage_ranks().get(cond['stage'], 0))
    return out


# --- every causal dependency, in one place ------------------------------------------
#
#   Everything above *places* rows; this lists what each row has to come after, so that
#   the placement can be checked (tools/check_story_order.py) and, where a heuristic
#   still gets it wrong, repaired (translator_context's causal pass). A row is subject to
#   the needs of its script, of its block and of the entry point that leads to it, and
#   each need is satisfied by any one of the listed (script, block) having run:
#
#     load    the script is loaded by a hub while counter var == val (or by a script that
#             is), so it plays after the block that set the counter to val
#     stage   the entry is gated by `var >= floor`: after a write of var to >= floor
#     flag    the entry is gated by `flag set`: after a `1d <flag>`
#     step    the block needs the script's own progress counter at >= step: after the
#             block that advances it there
#     chain   the block advances a counter to n: after the block that set it to n - 1
#
#   The world map's writes never count (docs/engine_notes.md, "Which area leads where").
INC = re.compile(rb'\x22([\x00-\xff])\x00', re.S)     # `22 <var> 00` - counter++
LOW_VARS = 0x08
BLOCK_KEY = lambda w: (w[0], -1 if w[1] is None else w[1])   # (script, block or None), sortable                                       # 0..7 are engine registers (var 3: destination)


def stand_ins(scripts=None):
    """-> {script: [scripts it loads]} - where a script with no text of its own "is".

    A stage script (06BLK02) sets flags and counters but prints nothing, so no row can
    stand for it. The scenes it loads (06BLK02A...) play while it is running, so the
    first row of any of them is the earliest a need on it can be counted satisfied - a
    proxy that may be early, never late, which is the safe side for a check.
    """
    scripts = scripts or _scripts()
    out = collections.defaultdict(list)
    for name, d in scripts.items():
        for m in LOAD.finditer(d):
            child = m.group(1).decode().upper()
            if child != name and child in scripts and child not in out[name]:
                out[name].append(child)
        # a hub's stage case: the scripts that case loads stand for it
        if re.fullmatch(r'\d\d[A-Z]+', name):
            for s, e, _var, _val in hub_regions(name, d):
                kids = [m.group(1).decode().upper() for m in LOAD.finditer(d, s, e)]
                out[(name, s)] = [k for k in kids if k != name and k in scripts]
            # and, last resort, the hub stands for what it loads: 11STG01 prints nothing
            # and loads nothing, but 11STG's own text is on screen when it runs
            for k in out.get(name, ()):
                out.setdefault(('loader', k), []).append(name)
    return dict(out)


def dependencies(scripts=None):
    """-> {('script', name) | ('block', name, start) | ('entry', name, offset):
              [(kind, label, [(name, block start or None), ...]), ...]}

    Names carry no extension. A block of None means "the script, wherever": the
    satisfier's file has no readable block table (25TOU00C).
    """
    scripts = scripts or _scripts()
    blocks_of = {}

    def block_of(name, off):
        if name not in blocks_of:
            got = _blocks_of(name)
            blocks_of[name] = got[2] if got else []
        return block_at(name, scripts[name], blocks_of[name], off)

    writes = collections.defaultdict(list)            # (var, val) -> [(name, block)]
    incs = collections.defaultdict(list)              # var -> [(name, block)]
    sets = collections.defaultdict(list)              # flag -> [(name, block)]
    for name, d in scripts.items():
        if name == WORLD_MAP:
            continue
        for m in SET.finditer(d):
            writes[(m.group(1)[0], m.group(2)[0])].append((name, block_of(name, m.start())))
        for m in INC.finditer(d):
            incs[m.group(1)[0]].append((name, block_of(name, m.start())))
        for m in re.finditer(rb'\x1d([\x00-\xff])\x00', d, re.S):
            sets[m.group(1)[0]].append((name, block_of(name, m.start())))

    def writers(var, floor, exact=False):
        out = [w for (v, n), ws in writes.items() if v == var
               and (n == floor if exact else n >= floor) for w in ws]
        if not exact:
            out += incs.get(var, [])
        return sorted(set(out), key=BLOCK_KEY)

    out = collections.defaultdict(list)
    # load: a hub's stage switch, followed down through whatever those scripts load
    hubs = {n: hub_cases(d) for n, d in scripts.items() if re.fullmatch(r'\d\d[A-Z]+', n)}
    #   need[script] lists the ways it gets loaded: (var, val, via), or None for a way
    #   that waits for nothing - stage 0, or a switch on a register nobody resolved. One
    #   such way and the script needs nothing at all: 02OLB01 is loaded at Albein's stage
    #   0 as well as its stage 1, so its first-meeting scenes come before the manor.
    need = collections.defaultdict(list)
    for hub, cases in hubs.items():
        for var, val, child in cases:
            if child in scripts:
                #  a case on a scratch register or an engine variable (0x4, the counter
                #  every area writes) is not a stage: 17DRL loads 17DRL04 at `0x4 == 6`
                #  as well as at its stages 3-8, and every write of 0x4 in the game is
                #  not what dates it
                real = var not in LOCAL_SKIP and var >= LOW_VARS and val
                need[child].append((var, val, hub) if real else None)
    loads = collections.defaultdict(set)
    for name, d in scripts.items():
        if name in hubs:
            continue
        for m in LOAD.finditer(d):
            child = m.group(1).decode().upper()
            if child != name and child in scripts:
                loads[name].add(child)
    for _round in range(4):
        for parent, kids in loads.items():
            for kid in kids:
                for way in need.get(parent, ()):
                    if way is None:
                        if None not in need[kid]:
                            need[kid].append(None)
                    elif not any(w and w[:2] == way[:2] for w in need[kid]):
                        need[kid].append((way[0], way[1], parent))
    for child, reqs in need.items():
        if None in reqs:
            continue
        # loaded at several stages: it plays from the earliest, so every alternative is
        # a satisfier of one need
        alts = sorted({w for var, val, _via in reqs for w in writers(var, val, exact=True)}, key=BLOCK_KEY)
        if alts:
            out[('script', child)].append(('load', tuple(sorted({(v, n) for v, n, _w in reqs})), alts))
    # visit: an area's visit n+1 comes after its visit n - every script a hub loads at
    # a later value of its own counter, after the whole of what it loads at the earlier
    # one (scripts loaded at both stay out of it). Always true of the sheet as sorted;
    # what it adds is that a visit moved by the play order takes the later visits with it
    for hub, cases in hubs.items():
        var = stage_var(hub)
        stages = collections.defaultdict(set)
        for v, val, child in cases:
            if v == var and child in scripts:
                stages[val].add(child)
        visits, seen_sets = [], []
        for val in sorted(stages):
            key = frozenset(stages[val])
            if key not in seen_sets:
                seen_sets.append(key)
                visits.append(set(stages[val]))
        for earlier, later in zip(visits, visits[1:]):
            both = earlier & later
            for child in later - both:
                for prev in sorted(earlier - both):
                    out[('script', child)].append(('visit', (var, hub), [(prev, None)]))
    # stage and flag gates on an entry point
    for (sfn, entry), cond in all_conditions(scripts).items():
        name = sfn[:-4]
        if cond['stage']:
            var, floor = cond['stage']
            if var not in LOCAL_SKIP and var >= LOW_VARS and floor > 0:
                alts = writers(var, floor)
                if alts:
                    out[('entry', name, entry)].append(('stage', (var, floor), alts))
        for flag in cond['after']:
            if sets.get(flag):
                out[('entry', name, entry)].append(('flag', flag, sorted(set(sets[flag]), key=BLOCK_KEY)))
    # step: a script's own progress counter
    for name in sorted(scripts):
        var, steps = block_steps(name)
        if not var:
            continue
        for block, step in steps.items():
            if step:
                alts = [w for w in writers(var, step) if w[0] == name and w[1] != block]
                if alts:
                    out[('block', name, block)].append(('step', (var, step), alts))
    # chain: a milestone follows the milestone before it. Not for a hub with scripts of
    # its own: it runs on every visit, its "block" is the whole stage switch, and its
    # text is the arrival - 06BLK's name plate is in the block that starts Skus's stage
    # 7, and is shown on the first visit all the same.
    lone = {n for n in hubs if not any(m != n and m[:5] == n for m in scripts)}
    for key, groups in chain_groups().items():
        name, block = key[0][:-4], key[1]
        if name in hubs and name not in lone:
            continue
        for preds in groups:
            out[('block', name, block)].append(('chain', None, sorted({(p[0][:-4], p[1]) for p in preds}, key=BLOCK_KEY)))
    return dict(out)


def causal_order(units, needs):
    """Keep `units` in the given order except where a need says otherwise.

    `needs[u]` is a list of alternatives, each a set of units of which *one* has to come
    before u. The result is the given order with the fewest changes that satisfy every
    need: a unit is emitted as soon as it may be, and among the units that may be, the
    one that came first. That is a topological sort that breaks ties by the original
    order, so everything the placement got right stays where it was and only a unit
    that sat above something it depends on moves - down to just after it.

    -> (ordered units, [(unit, the unit it waited for, rows it moved down by)], cycles)

    A cycle - two scenes each gated on the other, which the scripts' shared flags can
    produce - cannot be satisfied; its earliest unit is emitted where it was and named.
    """
    import heapq
    index = {u: i for i, u in enumerate(units)}
    need = {}
    for u, alts in needs.items():
        if u in index:
            alts = [{v for v in alt if v in index and v != u} for alt in alts]
            if any(alts):
                need[u] = [alt for alt in alts if alt]
    # A unit that can never be satisfied - it waits, through however many others, on
    # something that waits on it - keeps its needs out of the sort and its place in the
    # order, rather than dragging everything it blocks to the end.
    possible = set(units) - set(need)
    while True:
        more = {u for u, alts in need.items() if u not in possible
                and all(alt & possible for alt in alts)}
        if not more:
            break
        possible |= more
    cycles = sorted((u for u in need if u not in possible), key=index.get)
    for u in cycles:
        del need[u]
    dependents = collections.defaultdict(set)
    for u, alts in need.items():
        for alt in alts:
            for v in alt:
                dependents[v].add(u)
    done, out, unblocked = set(), [], {}

    def ready(u):
        return all(alt & done for alt in need.get(u, ()))
    heap = [index[u] for u in units if ready(u)]
    heapq.heapify(heap)
    queued = set(heap)
    while heap:
        i = heapq.heappop(heap)
        u = units[i]
        done.add(u)
        out.append(u)
        for d in sorted(dependents.get(u, ()), key=index.get):
            if d not in done and index[d] not in queued and ready(d):
                heapq.heappush(heap, index[d])
                queued.add(index[d])
                unblocked[d] = u                 # what it was waiting for, last
    assert len(out) == len(units)
    position = {u: i for i, u in enumerate(out)}
    moved = [(v, behind, position[v] - index[v]) for v, behind in unblocked.items()
             if position[v] > index[v]]
    moved.sort(key=lambda m: -m[2])
    return out, moved, cycles


def main():
    scripts = _scripts()
    rank, events, cyclic = timeline(scripts)
    if cyclic:
        print('counter writes that could not be ordered (a cycle): %s'
              % ', '.join('%s#%d' % m for m in sorted(cyclic)))
    places = script_places(scripts)
    for n, (p, basis) in sorted(places.items(), key=lambda kv: (kv[1][0], kv[0])):
        print('%8.3f  %-10s %s' % (p, n, basis))


if __name__ == '__main__':
    main()
