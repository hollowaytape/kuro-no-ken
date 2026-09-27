"""Walk a visit the way a player would, and record the order its scenes came in.

The scripts fix the order *between* visits (tools/story_order.py) and leave the order
inside one open: townspeople can be talked to in any sequence, a door can be taken
before or after the square. The sheet falls back to file order there, which is nobody's
order. This plays the visit instead, headless on np2core, with the geometry the player
has: from a real state - standing on a map with control - it repeatedly picks the
**nearest** target it has not tried (an NPC, a bump zone: door, sign, chest; a step zone:
walk-on event, exit), walks there **without noclip**, does what a player does (talk,
step in), reads what plays, and goes on from wherever that left it. A target the walk
cannot reach - a wall, a man asleep in a doorway - is put back and retried once every
other target has had its turn, which is how what only opens later comes later. Doors
into the area's other maps are taken when they are the nearest thing left; an exit to
the world map is noted and undone.

What it is not: a proof. A different player takes a different tour. It is the order a
player who explores nearest-first meets things in, which is a far better default than
the file, and every step of it is on the record (docs/play_tour/<name>.json: map,
target, position, distance, the scenes it produced) so a human can overrule it in
tools/play_order.json.

    python tools/play_tour.py r01_after_opening --name albein_1
    python tools/play_tour.py r03_manor_inside --name manor_1 --budget 60
    python tools/play_tour.py --to-play-order            # fold every tour into play_order.json

The scene labels come from the context workbook (KuroNoKen_dump_context*.xlsx, newest):
a line the game showed is matched to a dump row (kuro_test.Script), and the row's Scene
column names the conversation.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

OUT_DIR = os.path.join(HERE, 'docs', 'play_tour')
PLAY_ORDER = os.path.join(HERE, 'tools', 'play_order.json')
WORLD_MAPS = ('fld',)
# map resource name -> area number (engine_notes.md, "Teleport: destination is a global
# variable"): which scripts a map's text can belong to
MAP_AREA = {'ysk1': '03', 'ysk2': '03', 'olb1': '02', 'olb2': '02', 'old': '04', 'sks1': '05',
            'blk1': '06', 'blk2': '06', 'ckd': '08', 'hik': '09', 'tni1': '10', 'tni2': '10',
            'stg': '11', 'gakusha2': '12', 'haka': '13', 'ymm1': '14', 'mkr1': '15', 'mkr2': '15',
            'isk1': '16', 'drl1': '17', 'drl2': '17', 'goblin_s': '18', 'ire1': '19', 'nnp': '20',
            'gagoil': '21', 'isk2': '22', 'kies_m5': '23', 'umb1': '24', 'ds_16': '25', 'kkr': '26',
            'taicho_o': '27', 'mimic': '28', 'knt': '29', 'bac_11': '31',
            #  sub-maps met by walking (2026-09-25): the capital's other screens, the
            #  castle, the rest house's rooms, Makrun's and Sohagi's second maps
            'blk2': '06', 'blk3': '06', 'csl1': '07', 'csl2': '07', 'sks2': '05', 'mkr2': '15',
            'soh1': '23', 'soh2': '23', 'drl2': '17', 'ire2': '19', 'umb2': '24'}
MAX_REAL_ZONES = 80          # more than this and the "map" is a scene's data, not a map
MAP_EXTS = ('.mp1', '.mp2', '.mpc', '.mp')
_HEADS = {}


def _looks_like_map(name):
    n = name.lower()
    return n.endswith(MAP_EXTS) or (n.startswith(('fld', 'ysk', 'olb', 'tni')) and '_' not in n)


def newest_context_workbook():
    paths = sorted(glob.glob(os.path.join(HERE, 'KuroNoKen_dump_context*.xlsx')),
                   key=lambda p: (re.search(r'_v(\d+)', p) and int(re.search(r'_v(\d+)', p).group(1)) or 0, p))
    return paths[-1] if paths else None


def scene_labels(path):
    """{(file, offset): 'SCRIPT #n'} from the context workbook's Scene column."""
    import openpyxl
    out = {}
    if not path:
        return out
    ws = openpyxl.load_workbook(path, read_only=True)['SCNs']
    it = ws.iter_rows(values_only=True)
    col = {h: i for i, h in enumerate(next(it)) if h}
    for r in it:
        fn, off, scene = r[col['Filename']], r[col['Offset']], r[col['Scene']]
        if fn and off and scene:
            try:
                out[(fn, int(str(off), 16))] = scene
            except ValueError:
                pass
    return out


