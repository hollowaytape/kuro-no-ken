"""Save a state in every area, by teleporting to each one.

A world-map exit is a single instruction - `20 <var 3> <N>`, writing the destination into
the global word variable array at 16d8:06d2 - so running that as a synthetic block sends
the player anywhere. Destinations 1..31 cover the game:

    1 ysk1 manor grounds   2 olb1 Albein      3 ysk2 manor      4 old
    5 sks1                 6 blk1             8 ckd             9 hik
   10 tni1                11 stg            12 gakusha2       13 haka
   14 ymm1               15 mkr1            16 isk1           17 drl1
   18 goblin_s           19 ire1            20 nnp            21 gagoil
   22 isk2               24 umb1            26 kkr            27 taicho_o
   28 mimic             29 knt             31 bac_11

With a state per area, everything that needs to run *in context* - sweeps, block
verification with the map's own objects, playtesting a scene - starts where it matters
instead of walking there.

    python tools/area_states.py [--from STATE] [--only 5 6 7] [--prefix area]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)


def leftover_script(emu):
    """A script left in a slot by the map we teleported from, i.e. one whose name does
    not share a prefix with anything else loaded. Returns its filename, or None."""
    from verify_blocks import loaded_scripts
    names = [fn for fn, _base in loaded_scripts(emu)]
    if len(names) < 2:
        return None
    prefixes = [n[:5] for n in names]
    for fn, pre in zip(names, prefixes):
        if prefixes.count(pre) == 1 and sum(1 for p in prefixes if p != pre) == len(names) - 1:
            if names.index(fn) != 0 and prefixes[0] != pre:
                return fn
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='base', default='ysk2_final')
    ap.add_argument('--only', nargs='*', type=int)
    ap.add_argument('--prefix', default='area')
    ap.add_argument('--max', type=int, default=31)
    args = ap.parse_args()

    from bench import RenderBench, SEG
    b = RenderBench(args.base)
    e = b.e
    dests = args.only or list(range(1, args.max + 1))
    print('teleporting from %s (%s)' % (args.base, e.map_name()))
    saved = []
    for n in dests:
        b.reset()
        at = b.free_at(8)
        e.write(SEG + at, bytes([0x20]) + int.to_bytes(3, 2, 'little')
                + int.to_bytes(n, 2, 'little') + bytes([0x83]))
        e.write(b.table() + 2 * 3, int.to_bytes(at, 2, 'little'))
        b.arm(3)
        for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
            e.tap(k, 0.25)
            e.wait(0.6)
            if e.state() != 'field':
                break
        for _ in range(6):
            e.wait(1.5)
            if e.state() == 'dos':
                break
        name = '%s_%02d' % (args.prefix, n)
        # Teleporting changes the map, but a slot is only reloaded if the new area needs
        # something different there. isk2 kept the manor's script in slot 1 and every
        # trigger on it then ran the wrong code - 19 "crashes" that were the state's
        # fault, not the game's. Flag it rather than save a state that lies.
        stale = leftover_script(e)
        if e.state() == 'dos':
            print('  %2d -> %-12s CRASHED, not saved' % (n, e.map_name()))
            continue
        # Let the map settle and give the player control before saving, or the state is
        # useless for anything that needs to move.
        e.wait(2.0)
        e.save_state(name)
        saved.append((n, e.map_name(), name, stale))
        print('  %2d -> %-12s %-8s %d zones  saved %s%s'
              % (n, e.map_name(), e.state(), len(e.zones()), name,
                 '   STALE SLOT: %s' % stale if stale else ''))
    bad = [x for x in saved if x[3]]
    print('%d area state(s) saved, %d with a stale script slot%s'
          % (len(saved), len(bad), ': ' + ', '.join(x[2] for x in bad) if bad else ''))


if __name__ == '__main__':
    main()
