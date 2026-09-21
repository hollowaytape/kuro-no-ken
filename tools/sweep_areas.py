"""Sweep every area for crashes: each NPC and trigger zone, on every map.

`area_states.py` leaves a save state in each of the game's areas, so this walks into
everything on all of them - the in-context check that script injection deliberately
cannot do, because here the map's own objects, flags and zone tables are real.

    python tools/sweep_areas.py [--states area_01 area_02 ...] [--out test_reports/areas.txt]

One process per area, because np2core allows a single Machine per process.
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--states', nargs='*')
    ap.add_argument('--out', default=os.path.join('test_reports', 'areas.txt'))
    ap.add_argument('--timeout', type=int, default=900)
    args = ap.parse_args()
    names = args.states or sorted(
        os.path.basename(p)[:-len('.np2core')]
        for p in glob.glob(os.path.join(HERE, 'states', 'area_*.np2core')))
    print('%d area(s) to sweep' % len(names))
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    rows, t0 = [], time.time()
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for name in names:
        try:
            p = subprocess.run([sys.executable, os.path.join('tools', 'sweep_map.py'), name],
                               capture_output=True, text=True, timeout=args.timeout,
                               cwd=HERE, env=env, errors='replace')
            out = p.stdout
        except subprocess.TimeoutExpired:
            out = '(timed out)'
        m = re.search(r'sweeping (\S+).*?(\d+) zones', out, re.S)
        n = re.search(r'(\d+) targets, (\d+) crashes', out)
        crashes = [l.strip() for l in out.splitlines() if 'CRASHED' in l]
        rows.append((name, m.group(1) if m else '?', n.group(1) if n else '?',
                     n.group(2) if n else '?', crashes))
        print('  %-10s %-12s %s targets, %s crashes  (%.0fs)'
              % (name, rows[-1][1], rows[-1][2], rows[-1][3], time.time() - t0), flush=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        bad = sum(1 for r in rows if r[3] not in ('0', '?'))
        f.write('%d areas swept, %d with crashes\n\n' % (len(rows), bad))
        for name, mapname, targets, crashes, lines in rows:
            f.write('%-10s %-12s %4s targets  %s crashes\n' % (name, mapname, targets, crashes))
            for l in lines:
                f.write('      %s\n' % l)
    print('-> %s' % args.out)


if __name__ == '__main__':
    main()
