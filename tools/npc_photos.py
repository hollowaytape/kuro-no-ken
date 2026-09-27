"""Photograph every person the game builds, in place, by walking its own zone graph.

tools/sprite_shots.py stands a mannequin where docs/npcs.json says a person is, and that
works only near where the save state was taken: the game builds the people of one
*region* of a map at a time (four or so), and rebuilds them when the player crosses a
step zone into the next region or through a door. Writing the player's position pans the
camera but fires nothing, and neither does standing in a zone: a zone fires when the
player *walks into* it. So this stands the player just outside each enabled zone, steps
in (no-clip, so walls do not matter), reads through whatever scene that opens, and looks
at what the game built:

* the same map with different people - a region: photograph them, then explore its zones;
* another map of the same area (a door, an exit) - a region of that map: the same;
* a battle, a menu, an exit to DOS - not a place: back to the state before.

Each live person's talk stub (+0x2a of its object) is the address docs/npcs.json records
for it, so the picture is named for the scene it opens - `<scene script>_<block>.png` in
docs/npc_img, which tools/translator_context.py hangs on the scene's Who cell. A person
whose talk stub is in no record (a shopkeeper the map builds without a scene) is skipped.

The states it starts from must have been saved on the disk image that is mounted now:
DOS's cached directory is part of the saved RAM, and the patched disk moves with every
build, so a state from another build reads garbage at the first file the game opens
(docs/sprites.md). Save them in the same session after a fresh boot, on the original
disk. A start on the world map hops into each exit that opens and explores what it
finds there.

    python tools/npc_photos.py                      # the default list of start states
    python tools/npc_photos.py --state fo_dog_from_sks5      # the capital

Nothing is written back to the game; the temporary states it saves are removed.
"""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

import sprite_shots as ss                                       # noqa: E402
from kuro_emu import OBJ_TABLE, OBJ_STRIDE, OBJ_SLOTS, OBJ_ANCHOR   # noqa: E402

IMG_DIR = os.path.join(HERE, 'docs', 'npc_img')
MANIFEST = os.path.join(IMG_DIR, 'taken.json')
SIZE = (320, 240)
UNIT = ss.UNIT

#  states saved from a fresh boot on the original disk (see the docstring)
STARTS = ['fo_r01_after_opening', 'fo_r01_world_map', 'fo_r03_manor_inside',
          'fo_after_mercenary', 'fo_world_map', 'fo_stg', 'fo_fld_east', 'fo_sks1',
          'fo_ckd_from_sks4', 'fo_dog_from_sks5']
POOL = ['_photo%d_%d' % (os.getpid(), i) for i in range(96)]   # temporary states, per process
MAX_REGIONS = 60
KEYS = ('DOWN', 'UP', 'LEFT', 'RIGHT')


def records():
    """talk address -> [(scene script, block, sprite, stage script)] from docs/npcs.json."""
    npcs = json.load(open(os.path.join(HERE, 'docs', 'npcs.json'), encoding='utf-8'))
    out = collections.defaultdict(list)
    for script, blocks in npcs.items():
        for block, npc in blocks.items():
            if npc.get('talk') is not None:          # sprite None: unplaced, any sprite fits
                out[npc['talk']].append((script[:-4], int(block), npc.get('sprite'), npc['from']))
    return out


_HEADS = None


def resident_scripts(e):
    """The stage/scene scripts in the game's script slots right now, by their first 32
    bytes against the original scripts (the disk mounted is the original)."""
    global _HEADS
    from verify_blocks import SEG
    if _HEADS is None:
        _HEADS = {}
        for path in glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN')):
            data = open(path, 'rb').read()
            _HEADS.setdefault(bytes(data[:32]), os.path.basename(path))
    out = set()
    for base in (0x0000, 0x1800, 0x3d00):
        name = _HEADS.get(bytes(e.read(SEG + base, 32)))
        if name:
            out.add(name)
    return out


