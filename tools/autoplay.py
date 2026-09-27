"""Play Kuro no Ken forward on its own, headless, looking for new text.

There's no walkthrough to script from, so this searches. From the current
state it forks one trial per NPC and per trigger zone on the map, runs the
trials in parallel worker processes (each has its own np2core Machine), lets
each play out until the player has control again (reading every page, fighting
with god mode and kuro_test's command rotation), and commits to the trial that
showed the most never-before-seen text, or failing that, reached a map it hasn't
visited. Then it repeats. Every page read, in trials and on the committed path,
goes through kuro_test's checks, so this is "test the game" as far as it gets.

A rough map of the story (chapters of a PS1 longplay, same game flow):
mansion -> Albein (permit) -> Old Book Cave -> Boss 1 -> Walkreuz -> Hiko scene
-> Boss 2 -> Sea Troll -> Tavern -> Sorcerer Trio -> ...

    python tools/autoplay.py [--start STATE] [--steps N] [--name RUN] [--workers W]

Writes routes/<RUN>.json (the committed path), test_reports/<RUN>_report.txt
(deduplicated issues + transcript), and states/<RUN>_NN.np2core per step.

With --follow it plays along a recorded playthrough (docs/video_anchors.json) instead:
the next script of the route is what it wants, and routes/atlas.json - the map graph
and who-plays-what that every run so far learned - says how to get it: talk to the
person standing here whose stub opens that script, or take the first move of the
shortest known path to a map that plays it. Only when the atlas has no answer does it
fall back to trying everything.
"""
import argparse
import json
import collections
import multiprocessing as mp
import os
import sys
import time
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

UNVISITED_MAP_BONUS = 8      # worth as much as 8 new pages
REPEAT_PENALTY = 3           # per earlier commit of the same (map, target)
EOL = chr(10)
MAP_EXTS = ('.mp1', '.mp2', '.mpc', '.mp')


_ORIG_HEADS = {}


def _scripts_loaded(emu):
    """Which .SCN files are in the script slots right now, by header match.

    This is what ties a map to its text: the slot holds a file, and script_map.py
    says which dump rows that file prints.
    """
    global _ORIG_HEADS
    if not _ORIG_HEADS:
        import glob
        for path in glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN')):
            with open(path, 'rb') as f:
                _ORIG_HEADS[f.read(32)] = os.path.basename(path)
    out = []
    for off in (0, 0x1800, 0x3d00):
        name = _ORIG_HEADS.get(bytes(emu.read(0x26d80 + off, 32)))
        if name:
            out.append(name)
    return out


def _label(sig):
    """A stable name for a map we never caught the name of. crc32, not hash(), so the
    same map gets the same label in every run and the reports can be merged."""
    return 'map_%04x' % (zlib.crc32(repr(sig).encode()) & 0xffff)


def _looks_like_map(name):
    n = name.lower()
    return n.endswith(MAP_EXTS) or (n.startswith(('fld', 'ysk', 'olb', 'tni')) and '_' not in n)


# --- worker side ------------------------------------------------------------------
_W = None


def _worker_init():
    global _W
    from kuro_core import CoreEmu
    from kuro_test import Tester
    emu = CoreEmu()
    _W = Tester(emu=emu, log=lambda *a: None)


#  the story counters (docs/engine_notes.md, "Every area has its own stage counter"):
#  each only ever counts up, in small steps. Anything else in that range is scratch -
#  0x99 took 218 once and led the autoplayer into a shop doorway it never left.
STORY_COUNTERS = (0x84, 0x85, 0x86, 0x87, 0x88, 0x8b, 0x8c, 0x8d, 0x91, 0x93, 0x95, 0x99, 0x9c)
STORY_VARS = (0x16d8 << 4) + 0x6d2
STORY_BONUS = 30            # a move that advances a story counter beats any amount of new text


def story_counters(e):
    return tuple(int.from_bytes(bytes(e.read(STORY_VARS + 2 * v, 2)), 'little') for v in STORY_COUNTERS)


def current_area(e):
    """Global var 2: the number of the area the party is in - the same number the
    scripts carry as their prefix (02OLB.., 07CSL..), so 1 = the world map, 6 = the
    capital, 7 = the castle."""
    return int.from_bytes(bytes(e.read(STORY_VARS + 4, 2)), 'little')


def current_region(e):
    """Global var 4: the region (sub-map) within the area - the hubs and region builders
    set it (`20 04 00 <n>`): the capital's street is 0, its second map's shops 6 and 9,
    the castle's hall 0 and throne room 1."""
    return int.from_bytes(bytes(e.read(STORY_VARS + 8, 2)), 'little')


def map_id(area, region, sig):
    """The name of a map, from RAM alone: area number, region number and the zone
    layout's fingerprint, e.g. 0700_0bef for the castle's hall, 0609_74ea for a shop of
    the capital's second map. The last resource name is no identity (a sprite or a
    script overwrites it, a castle of several regions loads one file), and the zone
    layout alone is not either (a house interior reuses its map's), so a name that
    means the same in every run has to come from here."""
    return '%02d%02d_%04x' % (area, region & 0xff, zlib.crc32(repr(sig).encode()) & 0xffff)


def story_reset(before, after):
    """Did the game restart from the title? Then the counters are all back to zero (or
    the one the opening sets). A story write can lower one counter while raising
    others (11STG01 puts the manor's back to 1), so a single decrease is not it."""
    live_before = sum(1 for a in before if a)
    live_after = sum(1 for b in after if b)
    return live_before >= 3 and live_after <= live_before // 2 and sum(after) < sum(before) // 2


def story_advanced(before, after):
    """Did a real counter go up by a step (1..8), the way the story moves?"""
    return any(0 < b - a <= 8 and a < 32 for a, b in zip(before, after))


ROUTE_BONUS = 40            # the trial's dialogue is the next script of the recorded route
ROUTE_LOOKAHEAD = 3         # ...or one of the next few (a run the walker skipped, a revisit)
ROUTE_AREA_BONUS = 12       # no dialogue, but the trial lands in the next script's area


def recorded_route(series='twitch', least=2):
    """The scripts a recorded player went through, in order, from docs/video_anchors.json:
    the script runs of that series with at least `least` anchors, consecutive repeats
    folded. This is the walkthrough the follower plays along."""
    path = os.path.join(HERE, 'docs', 'video_anchors.json')
    anchors = sorted((a for a in json.load(open(path, encoding='utf-8'))['anchors']
                      if a.get('series', 'twitch') == series), key=lambda a: a['at'])
    runs = []
    for a in anchors:
        if runs and runs[-1][0] == a['script']:
            runs[-1][1] += 1
        else:
            runs.append([a['script'], 1])
    out, counts = [], []
    for script, n in runs:
        if n >= least and (not out or out[-1] != script):
            out.append(script)
            counts.append(n)
        elif n >= least:
            counts[-1] += n
    recorded_route.counts = counts          # anchors per entry: how big a scene the run was
    return out


def area_of_map(name):
    """'olb1.mp2' -> '02'; a scene or battle screen -> None."""
    from play_tour import MAP_AREA
    base = (name or '').replace('d\\', '').split('.')[0]
    if base[:2].isdigit():
        return base[:2]
    return MAP_AREA.get(base)


PLAN_BONUS = 20             # the trial is the planned move and lands where the plan said


