"""Photograph the game's NPC sprites, straight out of the running game.

The objects that carry the dialogue (tools/npcs.py) name their sprite by number, and the
number means nothing to a translator. This takes the picture instead.

How: load a save state whose map is the one wanted, borrow an object slot as a mannequin,
stand it on the tile beside the player and write the sprite number into its field 0x02
(the engine redraws from that every frame). Two frames are captured for each number - one
with the mannequin there, one with it moved far away - and the pixels that differ are the
sprite, which needs no guess about where the sprite is drawn relative to its anchor or
what furniture is behind it.

    python tools/sprite_shots.py --state r01_after_opening --area 02OLB
    python tools/sprite_shots.py --list-maps        # which state sits on which map

Writes docs/sprite_img/<area>_<sprite>.png and re-writes docs/sprites.html with the
pictures in it. Nothing is written back to the game: the state is loaded into RAM, poked
and thrown away.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

BD = 0x16d80
OBJ = BD + 0x1aa            # object table; slot 0 is the player, 0xf0 bytes each
SLOT = 0xf0
RESOURCE = BD + 0x951       # the name of the last resource loaded
UNIT = 8                    # screen pixels per map unit (see tools/npcs.py)
IMG_DIR = os.path.join(HERE, 'docs', 'sprite_img')
AWAY = 0x7000               # where the mannequin goes for the background frame


def resource(e):
    return bytes(e.read(RESOURCE, 16)).split(b'\x00')[0].decode('ascii', 'replace')


def slot_free(e, n):
    """Is object slot n empty (type word 0)?"""
    return int.from_bytes(bytes(e.read(OBJ + n * SLOT, 2)), 'little') in (0, 0xffff)


def mannequin(e):
    """A slot to borrow: a person the map already built, restored afterwards.

    An empty slot is not enough - writing a type, a position and a sprite into one draws
    almost nothing, because the rest of the object (its animation frame, its facing, the
    fields the draw routine reads) is still zero. Borrowing a live NPC gets all of that
    for free; only its sprite and position change, and both are put back.
    """
    for n in range(1, 16):
        typ = int.from_bytes(bytes(e.read(OBJ + n * SLOT, 2)), 'little')
        if typ >> 8 == 0x80:                     # a person, as the stage scripts build them
            return n
    for n in range(1, 16):
        if slot_free(e, n):
            return n
    return 1


#   Where to stand the mannequin, as an offset in map units from the player's own tile.
#   A sprite drawn behind furniture comes out clipped, so several spots are tried and the
#   tallest capture wins - a whole person is about 40 screen pixels, a head about 12.
SPOTS = [(6, 0), (-6, 0), (0, 6), (0, -6), (10, 0), (-10, 0), (0, 10), (6, 6), (-6, -6)]
WHOLE = 36


def shoot(e, sprites, settle=0.25, spots=SPOTS):
    """-> {sprite: RGBA image} - each sprite cut out of the screen, background removed.

    Only a window around where the mannequin stands is compared. The town's own people
    walk about between the two frames, and a whole-screen diff picks them up as well - the
    first attempt at this came back with a staff and half a hedge. The anchor is known
    exactly (screen = (object - camera) * 8), so looking only there is both simpler and
    stricter than any amount of frame-averaging, which fails anyway because the sprite
    itself animates.
    """
    n = mannequin(e)
    at = OBJ + n * SLOT
    was = bytes(e.read(at, 0x30))
    out = {}
    for sprite in sprites:
        best = None
        for dx, dy in spots:
            cam = e.pos()          # read fresh: the caller may have panned since
            nx, ny = cam[0] + 0x28 + dx, cam[1] + 0x1c + dy
            e.write(at + 4, nx.to_bytes(2, 'little'))
            e.write(at + 6, ny.to_bytes(2, 'little'))
            e.write(at + 2, bytes([sprite]))
            e.wait(settle)
            shot = e.image()
            cam_now = e.pos()
            e.write(at + 4, AWAY.to_bytes(2, 'little'))       # off the world
            e.wait(settle)
            anchor = ((nx - cam_now[0]) * UNIT, (ny - cam_now[1]) * UNIT)
            cut = _cut_out(shot, e.image(), anchor=anchor)
            if cut and (best is None or cut.height > best.height):
                best = cut
            if best is not None and best.height >= WHOLE:
                break
        if best is not None:
            out[sprite] = best
    e.write(at, was)
    return out


WINDOW = (28, 56, 12)      # how far around the anchor a sprite reaches: left/right, up, down


def _cut_out(shot, back, anchor=None, slack=1):
    """The pixels the mannequin added, as RGBA with everything else transparent.

    `anchor` is where the object stands on screen; only WINDOW around it is compared, so
    a townsperson walking somewhere else in the frame cannot join in.
    """
    from PIL import Image
    a, b = shot.convert('RGB'), back.convert('RGB')
    pa, pb = a.load(), b.load()
    w, h = a.size
    if anchor:
        ax, ay = anchor
        x0, x1 = max(0, ax - WINDOW[0]), min(w, ax + WINDOW[0])
        y0, y1 = max(0, ay - WINDOW[1]), min(h, ay + WINDOW[2])
    else:
        x0, x1, y0, y1 = 0, w, 0, h
    mask = Image.new('L', (w, h), 0)
    pm = mask.load()
    xs, ys = [], []
    for y in range(y0, y1):
        for x in range(x0, x1):
            if pa[x, y] != pb[x, y]:
                pm[x, y] = 255
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 - x0 > 64 or y1 - y0 > 96:      # a scroll or an animation, not just the sprite
        return None
    box = (max(0, x0 - slack), max(0, y0 - slack),
           min(w, x1 + 1 + slack), min(h, y1 + 1 + slack))
    out = a.crop(box).convert('RGBA')
    out.putalpha(mask.crop(box))
    return out


#   How far from the capture point an NPC may stand and still be photographed. The sprite
#   *number* is an index into whatever set the game had loaded when the state was saved,
#   and panning does not reload it (checked: sprite 12 renders identically at the house,
#   the square and the tavern of one stage). So a picture is only known-good for the part
#   of the map the game was actually in - beyond that it is a guess wearing a face, which
#   is worse than no picture at all.
NEAR = 60


def where_they_stand(e, area, size=(320, 240), settle=0.3, near=NEAR):
    """-> {(script, block): image} - each NPC on the spot the map puts them.

    The camera follows the player, so writing the player's position pans the view; the
    mannequin is then stood on the NPC's own tile with the NPC's own sprite, a little away
    from the player so the two do not overlap. What comes back is that corner of the map
    with the right person in it.
    """
    npcs = json.load(open(os.path.join(HERE, 'docs', 'npcs.json'), encoding='utf-8'))
    n = mannequin(e)
    at = OBJ + n * SLOT
    was = bytes(e.read(at, 0x30))
    player = bytes(e.read(OBJ, 0x30))
    home = e.pos()
    out = {}
    for script, blocks in sorted(npcs.items()):
        if script[:5] != area:
            continue
        for block, npc in sorted(blocks.items(), key=lambda kv: int(kv[0])):
            x, y = npc['x'], npc['y']
            if npc.get('sprite') is None:
                continue
            if abs(x - home[0]) > near or abs(y - home[1]) > near:
                continue                     # outside the part of the map this state loaded
            e.write(OBJ + 4, max(0, x - 8).to_bytes(2, 'little'))    # pan: player off to one side
            e.write(OBJ + 6, y.to_bytes(2, 'little'))
            e.write(at + 4, x.to_bytes(2, 'little'))
            e.write(at + 6, y.to_bytes(2, 'little'))
            e.write(at + 2, bytes([npc['sprite']]))
            e.wait(settle)
            shot = e.image()
            cam = e.pos()
            sx, sy = (x - cam[0]) * UNIT, (y - cam[1]) * UNIT
            half = (size[0] // 2, size[1] // 2)
            box = (max(0, sx - half[0]), max(0, sy - half[1]),
                   min(shot.width, sx + half[0]), min(shot.height, sy + half[1]))
            if box[2] - box[0] <= 32 or box[3] - box[1] <= 32:
                continue
            crop = shot.crop(box)
            if not _is_a_place(crop):
                continue
            out[(script, int(block))] = crop
    e.write(at, was)
    e.write(OBJ, player)
    return out


def _is_a_place(img, share=0.9, least_tiles=24):
    """Is this a picture of somewhere, or of nothing?

    Only the part of the map the player stands in is loaded. Pan past it and the screen is
    either black or one tile repeated for ever - the engine drawing whatever the tilemap
    pointer now lands on. Both are worth dropping, and the second is what a "mostly black"
    test misses: count the distinct 16x16 tiles instead, of which a real corner of a town
    has plenty (60-120 in the towns) and an unloaded one has a dozen, all variations of the
    same wall. Measured on both: 12 tiles for a stretch of nothing, 66 and 124 for real
    rooms, so the line sits at 24.
    """
    small = img.convert('RGB')
    pixels = small.convert('L').getdata()
    if sum(1 for p in pixels if p < 16) >= share * len(pixels):
        return False
    w, h = small.size
    tiles = {small.crop((x, y, x + 16, y + 16)).tobytes()
             for y in range(0, h - 15, 16) for x in range(0, w - 15, 16)}
    return len(tiles) >= least_tiles


def wanted(area):
    """The sprite numbers this area's NPCs use, from docs/npcs.json."""
    with open(os.path.join(HERE, 'docs', 'npcs.json'), encoding='utf-8') as fh:
        npcs = json.load(fh)
    out = set()
    for script, blocks in npcs.items():
        if script[:5] != area:
            continue
        for npc in blocks.values():
            if npc.get('sprite') is not None:
                out.add(npc['sprite'])
    return sorted(out)