def places():
    """sprite -> [(scene script, block, sprite, stage script, x, y)] from docs/npcs.json."""
    npcs = json.load(open(os.path.join(HERE, 'docs', 'npcs.json'), encoding='utf-8'))
    out = collections.defaultdict(list)
    for script, blocks in npcs.items():
        for block, npc in blocks.items():
            if npc.get('sprite') is not None:
                out[npc['sprite']].append((script[:-4], int(block), npc['sprite'], npc['from'], npc.get('x', 0), npc.get('y', 0)))
    return out


_ANALYSED = {}


def resident_slots(e):
    """{slot base: script filename} for the scripts in the game's slots right now."""
    global _HEADS
    from verify_blocks import SEG
    if _HEADS is None:
        resident_scripts(e)
    out = {}
    for base in (0x0000, 0x1800, 0x3d00):
        name = _HEADS.get(bytes(e.read(SEG + base, 32)))
        if name:
            out[base] = name
    return out


def resolve_live(e, talk):
    """What a live person's talk stub opens, from the scripts resident right now:
    -> [(scene script, block)] - exact, no guess about which scene script a stage
    swaps in (the records in docs/npcs.json have to guess that, and cannot for a stage
    script whose swaps the decoder does not reach, e.g. Sohagi's)."""
    import npcs, script_decode as sd
    slots = resident_slots(e)
    for base, fn in slots.items():
        if fn not in _ANALYSED:
            try:
                r = sd.analyse(fn)
                _ANALYSED[fn] = (r['base'], npcs._read(fn), r['insns'])
            except Exception:                        # noqa: BLE001
                _ANALYSED[fn] = None
        info = _ANALYSED[fn]
        if not info:
            continue
        sbase, data, insns = info
        if not sbase <= talk < sbase + len(data):
            continue                                 # not this script's stub
        target = npcs.talk_target(insns, data, sbase, talk)
        if not target:
            return []
        where, value = target
        if where == 'here':
            return [(fn[:-4], value)]
        #  the stub's first instruction, `04 <load block>`, names the scene script it
        #  swaps in before running the entry; failing that, the one resident now
        scene = slots.get(0x3d00)
        off = talk - sbase
        if data[off] == 0x04:
            called = npcs.load_blocks(fn, data, sbase).get(int.from_bytes(data[off + 1:off + 3], 'little'))
            if called:
                scene = called + '.SCN'
        if scene:
            entries = npcs.scene_entries(scene)
            if value < len(entries):
                return [(scene[:-4], entries[value])]
        return []
    return []


def people(e):
    """The live persons: [(slot, sprite, x, y, talk)] with raw object coordinates."""
    out = []
    for n in range(1, OBJ_SLOTS):
        r = bytes(e.read(OBJ_TABLE + n * OBJ_STRIDE, 0x2c))
        if (r[0] | r[1] << 8) >> 8 == 0x80:
            out.append((n, r[2], r[4] | r[5] << 8, r[6] | r[7] << 8, r[0x2a] | r[0x2b] << 8))
    return out


def resource(e):
    return ss.resource(e).replace('d\\', '').split('.')[0]


def area_of(name):
    """Which area a resource name belongs to, or None when it says nothing: a map is
    looked up, a script says so itself (02olb02a); a portrait or a battle screen (the
    last resource loaded is often one of those) is None, and the world map is 'fld'."""
    from play_tour import MAP_AREA
    if name.startswith('fld'):
        return 'fld'
    if name[:2].isdigit():
        return name[:2]
    return MAP_AREA.get(name)


def noclip(e, on):
    """set_noclip, where the module in memory has the walking code it patches."""
    try:
        e.set_noclip(on)
        return True
    except RuntimeError:
        return False


def put_player(e, x, y):
    e.write(OBJ_TABLE + 4, x.to_bytes(2, 'little'))
    e.write(OBJ_TABLE + 6, y.to_bytes(2, 'little'))


