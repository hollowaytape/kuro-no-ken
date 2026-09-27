"""When did each area's text actually play, according to the autoplay runs?

`story_order.py` works out the order from the scripts alone, and for a few areas the
scripts say nothing: nothing dates them, and only the world map leads to them (whose exits
are gated by the zone table's 0x80 bit, not by script). The playtests can answer where the
scripts cannot, because a save state carries the story counters in RAM:

* every autoplay run wrote `states/<run>_NN.np2core` and `test_reports/<run>_report.txt`,
* the report's transcript says which lines were shown, which maps back to the dump rows,
* the state says what the story counters were at the time (variables at 16d8:06d2 + 2*i).

So "36 lines that exist only in 12MRS.SCN were shown in auto_run14, whose state has
0x84 = 1 and every other counter still 0" dates the Isle of Forests to just after the
first manor visit - which is where the scripts alone could not put it.

Two things to keep in mind when reading the result:

* the autoplayer is not a story playthrough. It starts from a save state and walks into
  whatever trigger zones are open, so this says "this content plays at that point", not
  "this is the first time the story sends you here";
* a run only proves what it reached. An area no run visited (13SLP, 21KTI, 22MZI) gets
  nothing here.

    python tools/seen_when.py                 # report, and write docs/playtest_clocks.json
    python tools/seen_when.py --no-write      # just the report
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

BD, VARS = 0x16d80, 0x06d2
OUT = os.path.join(HERE, 'docs', 'playtest_clocks.json')
MIN_LINES = 3          # one shared phrase proves nothing; three of a file's own lines do


def norm(s):
    return re.sub(r'[\s　「」]|\\[a-z]\d*|\[[A-Z]+\]', '', s or '')


def meaty(s):
    """Long enough to identify a file - not 「・・・・・・」, which half the game shares."""
    return len(re.sub(r'[・。、！？…]', '', s)) >= 6


def own_lines():
    """filename -> its lines that no other script has."""
    import openpyxl
    from rominfo import DUMP_XLS_PATH
    owners = collections.defaultdict(set)
    wb = openpyxl.load_workbook(DUMP_XLS_PATH, read_only=True)
    for r in wb['SCNs'].iter_rows(min_row=2, values_only=True):
        if r[0] and isinstance(r[2], str):
            key = norm(r[2])[:14]
            if meaty(key):
                owners[key].add(r[0])
    out = collections.defaultdict(list)
    for key, files in owners.items():
        if len(files) == 1:
            out[next(iter(files))].append(key)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-write', action='store_true')
    args = ap.parse_args()

    from kuro_core import CoreEmu
    import story_order as so

    clocks = sorted(so.counters(so._scripts()))
    lines = own_lines()
    e = CoreEmu()

    def state_clocks(name):
        try:
            e.load_state(name)
        except Exception:
            return None
        return {v: int.from_bytes(bytes(e.read(BD + VARS + 2 * v, 2)), 'little') for v in clocks}

    seen = collections.defaultdict(list)
    for rep in sorted(glob.glob(os.path.join(HERE, 'test_reports', '*_report.txt'))):
        run = os.path.basename(rep)[:-len('_report.txt')]
        st = next((s for s in ('%s_01' % run, '%s_02' % run)
                   if os.path.exists(os.path.join(HERE, 'states', s + '.np2core'))), None)
        if not st:
            continue
        cl = state_clocks(st)
        if cl is None:
            continue
        txt = norm(open(rep, encoding='utf-8', errors='replace').read())
        for fn, own in lines.items():
            n = sum(1 for l in own if l in txt)
            if n >= MIN_LINES:
                seen[fn[:5]].append((cl, run, fn, n))

    # earliest = the run whose counters had advanced least
    rank = lambda c: tuple(c.get(v, 0) for v in clocks)
    result = {}
    for a in sorted(seen):
        cl, run, fn, n = min(seen[a], key=lambda x: rank(x[0]))
        result[a] = {'clocks': {'%#x' % k: v for k, v in cl.items() if v},
                     'run': run, 'file': fn, 'lines': n}
        print('%-6s seen in %-12s (%s, %d of its own lines)  counters: %s'
              % (a, run, fn, n, ' '.join('%s=%d' % kv for kv in sorted(result[a]['clocks'].items()))
                 or 'all zero'))
    if not args.no_write:
        with open(OUT, 'w') as f:
            json.dump(result, f, indent=1, sort_keys=True)
        print('-> %s' % OUT)


if __name__ == '__main__':
    main()