def list_maps(states=None):
    """Which save state sits on which map - so a map can be photographed at all."""
    from kuro_core import CoreEmu
    e = CoreEmu()
    names = states or [os.path.basename(p)[:-8]
                       for p in sorted(glob.glob(os.path.join(HERE, 'states', '*.np2core')))]
    for name in names:
        try:
            e.load_state(name)
            e.wait(0.2)
        except Exception as exc:
            print('%-26s -- %s' % (name, str(exc)[:40]))
            continue
        print('%-26s %-16s camera %s' % (name, resource(e), e.pos()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', help='a save state whose map is the one to photograph')
    ap.add_argument('--area', help='area prefix, e.g. 02OLB - picks which sprites to shoot')
    ap.add_argument('--sprites', help='comma-separated numbers, instead of the area\'s own')
    ap.add_argument('--list-maps', action='store_true')
    ap.add_argument('--npcs', action='store_true',
                    help='also photograph the spot each NPC of the area stands on')
    ap.add_argument('--states', nargs='*', help='limit --list-maps to these')
    args = ap.parse_args()

    if args.list_maps:
        list_maps(args.states)
        return
    if not (args.state and args.area):
        ap.error('--state and --area are both needed')

    from kuro_core import CoreEmu
    e = CoreEmu()
    e.load_state(args.state)
    e.wait(1.0)
    sprites = ([int(s) for s in args.sprites.split(',')] if args.sprites else wanted(args.area))
    print('%s on %s: shooting %d sprites %s' % (args.state, resource(e), len(sprites), sprites))
    shots = shoot(e, sprites)
    os.makedirs(IMG_DIR, exist_ok=True)
    manifest_path = os.path.join(IMG_DIR, 'taken.json')
    try:
        with open(manifest_path, encoding='utf-8') as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        manifest = {}
    for sprite, img in sorted(shots.items()):
        path = os.path.join(IMG_DIR, '%s_%s.png' % (args.area, sprite))
        img.save(path)
        # where this picture is valid: the state, and where the game was standing
        manifest['%s_%s' % (args.area, sprite)] = {'state': args.state,
                                                   'camera': list(e.pos()),
                                                   'map': resource(e)}
    with open(manifest_path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    missing = [s for s in sprites if s not in shots]
    print('%d saved in docs/sprite_img%s'
          % (len(shots), ', %d gave no picture: %s' % (len(missing), missing) if missing else ''))

    if args.npcs:
        e.load_state(args.state)
        e.wait(1.0)
        spots = where_they_stand(e, args.area)
        where = os.path.join(HERE, 'docs', 'npc_img')
        os.makedirs(where, exist_ok=True)
        for (script, block), img in sorted(spots.items()):
            img.save(os.path.join(where, '%s_%04x.png' % (script[:-4], block)))
        print('%d places saved in docs/npc_img' % len(spots))


if __name__ == '__main__':
    main()