class Atlas:
    """What every run learned about the world, kept in routes/atlas.json so a new run
    can plan from the first step: which move on which map leads where (`edges`), which
    move played which script (`plays`), which scene scripts the people of a map open
    (`holds`, from their talk stubs), and which area an unnamed map belongs to (`area`,
    from the scripts seen on it). Seeded from every routes/*_map.json, which record all
    trials of a run, not just the committed moves."""
    PATH = os.path.join(HERE, 'routes', 'atlas.json')

    def __init__(self):
        self.edges, self.plays, self.holds, self.area = {}, {}, {}, {}
        if os.path.exists(self.PATH):
            d = json.load(open(self.PATH, encoding='utf-8'))
            self.edges = {m: {mv: {d: n for d, n in ds.items() if self.is_map(d)} for mv, ds in e.items()}
                          for m, e in d.get('edges', {}).items() if self.is_map(m)}
            self.edges = {m: {mv: ds for mv, ds in e.items() if ds} for m, e in self.edges.items()}
            self.plays = {m: v for m, v in d.get('plays', {}).items() if self.is_map(m)}
            self.holds = {m: v for m, v in d.get('holds', {}).items() if self.is_map(m)}
            self.area = d.get('area', {})
        self.seed()

    @staticmethod
    def is_map(name):
        """A map name of the form the follower gives them (area, region, zone crc):
        anything else is an older run's name, or a resource mistaken for a map."""
        return bool(name) and len(name) == 9 and name[4] == '_' and name[:4].isdigit()

    #  what runs before 2026-09-25 called the maps whose fingerprints are known (states
    #  fo_*): the rest of their names name nothing the planner can reach and stay as is
    RENAME = {'fld1': '01_0aaa', 'olb1': '02_ece5', 'olb2': '02_2c3f', 'map_2c3f': '02_2c3f',
              'ysk1': '03_bca5', 'ysk2': '03_ed86', 'sks1': '05_5680', 'sks2': '05_10b6',
              'map_62e9': '06_62e9', 'csl4_62e9': '06_62e9', 'blk2': '06_74ea', 'map_74ea': '06_74ea',
              'blk3': '06_7a02', 'csl2': '07_0bef', 'csl2_e7ca': '07_e7ca', 'csl3': '07_ea0c',
              'csl4': '07_e65a', 'ckd': '08_09cb', 'tni1': '10_c2d1', 'csl3_1c26': '10_1c26',
              'stg': '11_0345'}

    def seed(self):
        import glob
        names = set()
        graphs = []
        for path in glob.glob(os.path.join(HERE, 'routes', '*_map.json')):
            g = json.load(open(path, encoding='utf-8')).get('graph', {})
            graphs.append(g)
            names |= {v['map'] for v in g.values()}
        for g in graphs:
            for v in g.values():
                if v['map'] == '?':
                    continue
                src_map = self.RENAME.get(v['map'], v['map'])
                if not self.is_map(src_map):
                    continue
                dest = self.RENAME.get(v.get('leads_to'), v.get('leads_to'))
                if self.is_map(dest):
                    self.edge(src_map, v['kind'], v['index'], dest)
                for src in v.get('text', ()):
                    self.played(src_map, v['kind'], v['index'], str(src[0])[:-4])

    def edge(self, src, kind, index, dest):
        if self.is_map(dest) and self.is_map(src) and dest != src:
            seen = self.edges.setdefault(src, {}).setdefault('%s|%d' % (kind, index), {})
            seen[dest] = seen.get(dest, 0) + 1

    def dests(self, src, move):
        return self.edges.get(src, {}).get(move, {})

    def played(self, src, kind, index, script):
        if len(script) < 4 or not script[:2].isdigit():      # a page with no script behind it
            return
        moves = self.plays.setdefault(src, {}).setdefault(script, [])
        move = '%s|%d' % (kind, index)
        if move not in moves:
            moves.append(move)
        self.saw(src, script)

    def held(self, src, script):
        if script not in self.holds.setdefault(src, []):
            self.holds[src].append(script)
        self.saw(src, script)

    def saw(self, src, script):
        from play_tour import MAP_AREA
        if src.startswith('map_') and script[:2] in MAP_AREA.values():
            self.area.setdefault(src, script[:2])

    @staticmethod
    def name(area, region, sig):
        return map_id(area, region, sig)

    def area_of(self, name):
        return area_of_map(name) or self.area.get(name)

    def where_plays(self, script):
        """The maps known to play a script, by a move or through a person."""
        return sorted({m for m, d in self.plays.items() if script in d} | {m for m, l in self.holds.items() if script in l})

    def maps_of_area(self, area):
        return sorted(m for m in set(self.edges) | {d for e in self.edges.values() for ds in e.values() for d in ds}
                      if self.area_of(m) == area)

    def path(self, src, goals, avoid=()):
        """Shortest path of moves from src to any of goals -> [(map, (kind, index), dest)]."""
        goals = set(goals) - {src}
        if not goals:
            return []
        prev, queue = {src: None}, collections.deque([src])
        while queue:
            m = queue.popleft()
            for move, ds in self.edges.get(m, {}).items():
                if (m, move) in avoid:
                    continue
                for dest in sorted(ds, key=ds.get, reverse=True):
                    if dest in prev:
                        continue
                    prev[dest] = (m, move)
                    if dest in goals:
                        out = []
                        while prev[dest]:
                            m0, mv = prev[dest]
                            kind, idx = mv.split('|')
                            out.append((m0, (kind, int(idx)), dest))
                            dest = m0
                        return out[::-1]
                    queue.append(dest)
        return None

    def save(self):
        with open(self.PATH, 'w', encoding='utf-8') as f:
            json.dump({'edges': self.edges, 'plays': self.plays, 'holds': self.holds, 'area': self.area},
                      f, indent=1, sort_keys=True)


_STAGE = __import__('re').compile(r'^(\d\d)[A-Z]+(\d\d)')


def stage_needed(script):
    """'06BLK02A' -> (6, 2): the capital's second stage. None for a script with no
    stage in its name (12MRS, 99CMN)."""
    m = _STAGE.match(script)
    return (int(m.group(1)), int(m.group(2))) if m else None


_SETTERS = {}
_HUBS = {}
_STAGES = {}


def _hub_walk(d, counter, value, limit=600):
    """Follow a hub script from its first byte with the area's counter at `value`
    (every other variable 0, every flag clear) until it loads a stage script into slot
    0x1800, and return (that script's name, the scene scripts the same straight run
    loads into slot 0x3d00 - 02OLB's hub loads 02olb01a right after 02olb01); (None,
    set()) if it ends or gets lost first. The hubs
    pick the stage script in their first bytes by a switch on the counter (06BLK) or a
    chain of compares (07CSL, 15MKR: `jne 91 0 -> 15mkr01a, jg 91 2 -> 15mkr01b ...`),
    which no fixed pattern reads reliably (05SKS's head has a resource string in it)."""
    import struct
    import scn_disasm
    lay = scn_disasm.LAY
    vals = {counter: value}
    pc, stack = 0, []
    stage, scenes = None, set()

    def tagged(q):
        t = d[q]
        if t in (0, 1):
            v = struct.unpack('<H', d[q + 1:q + 3])[0]
            return (v if t == 0 else vals.get(v, 0)), q + 3
        return None, q + 1

    def skip(q, kinds):
        for kind in kinds:
            if kind == 'word':
                q += 2
            elif kind == 'byte':
                q += 1
            elif kind == 'tagged':
                _v, q = tagged(q)
            elif kind == 'switch':
                q += 2
                _v, q = tagged(q)
                n = d[q]
                q += 1
                for _ in range(n):
                    _v, q = tagged(q)
            elif kind == 'table':
                q += 1 + 2 * d[q]
            elif kind == 'str':
                q = d.index(b'\x00', q + 1) + 1
            else:
                q = d.index(b'\x00', q) + 1
        return q
    for _ in range(limit):
        if pc >= len(d):
            break
        op = d[pc]
        if op == 0x39:                                      # load <slot> 02 <name>
            slot, q = tagged(pc + 1)
            e = d.index(b'\x00', q + 1)
            name = d[q + 1:e].decode('ascii', 'replace').lower()
            if name.endswith('.scn'):                       # 16MKI's loads name the file
                name = name[:-4]
            if slot == 0x1800 and stage is None:
                stage = name
            elif slot == 0x3d00 and stage is not None:
                scenes.add(name)
            pc = e + 1
        elif op == 0x09:
            if stage is not None:                           # the straight run after the load is over
                break
            pc = struct.unpack('<H', d[pc + 1:pc + 3])[0]
        elif op == 0x04:
            tgt = struct.unpack('<H', d[pc + 1:pc + 3])[0]
            if tgt < 0x1800:
                stack.append(pc + 3)
                pc = tgt
            else:
                pc += 3
        elif op == 0x07:
            if not stack:
                break
            pc = stack.pop()
        elif op == 0x83:
            break
        elif op in (0x06, 0x0b):                            # switch var default n entries
            var = struct.unpack('<H', d[pc + 1:pc + 3])[0]
            dflt, q = tagged(pc + 3)
            n = d[q]
            q += 1
            entries = []
            for _ in range(n):
                v, q = tagged(q)
                entries.append(v)
            idx = vals.get(var, 0)
            tgt = entries[idx] if 0 <= idx < n else dflt
            if tgt is None or stage is not None:
                break
            pc = tgt
        elif 0x10 <= op < 0x1c:                             # compare, branch if true
            a = vals.get(struct.unpack('<H', d[pc + 1:pc + 3])[0], 0)
            b = struct.unpack('<H', d[pc + 3:pc + 5])[0]
            if op & 1:
                b = vals.get(b, 0)
            tgt = struct.unpack('<H', d[pc + 5:pc + 7])[0]
            cond = {0x10: a != b, 0x12: a == b, 0x14: a <= b, 0x16: a < b, 0x18: a > b, 0x1a: a >= b}[op & 0x1e]
            pc = tgt if cond else pc + 7
        elif op == 0x0c:                                    # branch if flag set: never
            pc += 5
        elif op == 0x0d:                                    # branch if flag clear: always
            pc = struct.unpack('<H', d[pc + 3:pc + 5])[0]
        elif op in (0x1f, 0x20, 0x21, 0x22, 0x23) or 0x28 <= op < 0x30:
            var = struct.unpack('<H', d[pc + 1:pc + 3])[0]
            if op == 0x1f:
                vals[var] = 0
                pc += 3
            elif op == 0x22:
                vals[var] = vals.get(var, 0) + 1
                pc += 3
            elif op == 0x23:
                vals[var] = vals.get(var, 0) - 1
                pc += 3
            else:
                b = struct.unpack('<H', d[pc + 3:pc + 5])[0]
                if op == 0x21 or (op & 1 and op >= 0x28):
                    b = vals.get(b, 0)
                if op in (0x20, 0x21):
                    vals[var] = b
                elif op in (0x28, 0x29):
                    vals[var] = vals.get(var, 0) + b
                elif op in (0x2a, 0x2b):
                    vals[var] = vals.get(var, 0) - b
                elif op in (0x2c, 0x2d):
                    vals[var] = vals.get(var, 0) & b
                elif op in (0x2e, 0x2f):
                    vals[var] = vals.get(var, 0) | b
                pc += 5
        elif op in lay:
            pc = skip(pc + 1, lay[op])
        else:
            break
    return stage, scenes


