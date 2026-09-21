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
    e.heal()
    outcome = 'ok'
    t0 = time.time()
    try:
        kind, idx = target
        if kind == 'npc':
            t.talk_to(idx)
        else:
            t.goto_zone(idx, kind=kind, timeout=20)
        t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 180})
    except GameOver:
        outcome = 'gameover'
    except Blocked as ex:
        outcome = f'blocked: {str(ex)[:60]}'
    except Exception as ex:          # never let one trial kill the pool
        outcome = f'error: {type(ex).__name__}: {str(ex)[:80]}'
    st = e.state()
    field = st == 'field' and len(e.zones()) <= AutoPlayer.MAX_REAL_ZONES   # not a scene/battle
    return {
        'target': target, 'outcome': 'CRASH' if st == 'dos' else outcome,
        'pages': [(m, src, lines) for m, src, lines in t.pages],
        'issues': list(t.issues),
        'sig': e.map_sig() if field else None,
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
            sig = self.emu.map_sig()
            # A map whose name we never caught still needs a label of its own, or every
            # unnamed map would merge into one entry in the map report.
            self.maps.setdefault(sig, self.last_map_name if self.last_map_name != '?'
                                 else _label(sig))
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
        for _ in range(10):
            self.t.run_step({'op': 'settle', 'quiet': 3, 'timeout': 120})
            if len(self.emu.zones()) <= self.MAX_REAL_ZONES and self.emu.state() == 'field':
                return True
            self.emu.wait(2)
        return False

    def step(self, n):
        targets = self.targets()
        if targets is None:
            self.log(f'step {n:3d}: not on a map (scene?); letting it play out')
            if not self._settle_until_map():
                self.log('  still not on a map after waiting; stopping')
                return False
            targets = self.targets() or []
        here = self._remember_map()
        self._last_sig = here
        base = zlib.compress(self.emu.m.save_state(), 1)
        t0 = time.time()
        results = self._run_trials(base, targets)
        scored = []
        for r in results:
            keys = {self._key(l) for _, _, l in r['pages']}
            new = len({k for k in keys if k and k not in self.seen})
            unvisited = r['sig'] is not None and r['sig'] not in self.maps
            score = new + (UNVISITED_MAP_BONUS if unvisited else 0)
            score -= REPEAT_PENALTY * self.commits.get((here, r['target']), 0)
            # With nothing new on offer, head for the map we've spent least time on,
            # otherwise it circles one map instead of covering the rest of the game.
            if r['sig'] is not None:
                score += 1 if r['sig'] != here else 0
                score -= 0.2 * self.visits.get(r['sig'], 0)
            if r['outcome'] in ('CRASH', 'gameover') or r['after'] is None:
                score = -100
            if r['outcome'] == 'CRASH':
                self.log(f'  !! CRASH: {r["target"]} from {self.maps.get(here, "?")}')
            self._absorb(r['pages'], r['issues'], committed=False)   # every trial's text is tested
            self._record(here, r)                                    # ...and mapped
            scored.append((score, new, unvisited, r))
        scored.sort(key=lambda s: s[0], reverse=True)
        if scored and all(sc <= -100 for sc, _, _, _ in scored):
            # Every move from here ends the game: this state is already lost (committed
            # into a defeat whose aftermath still reads as a normal map). Rewinding is
            # the same recovery as dying, so reuse it instead of ending the run.
            from kuro_test import GameOver
            self.log('step %3d: every move from here ends the game; rewinding' % n)
            raise GameOver()
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
        self.emu.m.load_state(zlib.decompress(r['after']))
        self.emu._last_lines = None
        self.transcript += [(m, s, l) for m, s, l in r['pages']]
        key = (here, r['target'])
        self.commits[key] = self.commits.get(key, 0) + 1
        self.last_commit = (self.maps.get(here), tuple(r['target']))
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
        self.log(f'step {n:3d}: {src_name:9} {kind:4} {idx:2} -> {self.last_map_name:9} '
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
        dest = self.maps.get(r['sig']) or (r['map'].split('.')[0] if r['sig'] else None)
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
        key = f'{here_name}|{kind}|{idx}'
        old = self.graph.get(key)
        if old is None or len(sources) >= len(old['text']):     # keep the richest attempt
            self.graph[key] = {'map': here_name, 'kind': kind, 'index': idx,
                               'leads_to': dest if dest != here_name else None,
                               'outcome': r['outcome'], 'pages': len(r['pages']),
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
    args = ap.parse_args()
    t0 = time.time()
    from kuro_emu import Blocked
    from kuro_test import GameOver
    p = AutoPlayer(args.name, start=args.start, workers=args.workers)
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