class Tour:
    def __init__(self, name, log=print):
        from kuro_core import CoreEmu
        from kuro_test import Tester
        self.name, self.log = name, log
        self.emu = CoreEmu()
        self.t = Tester(emu=self.emu, log=lambda *a: None)
        self.labels = scene_labels(newest_context_workbook())
        self.tried = collections.defaultdict(set)      # map sig -> {(kind, index)}
        self.deferred = collections.defaultdict(dict)  # map sig -> {(kind, index): why}
        self.steps = []
        self.sequence = []                             # scene labels, first appearance
        self.maps = {}                                 # sig -> name
        self.grids = {}                                # sig -> walkgrid.Grid
        self.arrived = {}                              # sig -> where the player first stood

    # --- what the map offers ---------------------------------------------------
    def here(self):
        """The map's identity is its zone layout; its name the last map resource seen
        (the resource name at 16d8:0951 also changes on script and scene loads)."""
        name = self.emu.map_name()
        if _looks_like_map(name):
            self.last_map = name.split('.')[0]
        sig = self.emu.map_sig()
        self.maps.setdefault(sig, getattr(self, 'last_map', '?'))
        return sig

    def on_a_map(self):
        return self.emu.state() == 'field' and len(self.emu.zones()) <= MAX_REAL_ZONES

    def settle(self):
        """Let a scene or battle play out until the player stands on a real map."""
        from kuro_emu import Blocked
        for _ in range(8):
            if self.on_a_map():
                return True
            try:
                self.t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 120})
            except Blocked as ex:                # a battle that goes nowhere, a hung scene
                self.log('  (settle: %s)' % str(ex)[:60])
                return False
            except Exception as ex:             # noqa: BLE001
                self.log('  (settle: %s)' % str(ex)[:60])
                return False
            self.emu.wait(1)
        return self.on_a_map()

    def loaded_scripts(self):
        global _HEADS
        if not _HEADS:
            # the emulator runs the patched build, whose headers differ where the text
            # moved: both sets of files are known
            for sub in (('original', 'decompressed'), ('patched',)):
                for path in glob.glob(os.path.join(HERE, *sub, '*.SCN')):
                    with open(path, 'rb') as f:
                        _HEADS.setdefault(f.read(32), os.path.basename(path))
        out = set()
        for off in (0, 0x1800, 0x3d00):
            name = _HEADS.get(bytes(self.emu.read(0x26d80 + off, 32)))
            if name:
                out.add(name)
        # (the entry table at the top of a loaded script is relocated in RAM, so this
        # often names nothing; then no script filter is applied)
        return out

    def grid(self):
        """The walk grid of the map the player stands on, learned on first arrival."""
        from walkgrid import Grid
        sig = self.here()
        if sig not in self.grids:
            self.log('  learning %s ...' % self.maps[sig])
            g = Grid(self.emu, log=self.log)
            g.learn(max_cells=8000, budget_s=600)
            self.grids[sig] = g
        return self.grids[sig]

    def targets(self):
        """Every NPC and enabled zone, nearest first *by walking*: (steps, target, x, y,
        approach tile). A target no learned tile comes within reach of gets no path
        and sorts last with steps None."""
        zones = self.emu.zones()
        if len(zones) > MAX_REAL_ZONES:
            return []
        g = self.grid()
        here = g.root()
        # walking distance from here to every tile, once
        dist = {here: 0} if here else {}
        queue = collections.deque([here] if here else [])
        while queue:
            c = queue.popleft()
            for n in g.edges[c]:
                if n not in dist:
                    dist[n] = dist[c] + 1
                    queue.append(n)
        out = []
        points = [(('npc', o['slot']), o['x'], o['y']) for o in self.emu.objects()]
        points += [((z['kind'], z['index']), (z['x1'] + z['x2']) // 2, (z['y1'] + z['y2']) // 2)
                   for z in zones if z['enabled']]
        for target, x, y in points:
            near = [c for c in g.cells if abs(c[0] - x) + abs(c[1] - y) <= 6 and c in dist]
            if near:
                cell = min(near, key=lambda c: (dist[c], abs(c[0] - x) + abs(c[1] - y)))
                out.append((dist[cell], target, x, y, cell))
            else:
                out.append((None, target, x, y, None))
        return sorted(out, key=lambda t: (t[0] is None, t[0] or 0, t[1]))

    # --- one interaction -------------------------------------------------------
    def scenes_of(self, pages, scripts):
        """The scene labels the pages came from, in order, without repeats - and only
        from scripts that were loaded: a short line (a name, an ellipsis) is in a
        hundred rows and the matcher picks one, which put the opening's scene on
        Innes's talk."""
        seen, out = set(), []
        for _m, src, lines in pages:
            # a page that is only a name plate and a word ("Innes / Hmm?") matches a
            # dozen rows across the game; it names no scene on its own
            body = ''.join(l.strip() for l in lines[1:]) if len(lines) > 1 else ''.join(l.strip() for l in lines)
            if len(body.replace('.', '').replace('・', '')) < 8:
                continue
            if not src:
                for line in lines:
                    hit = self.t.script.find_japanese(line.strip())
                    if hit and isinstance(hit[0], str):
                        src = (hit[0], hit[1])
                        break
            if not src or not isinstance(src[0], str):
                continue
            try:
                key = (src[0], int(str(src[1]), 16))
            except ValueError:
                continue
            label = self.labels.get(key)
            if label and label not in seen:
                seen.add(label)
                out.append(label)
        return out

    def do(self, target, cell=None, noclip=False):
        """Walk to a target and interact. -> (outcome, scenes, map changed?)

        The way there is the learned grid's path to `cell`, a tile next to the target;
        talk_to / goto_zone then do the last step or two. With noclip (the retry of
        what stayed blocked) the straight walk is used instead."""
        from kuro_emu import Blocked
        from kuro_test import GameOver
        kind, idx = target
        sig0 = self.here()
        scripts = self.loaded_scripts()
        self.t.pages = []
        self.emu.set_noclip(noclip)
        outcome = 'ok'
        try:
            if cell is not None and not noclip:
                start = self.grid().root()
                if start is None or not self.grid().snap(start):
                    raise Blocked('off the grid at %s' % (self.emu.pos(),))
                path = self.grid().path(start, cell)
                if path is None:
                    raise Blocked('no path to %s' % (cell,))
                if not self.grid().walk(path, on_interrupt=self.t.handle_interrupt):
                    # something took over on the way (a scene, a battle, a wandering
                    # NPC): deal with it and try the rest of the way once more
                    self.t.handle_interrupt()
                    if self.here() != sig0 or self.emu.state() != 'field':
                        raise Blocked('interrupted on the way')
                    start = self.grid().root()
                    path = self.grid().path(start, cell) if start and self.grid().snap(start) else None
                    if path is None or not self.grid().walk(path, on_interrupt=self.t.handle_interrupt):
                        raise Blocked('could not finish the way to %s' % (cell,))
            if kind == 'npc':
                self.t.talk_to(idx)
            else:
                self.t.goto_zone(idx, kind=kind, timeout=20)
            self.t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 120})
        except GameOver:
            outcome = 'gameover'
        except Blocked as ex:
            outcome = 'blocked: ' + str(ex)[:60]
        except Exception as ex:                      # noqa: BLE001 - one target must not end the tour
            outcome = 'error: %s: %s' % (type(ex).__name__, str(ex)[:60])
        finally:
            self.emu.set_noclip(False)
        if self.emu.state() == 'dos':
            outcome = 'CRASH'
        elif not self.settle():
            outcome = 'lost: not back on a map'
        scripts |= self.loaded_scripts()
        scenes = self.scenes_of(self.t.pages, scripts)
        return outcome, scenes, self.here() != sig0

    # --- the tour ------------------------------------------------------------
    def run(self, budget=80):
        base = self.emu.save_state('_tour_base')
        n = 0
        while n < budget:
            sig = self.here()
            name = self.maps[sig]
            if name.lower().startswith(WORLD_MAPS):
                self.log('on the world map; the visit is over')
                break
            if sig not in self.arrived:
                # the door just come through: a player does not turn straight round
                ax, ay = self.emu.pos()
                self.arrived[sig] = (ax, ay)
                for _d, tg, x, y, _c in self.targets():
                    if tg[0] != 'npc' and abs(x - ax) + abs(y - ay) <= 4:
                        self.deferred[sig][tg] = 'the way in'
            all_targets = self.targets()
            options = [(d, tg, x, y, c) for d, tg, x, y, c in all_targets
                       if tg not in self.tried[sig] and tg not in self.deferred[sig] and d is not None]
            noclip = False
            if not options:
                # out of reach from here (no learned tile near it): deferred too
                for d, tg, x, y, c in all_targets:
                    if tg not in self.tried[sig] and tg not in self.deferred[sig]:
                        self.deferred[sig][tg] = 'no tile near it'
                # everything reachable has been tried: give what was blocked one more
                # go, nearest first, walking through whatever stopped it
                options = [(d if d is not None else 9999, tg, x, y, c) for d, tg, x, y, c in all_targets
                           if tg in self.deferred[sig] and self.deferred[sig][tg] != 'retried']
                options.sort(key=lambda t: t[0])
                noclip = True
                if not options:
                    self.log('nothing left to try on %s' % name)
                    break
            d, target, x, y, cell = options[0]
            px, py = self.emu.pos()
            before = self.emu.save_state('_tour_step')
            outcome, scenes, moved = self.do(target, cell=cell, noclip=noclip)
            n += 1
            step = {'n': n, 'map': name, 'target': list(target), 'at': [x, y], 'from': [px, py],
                    'dist': d, 'noclip': noclip, 'outcome': outcome, 'scenes': scenes,
                    'pages': len(self.t.pages)}
            if outcome.startswith('blocked') and not noclip:
                self.deferred[sig][target] = outcome
                self.emu.load_state('_tour_step')
                self.log('%3d %-8s %-14s %s, deferred' % (n, name, target, outcome[:40]))
                continue
            if noclip:
                self.deferred[sig][target] = 'retried'
            self.tried[sig].add(target)
            new_map = self.emu.map_name()
            if moved and new_map.lower().startswith(WORLD_MAPS):
                step['leads_to'] = new_map
                self.emu.load_state('_tour_step')
                self.log('%3d %-8s %-14s -> world map, undone' % (n, name, target))
                self.steps.append(step)
                continue
            if outcome in ('CRASH', 'gameover') or outcome.startswith('lost'):
                self.emu.load_state('_tour_step')
                self.log('%3d %-8s %-14s %s, undone' % (n, name, target, outcome))
                self.steps.append(step)
                continue
            if moved:
                step['leads_to'] = new_map
            for s in scenes:
                if s not in self.sequence:
                    self.sequence.append(s)
            self.steps.append(step)
            self.log('%3d %-8s %-14s %4s steps %s %s' % (n, name, target, d, outcome, ', '.join(scenes) or ('-> ' + new_map if moved else '')))
        self.emu.load_state('_tour_base')
        return self.steps

    def save(self, start):
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, self.name + '.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'start': start, 'when': time.strftime('%Y-%m-%d %H:%M'),
                       'sequence': self.sequence, 'steps': self.steps}, fh, ensure_ascii=False, indent=1)
        self.log('-> %s (%d steps, %d scenes)' % (path, len(self.steps), len(self.sequence)))
        return path


