"""Talk to every person and bump every door of a state with the follower's own trial:
which scripts each said, whether the party survived, where it landed.

    python tools/who_says.py STATE [STATE...]
"""
import sys, glob, zlib, collections
sys.path.insert(0, 'tools')
import autoplay
from autoplay import _trial, map_id
autoplay._worker_init()
t = autoplay._W; e = t.emu
for st in sys.argv[1:]:
    e.load_state(st); e.wait(0.4)
    base = zlib.compress(e.m.save_state(), 1)
    targets = [('npc', o['slot']) for o in e.objects()] + [(z['kind'], z['index']) for z in e.zones() if z['enabled']]
    print('==', st, map_id(autoplay.current_area(e), autoplay.current_region(e), e.map_sig()), len(targets), 'targets', flush=True)
    for tg in targets:
        r = _trial((base, tg))
        said = collections.Counter()
        for m, src, lines in r['pages']:
            if src:
                said[str(src[0])[:-4]] += 1
                continue
            for line in lines:
                hit = t.script.find_japanese(line)
                if hit:
                    said[str(hit[0])[:-4]] += 1
                    break
        landed = map_id(r['area'], r['region'], r['sig'][0]) if r['sig'] else r['state']
        print('  %-4s %2d -> %-9s %-10s pages %2d  %s' % (tg[0], tg[1], landed, r['outcome'][:10], len(r['pages']), dict(said.most_common(4))), flush=True)