def _hub_tables(area):
    import glob
    if area not in _HUBS:
        loads, scenes = {}, {}
        paths = [q for q in glob.glob(os.path.join(HERE, 'original', 'decompressed', '%02d???.SCN' % area))
                 if len(os.path.basename(q)) == 9]
        if paths:
            d = open(paths[0], 'rb').read()
            for v in range(16):
                name, sc = _hub_walk(d, 0x82 + area, v)
                if name:
                    loads[v] = name
                    scenes[v] = sc
        _HUBS[area] = (loads, scenes)
    return _HUBS[area]


def hub_loads(area):
    """An area hub's counter value -> the stage script it loads into slot 0x1800, by
    walking the hub for each value 0..15: 06BLK loads 06blk01 at 0 and 06blk02 at 1,
    07CSL 07csl01 at 0 and 1 and 07csl02 at 2, 15MKR 15mkr01a at 0, 15mkr01b at 1 and
    2, 15mkr01c at 3..5. {} for an area with no hub or no staged load."""
    return _hub_tables(area)[0]


def hub_scenes(area):
    """Counter value -> the scene scripts the hub itself loads on the way (02OLB loads
    02olb01a at 0, 02olb01b at 1, 02olb02a at 2 ...); {} where the stage scripts do it."""
    return _hub_tables(area)[1]


def stage_scripts_of(area, script, _seen=None):
    """The stage scripts (slot 0x1800, lowercase) whose residency lets `script` play:
    itself when it is one (15MKR01B), else the stage scripts that load it into the scene
    slot (06BLK03 loads 06blk03i) - through another scene when only a scene loads it.
    None when nothing constrains it: no loader is known. A scene the hub itself loads
    is constrained by hub_scenes instead (resident_values reads both)."""
    import glob
    key = (area, script.lower())
    if key in _STAGES:
        return _STAGES[key]
    _seen = _seen or set()
    _seen.add(key)
    low = script.lower()
    stages = set(hub_loads(area).values())
    if low in stages:
        result = {low}
    else:
        pats = [b'\x39\x00\x00\x3d\x02' + low.encode() + tail for tail in (b'\x00', b'.scn\x00')]
        result = set()
        unconstrained = False
        for path in sorted(glob.glob(os.path.join(HERE, 'original', 'decompressed', '%02d*.SCN' % area))):
            name = os.path.basename(path)[:-4]

            data = open(path, 'rb').read().lower()         # 08CKD01 loads 08CKD01A in capitals
            if name.lower() == low or not any(pat in data for pat in pats):
                continue
            if len(name) == 5:                              # the hub itself: hub_scenes has it
                continue
            elif name.lower() in stages:
                result.add(name.lower())
            elif (area, name.lower()) not in _seen:
                sub = stage_scripts_of(area, name, _seen)
                if sub is None:
                    unconstrained = True
                else:
                    result |= sub
        if unconstrained or not result:
            result = None
    _STAGES[key] = result
    return result


def resident_values(area, script):
    """The counter values at which `script` can be resident, or None when any will do
    (nothing is known to load it)."""
    low = script.lower()
    values = {v for v, sc in hub_scenes(area).items() if low in sc}
    stages = stage_scripts_of(area, script)
    if stages is not None:
        values |= {v for v, name in hub_loads(area).items() if name in stages}
    return values or None


def script_area(script):
    return int(script[:2]) if script[:2].isdigit() else None