VIDEO = os.path.join(HERE, 'docs', 'video_anchors.json')


def _norm(s):
    return re.sub(r'[\s　「」]|\[a-z]\d*|\[[A-Z]+\]', '', s or '')


def video_sequences(labels, log=print):
    """series -> the recorded playthrough's scenes in the order they were seen, from
    docs/video_anchors.json: each anchor's line is found in its script's rows and the
    row's scene taken; a scene counts at its first sighting. One sequence per recorded
    playthrough (series), since two players' routes are two orders."""
    if not os.path.exists(VIDEO):
        return {}
    import openpyxl
    path = newest_context_workbook()
    rows = collections.defaultdict(list)                  # script -> [(offset, jp)]
    ws = openpyxl.load_workbook(path, read_only=True)['SCNs']
    it = ws.iter_rows(values_only=True)
    col = {h: i for i, h in enumerate(next(it)) if h}
    for r in it:
        fn, off, jp = r[col['Filename']], r[col['Offset']], r[col['Japanese']]
        if fn and off and isinstance(jp, str):
            rows[fn[:-4]].append((int(str(off), 16), _norm(jp)))
    #  Script by script, not scene by scene: a frame of one conversation says the
    #  whole visit's script was being played then, and moving one scene of it while
    #  its neighbours stay would split the visit. A bare script name in play_order.json
    #  stands for its scenes in the order the sheet already has them.
    import story_order as so
    scripts = so._scripts()
    stages = collections.defaultdict(set)              # script -> the stage values it is loaded at
    for hub, d in scripts.items():
        if re.fullmatch(r'\d\d[A-Z]+', hub):
            for var, val, child in so.hub_cases(d):
                if var == so.stage_var(hub):
                    stages[child].add(val)
    #  a hub that loads scenes at several stages (03YSK, 06BLK, ...) shows its own lines,
    #  the place name and the like, on every visit: a sighting of it dates nothing
    revisited = {hub for hub, d in scripts.items() if re.fullmatch(r'\d\d[A-Z]+', hub)
                 and len({val for var, val, _c in so.hub_cases(d) if var == so.stage_var(hub)}) > 1}
    out, missing = collections.OrderedDict(), []
    anchors = sorted(json.load(open(VIDEO, encoding='utf-8'))['anchors'],
                     key=lambda a: (a.get('series', 'twitch'), a['at']))
    #  A lone anchor inside another script's run (the same line in a sibling script,
    #  matched from a frame read by machine) is noise, not a sighting: its neighbours
    #  within five minutes on both sides are one other script.
    keep = []
    for i, a in enumerate(anchors):
        prev = anchors[i - 1] if i else None
        nxt = anchors[i + 1] if i + 1 < len(anchors) else None
        lone = (prev and nxt and prev.get('series') == a.get('series') == nxt.get('series')
                and prev['script'] == nxt['script'] != a['script']
                and a['at'] - prev['at'] <= 300 and nxt['at'] - a['at'] <= 300)
        if not lone and a['script'] not in revisited:
            keep.append(a)
    for a in keep:
        seq = out.setdefault(a.get('series', 'twitch'), [])
        key = _norm(a['line'].split(' (')[0])
        hit = next(((a['script'] + '.SCN', off) for off, jp in rows.get(a['script'], ()) if key and key in jp), None)
        label = labels.get(hit) if hit else None
        if not label:
            missing.append('%s %ds' % (a['script'], a['at']))
            continue
        # a script the hub loads at two stages (02OLB01: the first meeting and, later,
        # the theft) spans visits; only the scene that was seen stands for it
        item = label if len(stages.get(a['script'], ())) > 1 else a['script']
        if item not in seq:
            seq.append(item)
    if missing:
        log('video anchors with no scene: %s' % ', '.join(missing[:8]))
    return out


