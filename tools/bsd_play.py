"""Run any battle script by name, the way a story battle starts it.

This is the .BSD counterpart of `verify_blocks.py`. Three scripts name a BSD inline -
28KDI, 29KNT and 20NNP93 - and the bytes around the name give the calling convention:

    8c 02 "d\\bac_11" 00     set the battle background
    b6 02 "d\DL21_O10" 00   fight this battle script
    83                      end of block

So a battle needs no disk staging and no map to be reached: write those three
instructions into the free space past the loaded map script, point a block-table slot
at them and take one step, exactly as bench.render() does for a line of dialogue.

    python tools/bsd_play.py D010_X10.BSD
    python tools/bsd_play.py D010_X10.BSD --state area11 --background bac_10
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))

import bsd_tool                                    # noqa: E402

BSD_BUF = 0x2aa80          # where the engine loads the battle script, every time

OP_BACKGROUND = 0x8c
OP_BATTLE = 0xb6
TAG = 0x02                 # the "nothing follows" operand tag; the path is inline
END = 0x83
MENU = ('Attack', 'Magic', 'Defend', 'Item', 'Equip', 'Run', 'Shinobu', 'HP ', 'MP ', 'ST ')


def block(bsd, background):
    def path(name):
        return b'd' + bytes([92]) + name.encode('ascii') + b'\x00'
    return (bytes([OP_BACKGROUND, TAG]) + path(background)
            + bytes([OP_BATTLE, TAG]) + path(bsd.rsplit('.', 1)[0])
            + bytes([END]))


def guard_sites(data):
    """Every `cmp cs:[var], imm` in the file -> {file offset: set of values compared}.

    A battle script gates its dialogue on bytes of itself: each site tests one byte
    against a constant and skips the lines after it if it does not match. That byte is
    the phase of the fight - an enemy having transformed, the boss below half health -
    so most of a long battle's script is unreachable in a fight that ends in two turns.
    Writing the byte makes those lines play straight away.

    The same byte is often compared to both 0 and 1 at different sites, so no single
    assignment reaches everything; `phases()` enumerates the combinations.
    """
    import struct
    parsed = bsd_tool.parse_bsd(data)
    spans = [(r.offset, r.end) for r in parsed['text_regions']]
    out = {}
    for j in range(len(data) - 6):
        if data[j:j + 3] != bytes([0x2e, 0x80, 0x3e]):
            continue
        if any(a <= j < b for a, b in spans):
            continue                       # a coincidence inside Shift-JIS text
        addr = struct.unpack_from('<H', data, j + 3)[0]
        if addr < len(data):
            out.setdefault(addr, set()).add(data[j + 5])
    return out


def phases(data, limit=8):
    """The guard assignments worth trying, most-different first."""
    import itertools
    sites = guard_sites(data)
    if not sites:
        return [{}]
    keys = sorted(sites)
    combos = [dict(zip(keys, vals))
              for vals in itertools.product(*(sorted(sites[k]) for k in keys))]
    return combos[:limit]


def interesting(line):
    s = line.strip()
    return s and not any(s.startswith(m) for m in MENU)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bsd', nargs='?')
    ap.add_argument('--all', action='store_true',
                    help='run every battle script that has dumped text, one after another')
    ap.add_argument('--state', default='auto_run12_08')
    ap.add_argument('--states', nargs='*',
                    help='with --all: try each of these states until the battle starts. '
                         'The game mounts one .FA1 at a time, so a battle script can only '
                         'be run from a map whose area has its archive open.')
    ap.add_argument('--background', default='bac_11')
    ap.add_argument('--seconds', type=float, default=60.0)
    ap.add_argument('--quiet-for', type=float, default=0.0,
                    help='watch this long before pressing anything')
    ap.add_argument('--defend', action='store_true',
                    help='pick Defend every turn, so the fight lasts long enough for '
                         'events that only fire part-way through it')
    ap.add_argument('--no-force', action='store_true',
                    help='do not satisfy the event guards; play the battle as it comes')
    args = ap.parse_args()

    from bench import RenderBench
    b = RenderBench(args.state)

    if not args.all and not args.bsd:
        print('name a .BSD, or pass --all')
        return 1
    if not args.all:
        lines = run_phases(b, args.bsd, args, verbose=True)
        if lines is None:
            print('%s never started here - try another --state' % args.bsd)
            return 1
        print('%d line(s) across all guard settings:' % len(lines))
        for line in lines:
            print('   %s' % line)
        return 0

    import fa1
    names = sorted(fa1.BSD_FILES_WITH_TEXT)
    print('running %d battle script(s)' % len(names))
    silent = []
    states = args.states or [args.state]
    for fn in names:
        pages = None
        for st in states:
            if st != args.state or len(states) > 1:
                e = b.e
                e.load_state(st)
                e.set_noclip(True)
                e.heal()
                b.base = e.m.save_state()
            pages = run_phases(b, fn, args, verbose=False)
            if pages:
                break
        if pages is None:
            print('%-14s  did not start' % fn)
            silent.append(fn)
            continue
        print('%-14s  %d line(s)' % (fn, len(pages)))
        for line in pages:
            print('        %s' % line)
        if not pages:
            silent.append(fn)
    print()
    print('%d of %d showed no text' % (len(silent), len(names)))
    if silent:
        print('   %s' % ' '.join(silent))
    return 0


def run_phases(b, bsd, args, verbose=True):
    """Run the battle once per guard assignment and merge everything it said.

    No single assignment reaches a whole boss script - the same byte gates the opening
    taunt at 0 and the second-phase lines at 1 - so each combination is worth one short
    fight.
    """
    src = os.path.join(HERE, 'patched', bsd)
    if not os.path.exists(src):
        src = os.path.join(HERE, 'original', 'decompressed', bsd)
    combos = [{}] if args.no_force else phases(open(src, 'rb').read())
    seen, out, started = set(), [], False
    for g in combos:
        lines = run_one(b, bsd, args, verbose=verbose, forced=g)
        if lines is None:
            continue
        started = True
        for line in lines:
            if line.strip() not in seen:
                seen.add(line.strip())
                out.append(line)
    return out if started else None


def run_one(b, bsd, args, verbose=True, forced=None):
    """Start `bsd` as a battle and return the lines it drew, or None if it never ran."""
    from bench import SEG, SCRIPT_IDX
    e = b.e
    code = block(bsd, args.background)
    b.reset()
    try:
        at = b.free_at(len(code))
    except AssertionError:
        # some maps load a script that fills slot 0; put the block in slot 1 instead
        at = 0x1800 - len(code) - 0x10
    e.write(SEG + at, code)
    e.write(b.table() + 2 * SCRIPT_IDX, int.to_bytes(at, 2, 'little'))
    b.arm(SCRIPT_IDX)
    b.clear_text()
    if verbose:
        print('on %s: running %s (%d byte block at %#x)' % (e.map_name(), bsd, len(code), at))
    for k in ('UP', 'LEFT', 'DOWN', 'RIGHT'):
        e.tap(k, 0.25)
        e.wait(0.6)
        if e.state() != 'field':
            break
    else:
        return None
    if e.state() != 'battle':
        return None
    src = os.path.join(HERE, 'patched', bsd)
    if not os.path.exists(src):
        src = os.path.join(HERE, 'original', 'decompressed', bsd)
    data = open(src, 'rb').read()
    g = {} if args.no_force else (forced if forced is not None else phases(data)[0])
    for addr, val in g.items():
        e.write(BSD_BUF + addr, bytes([val]))
    if verbose and g:
        print('forced %d guard(s): %s' % (len(g), ', '.join(
            '%#x=%d' % (a, v) for a, v in sorted(g.items()))))

    seen, out, t = set(), [], 0.0
    while t < args.seconds:
        for addr, val in g.items():
            e.write(BSD_BUF + addr, bytes([val]))
        for line in e.screen_text():
            if interesting(line) and line.strip() not in seen:
                seen.add(line.strip())
                out.append(line.rstrip())
        if t >= args.quiet_for:
            e.tap('SPACE', 0.08)
        e.wait(0.4)
        t += 0.5
        if t > 3 and e.state() == 'field':
            break
    return out


if __name__ == '__main__':
    sys.exit(main())