def stage_setters(area, script, have=None):
    """The scripts that write a counter value at which `script` can be resident
    (`20 <var> 00 <value> 00`, or `22 <var> 00` when the next value is one; 11STG01
    writes the 1 that opens the capital's stage 2, 07CSL02's audience the 2 that opens
    the castle's third stage, the dungeon's prison sequence the 1 that Makrun's
    15mkr01b needs) - docs/engine_notes.md, 'who advances the counter from outside the
    area' - with the scene scripts of their own stage after them, since the write
    usually sits inside one of those talks."""
    import glob
    values = resident_values(area, script) or set()
    key = (area, tuple(sorted(values)), have)
    if key not in _SETTERS:
        out = []
        pats = [bytes([0x20, 0x82 + area, 0x00, v & 0xff, 0x00]) for v in sorted(values)]
        if have is not None and have + 1 in values:
            pats.append(bytes([0x22, 0x82 + area, 0x00]))
        for path in sorted(glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN'))):
            name = os.path.basename(path)[:-4]

            data = open(path, 'rb').read()
            if any(pat in data for pat in pats) and name not in out:
                out.append(name)
                if stage_needed(name):
                    out += [os.path.basename(q)[:-4] for q in sorted(glob.glob(path[:-4] + '?.SCN'))]
        _SETTERS[key] = out
    return _SETTERS[key]


def stage_of(e, area):
    """An area's stage counter: variable 0x82 + the area number (docs/engine_notes.md,
    'Every area has its own stage counter')."""
    return int.from_bytes(bytes(e.read(STORY_VARS + 2 * (0x82 + area), 2)), 'little')


def buff(e):
    """God mode for the text's sake: every party member's maximum HP and MP raised so
    the fights the story starts (the capital's guards at stage 2, the prison monster
    whose round can take 300 HP) cannot wipe the party, then healed. The follower
    tests the story, not the balance."""
    from kuro_emu import STAT_HP, PARTY_STRIDE
    for k in (-1, 0):                       # Kaies, then the second member (kuro_emu.heal)
        base = STAT_HP + k * PARTY_STRIDE
        if 0 < e.word(base + 4) < 900:
            e.write(base + 4, (999).to_bytes(2, 'little'))
            e.write(base + 12, (999).to_bytes(2, 'little'))
    e.heal()


def frozen(e):
    """Is the game hung? The script interpreter fetches nothing for half a second (a
    hang has the CPU off in the interrupt vector table; a live field loop fetches
    every frame - Drl's village read as frozen once because the party stood in a
    wall after a failed walk), nothing on screen changes, and a step in two
    directions moves the party nowhere. The steps are taken on a snapshot that is
    restored afterwards: a party that has just arrived on a map stands on the way back
    out, and one step would leave again (the capital's gate did, every time)."""
    from kuro_emu import BD_SEG
    fetch = (BD_SEG << 4) + 0x33bb
    e.m.hook(fetch)
    e.m.events()
    a = e.image().tobytes()
    e.wait(0.5)
    n = len(e.m.events())
    e.m.unhook(fetch)
    if n or e.image().tobytes() != a:
        return False
    snap = e.m.save_state()
    try:
        p = e.pos()
        for key in ('DOWN', 'LEFT'):
            e.tap(key, 0.15)
            e.wait(0.25)
            if e.pos() != p or e.state() != 'field':
                return False
        return e.image().tobytes() == a
    finally:
        e.m.load_state(snap)
        e._last_lines = None


def _trial(args):
    """Run one target from a base state. Returns everything the parent needs."""
    from kuro_emu import Blocked
    from kuro_emu import Blocked
    from kuro_test import GameOver
    base, target = args
    t, e = _W, _W.emu
    e.m.load_state(zlib.decompress(base))
    e._last_lines = None
    t.pages, t.issues = [], []
    e.set_noclip(True)
    buff(e)
    outcome = 'ok'
    t0 = time.time()
    try:
        kind, idx = target
        if kind == 'npc':
            t.talk_to(idx)
        else:
            #  the walk to a zone: on a town map the straight line with no-clip, then, if
            #  that is blocked (a door in a wall the line crosses badly, a counter), by
            #  standing beside the zone and stepping in from each side; on the world map
            #  (no no-clip there) the sides straight away
            from kuro_emu import OBJ_TABLE, OBJ_ANCHOR
            z = next(z for z in e.zones() if z['kind'] == kind and z['index'] == idx)
            cx, cy = (z['x1'] + z['x2']) // 2, (z['y1'] + z['y2']) // 2
            px, py = e.pos()
            first = (('DOWN' if py < cy else 'UP') if abs(py - cy) >= abs(px - cx)
                     else ('RIGHT' if px < cx else 'LEFT'))
            sides = [first] + [k for k in ('DOWN', 'UP', 'RIGHT', 'LEFT') if k != first]
            attempts = ([None] if current_area(e) != 1 else []) + sides
            here = e.m.save_state()
            for n_try, approach in enumerate(attempts):
                if n_try:
                    e.m.load_state(here)
                    e._last_lines = None
                if approach is not None:
                    sx, sy = {'DOWN': (cx, z['y1'] - 6), 'UP': (cx, z['y2'] + 6),
                              'RIGHT': (z['x1'] - 6, cy), 'LEFT': (z['x2'] + 6, cy)}[approach]
                    e.write(OBJ_TABLE + 4, (sx + OBJ_ANCHOR[0]).to_bytes(2, 'little'))
                    e.write(OBJ_TABLE + 6, (sy + OBJ_ANCHOR[1]).to_bytes(2, 'little'))
                    e.wait(0.3)
                try:
                    t.goto_zone(idx, kind=kind, approach=approach, timeout=20)
                    break
                except Blocked as ex:
                    if n_try == len(attempts) - 1 or 'did nothing' in str(ex):
                        raise
            if e.state() == 'dos':
                #  the game quit to DOS: a no-clip walk that put the party inside the
                #  scenery does that (six zones of Mki's map 1601_3de3 did, none of
                #  them without the cheat) - once more, walls respected
                e.m.load_state(here)
                e._last_lines = None
                e.set_noclip(False)
                try:
                    t.goto_zone(idx, kind=kind, approach=approach, timeout=20)
                except Blocked as ex:
                    raise Blocked('quit to DOS with no-clip; without it ' + str(ex)[:40])
        #  360 s: the prison monster's fight takes 30 rounds even with the skills
        t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 360})
    except GameOver:
        outcome = 'gameover'
    except Blocked as ex:
        outcome = f'blocked: {str(ex)[:60]}'
    except Exception as ex:          # never let one trial kill the pool
        outcome = f'error: {type(ex).__name__}: {str(ex)[:80]}'
    st = e.state()
    #  the party died and the game is at its title (or already reloading its save):
    #  the counters still read as before, so the title menu itself is the sign
    m = e.menu()
    if m and t._is_title(m):
        outcome = 'gameover'
    for _ in range(12):              # a map transition may still be finishing
        if st == 'dos' or (st == 'field' and len(e.zones()) <= AutoPlayer.MAX_REAL_ZONES):
            break
        e.wait(0.5)
        st = e.state()
    field = st == 'field' and len(e.zones()) <= AutoPlayer.MAX_REAL_ZONES   # not a scene/battle
    if field and frozen(e):
        #  a hang: the screen no longer changes and the party cannot move (Makrun's
        #  shop doors, entered before the story sets the town up) - as bad as a crash
        outcome, field = 'FROZEN', False
    return {
        'target': target, 'outcome': 'CRASH' if st == 'dos' else outcome, 'state': st,
        'counters': story_counters(e),
        'area': current_area(e), 'region': current_region(e),
        'pages': [(m, src, lines) for m, src, lines in t.pages],
        'issues': list(t.issues),
        'sig': (e.map_sig(), current_region(e)) if field else None,
        'map': e.map_name(),
        'after': None if st == 'dos' else zlib.compress(e.m.save_state(), 1),
        'secs': round(time.time() - t0, 1),
    }