def photograph(e, person):
    """-> PIL image of the map around the person, with them in it, or None."""
    _slot, _sprite, x, y, _talk = person
    player = bytes(e.read(OBJ_TABLE, 0x30))
    put_player(e, max(0, x - 8), y)            # pan: the camera follows the player
    e.wait(0.3)
    shot = e.image()
    cam = e.pos()
    e.write(OBJ_TABLE, player)
    e.wait(0.1)
    sx, sy = (x - cam[0]) * UNIT, (y - cam[1]) * UNIT
    half = (SIZE[0] // 2, SIZE[1] // 2)
    box = (max(0, sx - half[0]), max(0, sy - half[1]),
           min(shot.width, sx + half[0]), min(shot.height, sy + half[1]))
    if box[2] - box[0] <= 32 or box[3] - box[1] <= 32:
        return None
    crop = shot.crop(box)
    return crop if ss._is_a_place(crop) else None


def walk_in(e, zone, key):
    """Stand 6 units outside the zone, on the side `key` walks in from, and step in.
    -> 'region', 'map', 'nothing', or the state that stopped it ('battle', 'menu',
    'dos', 'stuck')."""
    sig0, before = e.map_sig(), {p[4] for p in people(e)}
    cx, cy = (zone['x1'] + zone['x2']) // 2, (zone['y1'] + zone['y2']) // 2
    sx, sy = {'DOWN': (cx, zone['y1'] - 6), 'UP': (cx, zone['y2'] + 6),
              'RIGHT': (zone['x1'] - 6, cy), 'LEFT': (zone['x2'] + 6, cy)}[key]
    put_player(e, sx + OBJ_ANCHOR[0], sy + OBJ_ANCHOR[1])
    clip = noclip(e, True)                  # the world map's module has no such patch
    e.wait(0.2)
    try:
        for _ in range(12):
            e.tap(key, 0.08)
            e.wait(0.15)
            if e.state() != 'field' or e.map_sig() != sig0 or {p[4] for p in people(e)} != before:
                break
    finally:
        if clip:
            noclip(e, False)
    #  entering a region often opens a scene first (the guard at the gate); it is read
    #  through, and only then is the place looked at
    end = e.clock() + 15
    while e.clock() < end:
        st = e.state()
        if st == 'field':
            break
        if st == 'dialogue':
            e.press('SPACE', gap=0.3)
            continue
        return st
    else:
        return 'stuck'
    e.wait(1.5)
    if e.state() != 'field':
        return e.state()
    if e.map_sig() != sig0:
        return 'map'
    if {p[4] for p in people(e)} != before:
        return 'region'
    return 'nothing'


class Explorer:
    def __init__(self, e, recs, manifest, log, redo=False, max_regions=MAX_REGIONS):
        self.e, self.recs, self.manifest, self.log = e, recs, manifest, log
        self.by_place = places()
        self.redo, self.max_regions = redo, max_regions
        self.seen = set()
        self.pool = list(POOL)
        self.taken = 0

    def visit(self, label, start):
        """Photograph the live people here if this region is new. -> new?"""
        e = self.e
        sig = (e.map_sig(), frozenset(p[4] for p in people(e)))
        if sig in self.seen:
            return False
        self.seen.add(sig)
        live = people(e)
        loaded = resident_scripts(e)
        want = []
        for p in live:
            #  first choice: read the stub from the scripts resident now, which says
            #  exactly which scene it opens; the records are the fallback
            hits = [(scene, block, None, None) for scene, block in resolve_live(e, p[4])]
            #  the talk stub is exact - but only for a record of a stage script that is
            #  resident now (the same address means someone else in another town)
            hits = hits or [h for h in self.recs.get(p[4], ()) if h[3] in loaded] or list(self.recs.get(p[4], ()))
            if not hits:
                #  built by a scene script the parser has no base for: the same sprite
                #  standing within a few tiles of where a resident script puts one
                hits = [h for h in self.by_place.get(p[1], ())
                        if h[3] in loaded and abs(h[4] - p[2]) <= 24 and abs(h[5] - p[3]) <= 24]
                hits = [h[:4] for h in hits]
            if hits:
                want.append((p, hits))
        self.log('%s: %s (%s), %d people, %d in the records' % (label, resource(e), ' '.join(sorted(loaded)), len(live), len(want)))
        for person, hits in want:
            names = ['%s_%04x' % (script, block) for script, block, sprite, _from in hits
                     if sprite in (None, person[1])]
            if not names:
                continue
            if not self.redo and all(os.path.exists(os.path.join(IMG_DIR, n + '.png')) for n in names):
                self.log('    %s: have it' % names[0])
                continue
            img = photograph(e, person)
            if img is None:
                self.log('    %s: no picture (off the loaded part of the map)' % names[0])
                continue
            for n in names:
                img.save(os.path.join(IMG_DIR, n + '.png'))
                self.manifest[n] = {'state': start, 'map': resource(e), 'sprite': person[1],
                                    'at': [person[2], person[3]], 'talk': '%#x' % person[4]}
            self.taken += len(names)
            self.log('    %s' % ', '.join(names))
        return True

    def explore(self, start, area):
        """Breadth-first over the regions of one area from the current place."""
        e = self.e
        if not self.visit(start, start) or not self.pool:
            return
        queue = collections.deque()
        name = self.pool.pop()
        e.save_state(name)
        queue.append(name)
        regions = 1
        while queue and regions < self.max_regions and self.pool:
            here = queue.popleft()
            e.load_state(here)
            e.wait(0.3)
            zones = [z for z in e.zones() if z['enabled']]
            for z in zones[:48]:
                for key in KEYS:
                    e.load_state(here)
                    e.wait(0.3)
                    what = walk_in(e, z, key)
                    if what == 'nothing':
                        continue
                    if what in ('region', 'map'):
                        there = area_of(resource(e))
                        if what == 'map' and there not in (None, area):
                            break                      # another area: not this walk's job
                        if self.visit('  %s %d (%s)' % (z['kind'], z['index'], what), start) and self.pool:
                            name = self.pool.pop()
                            e.save_state(name)
                            queue.append(name)
                            regions += 1
                    break                              # fired (or crashed): next zone

    def run(self, start):
        e = self.e
        e.load_state(start)
        e.wait(0.8)
        if e.state() != 'field':
            self.log('%s: not on the field (%s), skipped' % (start, e.state()))
            return
        here = resource(e)
        if area_of(here) == 'fld':
            #  the world map: hop into every exit that opens, explore there, come back
            zones = [z for z in e.zones() if z['enabled'] and z['kind'] == 'step']
            for z in zones:
                e.load_state(start)
                e.wait(0.3)
                what = walk_in(e, z, 'DOWN')
                area = area_of(resource(e))
                if what == 'map' and area not in (None, 'fld'):
                    self.log('%s: exit %d -> %s' % (start, z['index'], resource(e)))
                    self.explore('%s/%d' % (start, z['index']), area)
            return
        self.explore(start, area_of(here))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', action='append', help='start from these states instead')
    ap.add_argument('--redo', action='store_true', help='retake pictures that exist')
    ap.add_argument('--max-regions', type=int, default=MAX_REGIONS)
    ap.add_argument('--hdd', help='the disk image the states were saved on; default: the original')
    args = ap.parse_args()
    from kuro_core import CoreEmu
    #  the fo_* states were saved with the original disk mounted, and a state is only
    #  good with the disk it was saved on (docs/sprites.md)
    e = CoreEmu(hdd=args.hdd or glob.glob(os.path.join(HERE, 'original', '*.hdi'))[0])
    recs = records()
    os.makedirs(IMG_DIR, exist_ok=True)
    try:
        manifest = json.load(open(MANIFEST, encoding='utf-8'))
    except (OSError, ValueError):
        manifest = {}
    x = Explorer(e, recs, manifest, print, args.redo, args.max_regions)
    for start in args.state or STARTS:
        x.pool = list(POOL)
        try:
            x.run(start)
        except Exception as ex:                  # noqa: BLE001 - one state must not end the run
            print('%s: %s: %s' % (start, type(ex).__name__, str(ex)[:80]))
        with open(MANIFEST, 'w', encoding='utf-8') as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True)
        sys.stdout.flush()
    for name in POOL:
        for path in glob.glob(os.path.join(HERE, 'states', name + '.*')):
            os.remove(path)
    print('%d pictures taken; %d in docs/npc_img' % (x.taken, len(glob.glob(os.path.join(IMG_DIR, '*.png')))))


if __name__ == '__main__':
    main()