def fold_into_play_order(log=print):
    """Every tour's sequence, and the recorded playthrough's, becomes an entry of
    tools/play_order.json (replacing an earlier entry from the same source;
    hand-written entries are never touched)."""
    spec = json.load(open(PLAY_ORDER, encoding='utf-8')) if os.path.exists(PLAY_ORDER) else {'sequences': []}
    keep = [e for e in spec.get('sequences', ()) if not str(e.get('source', '')).startswith(('tour ', 'video'))]
    added = 0
    for series, video in video_sequences(scene_labels(newest_context_workbook()), log).items():
        if len(video) >= 2:
            keep.append({'source': 'video ' + series,
                         'why': "the order the scenes were seen in %s's recorded playthrough (docs/video_anchors.json)" % series,
                         'scenes': video})
        added += 1
    for path in sorted(glob.glob(os.path.join(OUT_DIR, '*.json'))):
        tour = json.load(open(path, encoding='utf-8'))
        name = os.path.basename(path)[:-5]
        # only scenes of the areas the tour walked: a line the game shows everywhere
        # ("locked", an item message) matches 99CMN or some far script and is not a
        # scene of the visit
        areas = {MAP_AREA.get(m) for m in (step['map'] for step in tour.get('steps', ()))}
        areas |= {MAP_AREA.get(m.split('.')[0]) for step in tour.get('steps', ()) for m in [step.get('leads_to') or '']}
        areas.discard(None)
        seq = [lab for lab in tour.get('sequence', ()) if lab[:2] in areas]
        if len(seq) >= 2:
            keep.append({'source': 'tour ' + name,
                         'why': 'the order a nearest-first walk from %s met them in (docs/play_tour/%s.json)'
                                % (tour.get('start'), name),
                         'scenes': seq})
            added += 1
    spec['sequences'] = keep
    with open(PLAY_ORDER, 'w', encoding='utf-8') as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)
    log('%d tour(s) folded into %s' % (added, PLAY_ORDER))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('state', nargs='?', help='a save state with the player on a map')
    ap.add_argument('--name', help='tour name (default: the state)')
    ap.add_argument('--budget', type=int, default=80, help='at most this many interactions')
    ap.add_argument('--to-play-order', action='store_true', help='fold docs/play_tour/*.json into tools/play_order.json')
    args = ap.parse_args()
    if args.to_play_order:
        fold_into_play_order()
        return
    if not args.state:
        ap.error('a state is needed')
    tour = Tour(args.name or args.state)
    tour.emu.load_state(args.state)
    if tour.emu.state() != 'field':
        print('state is not on a map (%s); letting it settle' % tour.emu.state())
        tour.t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 180})
    print('on %s at %s, %d targets' % (tour.emu.map_name(), tour.emu.pos(), len(tour.targets())))
    tour.run(budget=args.budget)
    tour.save(args.state)


if __name__ == '__main__':
    main()