# --- parent side ------------------------------------------------------------------
class AutoPlayer:
    def __init__(self, name, start=None, workers=10, log=print):
        from kuro_core import CoreEmu
        from kuro_test import Tester
        self.name, self.log = name, log
        self.route_plan, self.route_i = [], 0          # the recorded route, and where we are in it
        self.route_counts = []                          # anchors per route entry
        self.window = []                                # this step's [(script, kind, route index)]
        self.atlas = Atlas()
        self.bad_moves = {}          # (map, "kind|index") -> step at which it did not go where the atlas said
        self.dull = 0                # committed steps in a row that brought nothing
        self.tried = {}              # (map, script) -> step at which its hinted moves there played nothing
        self.debts = []              # scripts the route pointer skipped past, still wanted: [(script, step, index)]
        self.step_n = 0
        self.start_state, self.last_commit_sig = start, None
        self.state_sigs, self.state_moves = {}, {}
        self.emu = CoreEmu()
        self.t = Tester(emu=self.emu, log=lambda *a: None)
        self.seen = set()
        self.maps = {}                # signature -> readable name
        self.last_map_name = '?'
        self.commits = {}
        self.hung = set()            # (map, target) whose trial never returned
        self.states = []             # saved states, newest last: the rollback stack
        self.last_commit = None      # (map, target) of the move we are now playing out
        self.visits = collections.Counter()   # map signature -> committed steps spent there
        self.graph = {}              # "map|kind|index" -> what that target did
        self.coverage = {}           # script file -> {offset: [maps it was seen on]}
        self.map_files = {}          # map name -> the .SCN files loaded on it
        self._last_sig = None
        self.workers = workers
        self.issues = {}              # (kind, detail) -> context, deduplicated
        self.transcript = []          # committed pages, in order
        self.route = {'start': {'state': start} if start else {'new_game': True}, 'steps': []}
        if start:
            self.emu.load_state(start)
            # A state saved mid-scene (hundreds of "zones") is not somewhere we can
            # play from, and a scene that ends in a fight will just kill us on step 1.
            if self.emu.state() != 'field' or len(self.emu.zones()) > self.MAX_REAL_ZONES:
                self.log('start state is not on a map; letting it play out first')
                self._settle_until_map()
        else:
            self.t.start({'new_game': True})
            self.t.run_step({'op': 'wait_field', 'timeout': 240})
        self._absorb(self.t.pages, self.t.issues, committed=True)
        self._remember_map()
        self.pool = mp.Pool(workers, initializer=_worker_init)

    def _scripts_said(self, pages):
        """The scripts a trial's dialogue came from. A page matched to the English is
        named already; on the original disk the pages are Japanese and unmatched, so
        each line is looked up in the workbook's Japanese instead."""
        out = collections.Counter()
        for _m, src, lines in pages:
            if src:
                out[str(src[0])[:-4]] += 1
                continue
            for line in lines:
                hit = self.t.script.find_japanese(line)
                if hit:
                    out[str(hit[0])[:-4]] += 1
                    break
        return out

    def _key(self, lines):
        """Identity of a page for novelty: digits are collapsed, so a counter or a
        gold/HP readout doesn't look like endless new text."""
        import re
        from kuro_test import normalize
        return re.sub(r'\d+', '#', normalize(' '.join(l.strip() for l in lines)))

    def _absorb(self, pages, issues, committed):
        new = 0
        for m, src, lines in pages:
            k = self._key(lines)
            if k and k not in self.seen:
                self.seen.add(k)
                new += 1
                if committed:
                    self.transcript.append((m, src, lines))
        for kind, detail, ctx in issues:
            self.issues.setdefault((kind, detail), ctx)
        return new

    def _remember_map(self):
        name = self.emu.map_name()
        if _looks_like_map(name):
            self.last_map_name = name.split('.')[0]
        if self.emu.state() == 'field':
            sig = (self.emu.map_sig(), current_region(self.emu))
            self.maps.setdefault(sig, map_id(current_area(self.emu), sig[1], sig[0]))
            for fn in _scripts_loaded(self.emu):
                if fn not in self.map_files.setdefault(self.maps[sig], []):
                    self.map_files[self.maps[sig]].append(fn)
            return sig
        return None

    MAX_REAL_ZONES = 80      # a real map has a few dozen; hundreds = not a map (a scene, a battle)

    def targets(self):
        zones = self.emu.zones()
        if len(zones) > self.MAX_REAL_ZONES:
            return None
        out = [('npc', o['slot']) for o in self.emu.objects()]
        out += [(z['kind'], z['index']) for z in zones if z['enabled']]
        return out

    def _settle_until_map(self):
        """Let a scene play out until the game is on a real map again."""
        #  (no ESC on a menu here: on the field ESC *opens* the status screen, whose HP
        #  and MP rows read as a battle that never offers a menu - which is how a whole
        #  run of "battle made no progress" rewinds came about)
        from kuro_emu import Blocked
        for _ in range(10):
            m = self.emu.menu()
            if m and self.t._is_title(m):
                from kuro_test import GameOver
                raise GameOver()
            try:
                self.t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 120})
            except Blocked as ex:
                #  a status screen read as a battle: one ESC closes it
                if 'battle' not in str(ex):
                    raise
                self.emu.tap('ESC', 0.1)
                self.emu.wait(0.8)
                if self.emu.state() != 'field':
                    raise
                self.log('  (the status screen read as a battle; closed it)')
            if len(self.emu.zones()) <= self.MAX_REAL_ZONES and self.emu.state() == 'field':
                return True
            self.emu.wait(2)
        return False

    def _learn_here(self, here_name):
        """Which scene scripts the people standing here open (their talk stubs name the
        scene and the entry), into the atlas - and back as {slot: scene}."""
        import npc_photos as np_
        out = {}
        try:
            for slot, _sprite, _x, _y, talk in np_.people(self.emu):
                for scene, _entry in np_.resolve_live(self.emu, talk):
                    out[slot] = scene
                    self.atlas.held(here_name, scene)
        except Exception as ex:                    # noqa: BLE001 - a hint, never a stop
            self.log('  (could not read the talk stubs: %s)' % str(ex)[:60])
        return out

    def _window(self):
        """The scripts to look for: the debts first - scripts the pointer skipped past
        when a later one matched, which may be what the story needed (12MRS before the
        capital's second stage) - then the next of the route. Three of those, unless
        each was already tried where it is known to play (a run of the recorded
        player's that this playthrough cannot reproduce - a revisit, a shop): then the
        window widens so the route can be picked up further on."""
        entries = [(sc if self._stage_ok(sc) else (self._stage_alias(sc) or sc), 'debt', idx) for sc, _, idx in self.debts]
        for size in (ROUTE_LOOKAHEAD, 2 * ROUTE_LOOKAHEAD, 3 * ROUTE_LOOKAHEAD):
            window = self.route_plan[self.route_i:self.route_i + size]
            for sc in window:
                maps = self.atlas.where_plays(sc)
                if not maps or any((m, sc) not in self.tried for m in maps):
                    break
            else:
                continue
            break
        #  a script of a stage its area has not reached cannot play yet (the hub loads
        #  the stage's script by its counter), so first the scripts that write the
        #  missing counter values - a talk in the castle at its stage 2 sets the
        #  capital's - and the scenes of their stage, where that talk lives
        #  a script of another stage whose lines mostly exist in a script of the current
        #  stage is that script as far as the video could tell (06BLK03I shares 27 of
        #  its 72 lines with 06BLK02I): the pointer takes the sibling in its place
        window = [sc if self._stage_ok(sc) else (self._stage_alias(sc) or sc) for sc in window]
        ready = [(sc, 'route', self.route_i + k) for k, sc in enumerate(window) if self._stage_ok(sc)]
        if window and not self._stage_ok(window[0]):
            area = script_area(window[0])
            have = stage_of(self.emu, area) & 0xff
            setters = [sc for sc in stage_setters(area, window[0], have) if self._stage_ok(sc)]
            #  the hub itself as the writer (15MKR sets 0x91 := 3 once a sub-counter its
            #  stage script's talks advance, var 0x42, has reached 6): nothing to play
            #  there but the resident stage script and its scenes, so those stand in
            if any(len(sc) == 5 for sc in setters):
                import glob
                resident = hub_loads(area).get(have, '')
                stand_ins = [os.path.basename(q)[:-4] for q in sorted(glob.glob(
                    os.path.join(HERE, 'original', 'decompressed', resident.upper() + '?.SCN')))] if resident else []
                stand_ins = [resident.upper()] + stand_ins if resident else []
                setters = [sc for sc in setters if len(sc) != 5] + [sc for sc in stand_ins if sc not in setters]
            if setters and setters != getattr(self, '_redo', None):
                self._redo = setters
                self.log("  route: %s needs area %d's counter in %s (it is %d, which loads %s); first %s, which set it"
                         % (window[0], area, sorted(resident_values(area, window[0])), have,
                            hub_loads(area).get(have), setters))
            return entries + [(sc, 'setter', None) for sc in setters] + ready
        return entries + ready

    def _stage_alias(self, script):
        """The same-area script, resident at the current stage, that shares the most of
        `script`'s lines - when it shares at least a quarter of them; else None."""
        lines = self._lines_of()
        mine = lines.get(script)
        if not mine:
            return None
        best, best_n = None, 0
        for other, theirs in lines.items():
            if other == script or other[:2] != script[:2] or not self._stage_ok(other):
                continue
            n = len(mine & theirs)
            if n > best_n:
                best, best_n = other, n
        return best if best_n * 4 >= len(mine) else None

    def _lines_of(self):
        """script -> set of its Japanese lines (of 4 characters or more), from the workbook."""
        if not hasattr(self, '_lines'):
            self._lines = {}
            for jp, fn, _off, _has_en in self.t.script.japanese:
                if len(jp) >= 4:
                    self._lines.setdefault(str(fn)[:-4], set()).add(jp)
        return self._lines

    def _stage_ok(self, script):
        """Can this script be resident now? The area's counter (low byte) must be one
        of the values at which the hub loads a stage script that is, or loads, this one
        (resident_values). A script nothing constrains - no area, no hub, the hub loads
        it at every stage - always."""
        area = script_area(script)
        if area is None:
            return True
        values = resident_values(area, script)
        return values is None or (stage_of(self.emu, area) & 0xff) in values

    def _pages_needed(self, kind, index):
        if kind != 'route' or index is None or index >= len(self.route_counts):
            return 1
        return min(4, max(1, self.route_counts[index] // 30))

    def _route_hit(self, hit, said, moved=False):
        """A trial played the script at index `hit` of the window: a debt is paid, a
        prerequisite was met, or the pointer moves past a route script and what it
        skipped becomes a debt."""
        script, kind, index = self.window[hit]
        if kind == 'debt':
            #  paid. When it moved a story counter, what the pointer matched after
            #  skipping it was premature (the story wanted them in the recorded order)
            #  and the pointer goes back to just after it; a debt that was only a
            #  revisit (a shop, a guard) leaves the pointer where it is
            self.debts = [d for d in self.debts if d[2] != index]
            if moved:
                self.route_i = min(self.route_i, index + 1)
                self.debts = [d for d in self.debts if d[2] < self.route_i]
                self.log('  route: debt %s paid and the story moved; back to %d/%d, next %s' % (script, self.route_i, len(self.route_plan), self.route_plan[self.route_i]))
            else:
                self.log('  route: debt %s paid (%d left)' % (script, len(self.debts)))
            return
        if kind == 'setter':
            self.log('  route: prerequisite %s played' % script)
            return
        skipped = [(sc, self.step_n, self.route_i + k) for k, sc in enumerate(self.route_plan[self.route_i:index])
                   if sc not in said and sc not in {d for d, _, _ in self.debts}]
        self.debts = (self.debts + skipped)[-4:]
        self.route_i = index + 1
        nxt = self.route_plan[self.route_i] if self.route_i < len(self.route_plan) else 'the end'
        self.log('  route: %d/%d done, next %s%s' % (self.route_i, len(self.route_plan), nxt,
                 '; owed: %s' % ', '.join(sc for sc, _, _ in self.debts) if self.debts else ''))

    def _preferred(self, here_name, targets):
        """What the route wants next, if the atlas knows how: [(why, [targets], check)]
        where check(result) says whether the trial did what was wanted."""
        if not self.route_plan or self.route_i >= len(self.route_plan):
            return []
        out = []
        #  people standing here whose talk opens the next script (or one of the next few)
        window = [sc for sc, _, _ in self.window]
        who = self._learn_here(here_name)
        slots = [('npc', slot) for slot, scene in sorted(who.items()) if scene in window and ('npc', slot) in targets]
        #  ...and the moves that played one of them here in an earlier run
        for want in window:
            for move in self.atlas.plays.get(here_name, {}).get(want, []):
                kind, idx = move.split('|')
                tg = (kind, int(idx))
                if tg in targets and tg not in slots:
                    slots.append(tg)
        fresh = [sc for sc in window if self.step_n - self.tried.get((here_name, sc), -99) > 15]
        slots = slots[:6]
        slots = [tg for tg in slots if self.commits.get((self._last_sig, tg), 0) < 3]
        if slots and fresh:
            out.append(('talk to %s for %s' % (slots, window[0]), slots, lambda r: r.get('route_hit') is not None))
        #  a wanted script of this very area, not yet looked for here: no shortcut out,
        #  every move of this map gets tried (the pass's scene is a step zone the exits'
        #  walks never crossed)
        #  - but only when it heads the window: a debt owed elsewhere (Drl's village scene
        #  that hands out the item Makrun's next talk wants) comes first, and run 45 spent
        #  80 steps combing Makrun's shops for the stand-in that followed it
        here_area = area_of_map(here_name)
        if any(sc[:2] == here_area and (here_name, sc) not in self.tried for sc in window[:1]):
            return out
        #  otherwise: the first move of the shortest known path to a map that plays the
        #  next script - or the one after, when no way to the next is known (the
        #  recorded player's run of it may be a revisit the route cannot tell apart) -
        #  or failing that to any map of its area we have not stood on this run
        visited = {self.maps.get(sig) for sig in self.visits}
        #  (a move that failed is left alone for a few steps only: the walk to it depends
        #  on where the party stands, and it usually works from somewhere else)
        avoid = {k for k, n in self.bad_moves.items() if self.step_n - n < 4} | {(m, '%s|%d' % tg) for (m, tg), n in self.commits.items() if n >= 99}
        path = None
        for want in window:
            #  not a map where its hinted moves already played nothing lately
            goals = [m for m in self.atlas.where_plays(want) if self.step_n - self.tried.get((m, want), -99) > 15]
            if here_name in self.atlas.where_plays(want) and (here_name, want) not in self.tried:
                continue                          # it plays here; only a full search can find how
            if not goals:
                goals = [m for m in self.atlas.maps_of_area(want[:2]) if m not in visited and m != here_name]
            path = self.atlas.path(here_name, goals, avoid) if goals else None
            if path:
                break
        if path is None and window and here_area != '01' and not self.atlas.maps_of_area(window[0][:2]):
            #  an area the atlas has never seen: the way to it starts on the world map,
            #  where the exits are cheap to try and one of them lands in that area
            path = self.atlas.path(here_name, self.atlas.maps_of_area('01'), avoid)
            if path:
                self.log('  plan: area %s unknown; heading for the world map' % window[0][:2])
        if path:
            m0, move, dest = path[0]
            #  every move known to lead there, not just the path's: a map's zone table
            #  differs between visits (the world map's does with the story), so the
            #  index that led to olb1 last run may be another door now
            moves = [tuple(mv.split('|')) for mv, ds in self.atlas.edges.get(m0, {}).items() if dest in ds and (m0, mv) not in avoid]
            moves = [(k, int(i)) for k, i in moves if (k, int(i)) in targets and self.commits.get((self._last_sig, (k, int(i))), 0) < 3]
            if moves:
                self.plan_dest = {dest} | set(goals)
                out.append(('go %s -> %s by %s (%d move(s) to %s for %s)' % (m0, dest, moves, len(path), path[-1][2], want),
                            moves, lambda r: self._landed(r) in self.plan_dest or r.get('route_hit') is not None))
        return out

    def _landed(self, r):
        """The name of the map a trial ended on, or None off any map."""
        return map_id(r['area'], r['region'], r['sig'][0]) if r['sig'] is not None else None

    def _backtrack_area(self, n, here):
        here_area = (self.maps.get(here) or '')[:2]
        entered = None
        while self.states and (self.maps.get(self.state_sigs.get(self.states[-1])) or '')[:2] == here_area:
            entered = self.state_moves.get(self.states.pop())
        prev = self.states[-1] if self.states else self.start_state
        if entered:
            self.bad_moves[(self.maps.get(entered[0]), '%s|%d' % tuple(entered[1]))] = n + 8   # not again for 20 steps
        self.log('step %3d: %d steps in area %s brought nothing; backtracking to %s'
                 % (n, self.dull, here_area, prev))
        self.emu.load_state(prev)
        self.emu._last_lines = None
        self.dull = 0

    def step(self, n):
        self.step_n = n
        if self.dull >= 8 and self.emu.state() == 'field':
            self._backtrack_area(n, self._remember_map())
            return True
        targets = self.targets()
        if targets is None:
            self.log(f'step {n:3d}: not on a map (scene?); letting it play out')
            if not self._settle_until_map():
                #  a scene that never ends on a map - a loop of guard fights after a
                #  no-entry zone - is a dead end like a death: rewind past the move
                from kuro_test import GameOver
                self.log('  still not on a map after waiting; rewinding')
                raise GameOver()
            targets = self.targets() or []
        here = self._remember_map()
        self._last_sig = here
        here_name = self.maps.get(here, '?')
        self.window = self._window() if self.route_plan else []
        base = zlib.compress(self.emu.m.save_state(), 1)
        counters0 = story_counters(self.emu)
        t0 = time.time()
        self.plan_dest = None
        results, tried = [], set()
        for why, subset, check in self._preferred(here_name, targets):
            subset = [tg for tg in subset if tuple(tg) not in tried]
            if not subset:
                continue
            self.log('  plan: ' + why)
            got = self._run_trials(base, subset)
            tried |= {tuple(r['target']) for r in got}
            results += got
            dead = ('CRASH', 'gameover', 'FROZEN', 'RESET')
            if any((check(r) or r.get('route_hit') is not None) and r['outcome'] not in dead and r['after'] is not None
                   for _sc, _n, _u, r in self._score(got, here, here_name, counters0)):
                break
            self.log('  plan: that did not do it')
            if why.startswith('talk '):
                for sc, _, _ in self.window:
                    self.tried[(here_name, sc)] = n
            if why.startswith('go '):
                for r in got:
                    self.bad_moves[(here_name, '%s|%d' % tuple(r['target']))] = n
        else:
            results += self._run_trials(base, [tg for tg in targets if tuple(tg) not in tried])
            for sc, _, _ in self.window:           # everything here was tried for them
                self.tried.setdefault((here_name, sc), n)
        scored = self._score(results, here, here_name, counters0)
        for r in results:
            self._absorb(r['pages'], r['issues'], committed=False)   # every trial's text is tested
            self._record(here, r)                                    # ...and mapped
        return self._commit(n, here, scored, results, t0)

    def _score(self, results, here, here_name, counters0):
        scored = []
        for r in results:
            keys = {self._key(l) for _, _, l in r['pages']}
            new = len({k for k in keys if k and k not in self.seen})
            unvisited = r['sig'] is not None and r['sig'] not in self.maps
            score = new + (UNVISITED_MAP_BONUS if unvisited else 0)
            r['route_hit'] = None
            if self.route_plan and self.route_i < len(self.route_plan):
                #  the recorded route: the trial's dialogue is the next script (or one of
                #  the next few - the walker skipped a run, or this is a revisit), or it
                #  at least lands where that script plays
                said = self._scripts_said(r['pages'])
                said_n = dict(said)
                #  a shared line names scripts of other towns too; only the map's own
                #  area can have played (a scene of another area on this map is rare)
                #  where the trial ended: by the map's fingerprint when it is a map we
                #  have named (the last resource loaded is often a portrait, not the map)
                landed = area_of_map(self._landed(r)) or area_of_map(r['map'])
                here_area = area_of_map(self.maps.get(here, ''))
                want = (self.window[0][0] if self.window else self.route_plan[self.route_i])[:2]
                back = self.route_plan[self.route_i - 1][:2] if self.route_i else None
                #  (a script of another area still counts when several of its pages
                #  played: a cutscene that carries the party to another town)
                if landed is None:
                    #  a map not named yet: what played can only be of the area we were
                    #  in, or the one the route goes to next (or came from)
                    said = {sc for sc, n in said.items() if sc[:2] in (here_area, want, back) or n >= 2}
                else:
                    said = {sc for sc, n in said.items() if sc[:2] == landed or n >= 2}
                #  a scene script with many entries is named by any one of its lines (the
                #  guards' lines are 07CSL02A's too), so a run the video spent long on -
                #  the audience, 122 anchors - must show several of its pages to count
                hit = next((j for j, (sc, kind, idx) in enumerate(self.window)
                            if sc in said and said_n.get(sc, 0) >= self._pages_needed(kind, idx)), None)
                #  a prerequisite only counts when a counter moved: its scene has many
                #  talks (the guards' lines), and one of them holds the write
                if hit is not None and self.window[hit][1] == 'setter' and not (
                        r.get('counters') and story_advanced(counters0, r['counters'])):
                    hit = None
                if hit is not None:
                    r['route_hit'], r['route_said'] = hit, sorted(said)
                    score += ROUTE_BONUS - 3 * sum(1 for sc, kind, _ in self.window[:hit] if kind == 'route')
                else:
                    #  no dialogue of the route: go where its next script plays, or,
                    #  failing that, back to where the recorded player was just before
                    moved = r['sig'] is not None and r['sig'] != here
                    if landed == want and here_area != want:
                        score += ROUTE_AREA_BONUS
                    elif landed == want and moved:
                        score += ROUTE_AREA_BONUS // 2          # another map of the right area
                    elif back and landed == back and here_area not in (want, back):
                        score += ROUTE_AREA_BONUS * 2 // 3
            #  the story: a counter moved, so the game itself says this was the way on
            if r.get('counters') and story_advanced(counters0, r['counters']):
                score += STORY_BONUS
                r['story_moved'] = True
                self.log('  story: %s moved a counter %s -> %s' % (r['target'],
                         [c for c in counters0 if c], [c for c in r['counters'] if c]))
            score -= REPEAT_PENALTY * self.commits.get((here, r['target']), 0)
            # With nothing new on offer, head for the map we've spent least time on,
            # otherwise it circles one map instead of covering the rest of the game.
            if r['sig'] is not None:
                score += 1 if r['sig'] != here else 0
                score -= 0.2 * self.visits.get(r['sig'], 0)
            #  the plan: the move went where the atlas said it would
            if self.plan_dest and r['sig'] not in (None, here):
                if self._landed(r) in self.plan_dest:
                    score += PLAN_BONUS
                    r['planned'] = True
            if r['sig'] is None and r['outcome'] != 'ok':
                score -= 30          # ended stuck off any map (a battle it could not fight)
            if r.get('counters') and story_reset(counters0, r['counters']):
                #  a story counter went down: the game restarted from the title (a death
                #  the trial read through, an ending, a reset) - as bad as a crash. Run
                #  17 took one such door out of the castle and played on in a new game.
                r['outcome'] = 'RESET'
                self.log(f'  !! RESET: {r["target"]} from {self.maps.get(here, "?")} wiped the story counters')
            if r['outcome'] in ('CRASH', 'gameover', 'FROZEN', 'RESET') or r['after'] is None:
                score = -100
            if r['outcome'] == 'FROZEN':
                self.log(f'  !! FROZEN: {r["target"]} from {self.maps.get(here, "?")}')
            if r['outcome'] == 'CRASH':
                self.log(f'  !! CRASH: {r["target"]} from {self.maps.get(here, "?")}')
            scored.append((score, new, unvisited, r))
        scored.sort(key=lambda s: s[0], reverse=True)
        return scored

    def _commit(self, n, here, scored, results, t0):
        if scored and all(sc <= -100 for sc, _, _, _ in scored):
            # Every move from here ends the game: this state is already lost (committed
            # into a defeat whose aftermath still reads as a normal map). Rewinding is
            # the same recovery as dying, so reuse it instead of ending the run.
            from kuro_test import GameOver
            self.log('step %3d: every move from here ends the game; rewinding' % n)
            raise GameOver()
        if scored and scored[0][0] <= 0.5 and not scored[0][1]:      # nothing new anywhere
            self.stale = getattr(self, 'stale', 0) + 1
            if self.stale >= 3:
                exits = [t for t in scored if t[3]['sig'] not in (None, here) and t[0] > -100]
                if exits:
                    self.log('step %3d: nothing here for %d steps; leaving by %s'
                             % (n, self.stale, exits[0][3]['target']))
                    scored = exits + [t for t in scored if t not in exits]
                    self.stale = 0
                else:
                    #  a trap: every move comes back here. Undo the moves that led in,
                    #  back to the last state on another map, and never take the move
                    #  that entered from there again
                    entered = None
                    while self.states and self.state_sigs.get(self.states[-1]) == here:
                        entered = self.state_moves.get(self.states.pop())
                    prev = self.states[-1] if self.states else self.start_state
                    if entered:
                        self.commits[entered] = 99
                    self.log('step %3d: nothing leads out of %s; backtracking to %s'
                             % (n, self.maps.get(here, '?'), prev))
                    self.emu.load_state(prev)
                    self.emu._last_lines = None
                    self.stale = 0
                    return True
        else:
            self.stale = 0
        if not scored or scored[0][0] <= -REPEAT_PENALTY * 3:
            # Say why, or a run that stops early looks like a bug in the scoring.
            self.log('step %3d: nothing worth doing on %s; best were:'
                     % (n, self.maps.get(here, '?')))
            for sc, new_n, unv, rr in scored[:4]:
                self.log('    %-4s %2d  score %6.1f  %-28s %d page(s)'
                         % (rr['target'][0], rr['target'][1], sc,
                            str(rr['outcome'])[:28], len(rr['pages'])))
            return False
        score, new, unvisited, r = scored[0]
        self.dull = 0 if (new or r.get('route_hit') is not None or r.get('planned')) else self.dull + 1
        if r.get('route_hit') is not None:
            self._route_hit(r['route_hit'], set(r.get('route_said', ())), moved=bool(r.get('story_moved')))
        #  a debt nobody could pay in 40 steps is forgiven
        self.debts = [d for d in self.debts if self.step_n - d[1] < 40]
        self.emu.m.load_state(zlib.decompress(r['after']))
        self.emu._last_lines = None
        self.transcript += [(m, s, l) for m, s, l in r['pages']]
        key = (here, r['target'])
        self.commits[key] = self.commits.get(key, 0) + 1
        self.last_commit = (self.maps.get(here), tuple(r['target']))
        self.last_commit_sig = here
        src_name = self.maps.get(here, '?')
        self.visits[self._remember_map()] += 1
        kind, idx = r['target']
        self.route['steps'] += [{'op': 'talk', 'slot': idx} if kind == 'npc'
                                else {'op': 'zone', 'kind': kind, 'index': idx},
                                {'op': 'settle', 'quiet': 3, 'timeout': 180}]
        # Only save once the game is back on a real map: a state saved mid-scene is
        # not somewhere we can play from, and rolling back to one loops on the scene.
        if len(self.emu.zones()) > self.MAX_REAL_ZONES or self.emu.state() != 'field':
            self._settle_until_map()
            self._remember_map()
        state_name = f'{self.name}_{n:02d}'
        self.emu.save_state(state_name)
        self.states.append(state_name)
        self.state_sigs[state_name] = self._remember_map()          # the map it sits on
        self.state_moves[state_name] = key                          # the move that made it
        self.log(f'step {n:3d}: {src_name:8} {kind:4} {idx:2} -> {self.maps.get(self._remember_map(), "?"):8} ({self.last_map_name}) '
                 f'score {score:3} ({new} new, {len(r["pages"])} pages{", new map" if unvisited else ""}) '
                 f'| {len(results)} trials in {time.time() - t0:4.0f}s | seen {len(self.seen)} pages, '
                 f'{len(self.maps)} maps, {len(self.issues)} issues')
        self.save()
        return True

    TRIAL_TIMEOUT = 180       # seconds of real time for one trial before it counts as hung

    def _run_trials(self, base, targets):
        """Run the trials in the pool, surviving a worker that never returns: a game
        state that hangs the emulator would otherwise block the whole run (seen on a
        battle that never starts). Whatever came back is used; hung targets are
        blacklisted so later steps don't retry them."""
        todo = [tg for tg in targets if (self.maps.get(self._last_sig), tg) not in self.hung]
        it = self.pool.imap_unordered(_trial, [(base, tg) for tg in todo])
        results, done = [], set()
        deadline = time.time() + self.TRIAL_TIMEOUT * 2
        try:
            for _ in range(len(todo)):
                r = it.next(timeout=max(5, deadline - time.time()))
                results.append(r)
                done.add(tuple(r['target']))
        except Exception as ex:
            missing = [tg for tg in todo if tuple(tg) not in done]
            self.log(f'  !! {len(missing)} trial(s) hung ({type(ex).__name__}); '
                     f'blacklisting {missing} and restarting the workers')
            for tg in missing:
                self.hung.add((self.maps.get(self._last_sig), tuple(tg)))
            self.pool.terminate()
            self.pool = mp.Pool(self.workers, initializer=_worker_init)
        return results

    def _record(self, here, r):
        """Remember what a target did and which script rows its text came from. Every
        trial counts, not just the committed one, so one run maps the whole map: each
        NPC and zone, where it leads, and where its text lives in the dump."""
        kind, idx = r['target']
        here_name = self.maps.get(here) or _label(here)
        dest = self._landed(r)
        sources = []
        for m, src, lines in r['pages']:
            if not src:
                # Untranslated text won't match the English corpus, but the workbook's
                # Japanese column still locates it - which is the point of the map.
                for line in lines:
                    hit = self.t.script.find_japanese(line.strip())
                    if hit and isinstance(hit[0], str):
                        src = (hit[0], hit[1])
                        break
            if not src or not isinstance(src[0], str):
                continue
            sources.append(list(src))
            seen_on = self.coverage.setdefault(src[0], {}).setdefault(str(src[1]), [])
            if here_name not in seen_on:
                seen_on.append(here_name)
        #  (a trial that died landed wherever the game's save reloads: no edge from that)
        if dest and dest != here_name and r['sig'] is not None and self.atlas.is_map(dest)                 and r['outcome'] not in ('CRASH', 'gameover', 'FROZEN', 'RESET'):
            self.atlas.edge(here_name, kind, idx, dest)
        #  a line shared with a far script (an item message, 99CMN) must not put that
        #  script on this map: a script of another area needs two pages to count
        by_script = collections.Counter(str(src[0])[:-4] for src in sources)
        here_area = self.atlas.area_of(here_name)
        for script, count in by_script.items():
            if here_area is None or script[:2] == here_area or count >= 2:
                self.atlas.played(here_name, kind, idx, script)
        key = f'{here_name}|{kind}|{idx}'
        old = self.graph.get(key)
        #  keep the richest attempt - and never let a later attempt that went nowhere
        #  (blocked on the way to the zone) erase where the move was seen to lead
        if old is None or len(sources) > len(old['text']) or (len(sources) == len(old['text']) and (dest or not old['leads_to'])):
            self.graph[key] = {'map': here_name, 'kind': kind, 'index': idx,
                               'leads_to': (dest if dest != here_name else None) or (old or {}).get('leads_to'),
                               'outcome': r['outcome'], 'state': r.get('state'), 'pages': len(r['pages']),
                               'text': sources}

    def write_map(self):
        """routes/<run>_map.json and docs/map_<run>.md: every map reached, what each of
        its NPCs and zones does, and which dump rows appeared where."""
        with open(os.path.join(HERE, 'routes', self.name + '_map.json'), 'w') as f:
            json.dump({'graph': self.graph, 'coverage': self.coverage,
                       'map_files': self.map_files}, f, indent=1)
        by_map = collections.defaultdict(list)
        for g in self.graph.values():
            by_map[g['map']].append(g)
        os.makedirs(os.path.join(HERE, 'docs'), exist_ok=True)
        with open(os.path.join(HERE, 'docs', 'map_%s.md' % self.name), 'w', encoding='utf-8') as f:
            def out(*t, **kw):
                print(*t, file=f, **kw)
            out('# What %s found' % self.name, end=EOL * 2)
            out('Every NPC and trigger zone tried, what it did, and the dump rows its text',
                'came from (`file offset`). Generated by autoplay.py.', end=EOL * 2)
            for m in sorted(by_map):
                out('## %s' % m, end=EOL * 2)
                if self.map_files.get(m):
                    out('Scripts loaded here: %s' % ', '.join(self.map_files[m]), end=EOL * 2)
                for g in sorted(by_map[m], key=lambda g: (g['kind'], g['index'])):
                    bits = ['%-4s %2d' % (g['kind'], g['index'])]
                    if g['leads_to']:
                        bits.append('-> %s' % g['leads_to'])
                    if g['pages']:
                        bits.append('%d page(s)' % g['pages'])
                    if g['outcome'] != 'ok':
                        bits.append('[%s]' % g['outcome'][:50])
                    srcs = sorted({'%s %s' % (a, b) for a, b in g['text']})
                    if srcs:
                        bits.append('text: ' + ', '.join(srcs[:8]) + ('...' if len(srcs) > 8 else ''))
                    out('- ' + '  '.join(bits))
                out()
            out('## Dump rows seen in play', end=EOL * 2)
            for fn in sorted(self.coverage):
                offs = self.coverage[fn]
                where = sorted({m for v in offs.values() for m in v})
                out('- **%s**: %d rows, on %s' % (fn, len(offs), ', '.join(where)))

    def save(self):
        os.makedirs(os.path.join(HERE, 'routes'), exist_ok=True)
        self.write_map()
        self.atlas.save()
        with open(os.path.join(HERE, 'routes', self.name + '.json'), 'w') as f:
            json.dump(self.route, f, indent=1)
        os.makedirs(os.path.join(HERE, 'test_reports'), exist_ok=True)
        path = os.path.join(HERE, 'test_reports', self.name + '_report.txt')
        by_kind = {}
        for (kind, detail), ctx in self.issues.items():
            by_kind.setdefault(kind, []).append((detail, ctx))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'{len(self.seen)} distinct pages seen, {len(self.maps)} maps, '
                    f'{len(self.issues)} distinct issues\n\n')
            for kind in sorted(by_kind):
                f.write(f'== {kind} ({len(by_kind[kind])})\n')
                for detail, ctx in by_kind[kind]:
                    f.write(f'  [{ctx}] {detail}\n')
                f.write('\n')
            f.write('--- committed transcript ---\n')
            for m, src, lines in self.transcript:
                where = f'{src[0]} {src[1]}' if src else '??'
                f.write(f'{m:12} {where:22} ' + ' / '.join(l.strip() for l in lines) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', help='named state to start from (default: New Game)')
    ap.add_argument('--steps', type=int, default=30)
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--name', default=time.strftime('auto_%m%d_%H%M'))
    ap.add_argument('--follow', help="play along a recorded route: 'twitch' or 'werdna' (docs/video_anchors.json)")
    ap.add_argument('--route-from', help='the script (or index) of the route to start at (default: its first)')
    ap.add_argument('--owe', help='scripts before the start still to play, comma separated (a skipped prerequisite)')
    args = ap.parse_args()
    t0 = time.time()
    from kuro_emu import Blocked
    from kuro_test import GameOver
    p = AutoPlayer(args.name, start=args.start, workers=args.workers)
    if args.follow:
        p.route_plan = recorded_route(args.follow)
        p.route_counts = recorded_route.counts
        if args.route_from and args.route_from.isdigit():
            p.route_i = int(args.route_from)
        elif args.route_from and args.route_from in p.route_plan:
            p.route_i = p.route_plan.index(args.route_from)
        if args.owe:
            #  each owed script at its last place in the route before the start
            p.debts = [(sc, 0, max(i for i, x in enumerate(p.route_plan[:p.route_i]) if x == sc))
                       for sc in args.owe.split(',')]
        print('following the %s route: %d scripts, starting at %d (%s)%s'
              % (args.follow, len(p.route_plan), p.route_i, p.route_plan[p.route_i],
                 '; owed: ' + args.owe if args.owe else ''))
    deaths = 0
    for n in range(1, args.steps + 1):
        try:
            productive = p.step(n)
        except (GameOver, Blocked) as ex:
            # The committed path can still die, or wedge in a battle that never offers
            # a menu - both are dead ends we have to back out of, not crashes.
            # That move leads to death: never pick it again. Then rewind one saved
            # state further, because the state we came from may be doomed too.
            if p.last_commit:
                p.hung.add(p.last_commit)
                p.last_commit = None
            if p.states:
                p.states.pop()
            back = p.states[-1] if p.states else args.start
            if not p.states and deaths >= 1:
                # Nothing earlier to go back to: the state we were given is already
                # lost, and rewinding to it again just repeats the same death.
                print('the start state cannot be recovered; start from an earlier one',
                      flush=True)
                break
            deaths += 1
            print(f'step {n:3d}: {type(ex).__name__}: {str(ex)[:60]}; '
                  f'rewinding to {back}', flush=True)
            if back is None or deaths > 8:
                print('too many dead ends in a row to keep going', flush=True)
                break
            p.emu.load_state(back)
            p.emu._last_lines = None
            p.emu.set_noclip(True)
            p.emu.heal()
            continue
        deaths = 0
        if not productive:
            print(f'no productive move left after {n - 1} steps', flush=True)
            break
    p.save()
    p.pool.terminate()
    print(f'done in {time.time() - t0:.0f} s: {len(p.seen)} distinct pages, {len(p.maps)} maps, '
          f'{len(p.issues)} distinct issues; routes/{p.name}.json, test_reports/{p.name}_report.txt',
          flush=True)


if __name__ == '__main__':
    main()
