"""Collect the actionable findings from every playtest report into one list.

Each run writes its own test_reports/<run>_report.txt, and most of what they contain is
"untranslated", which is expected for most of the game. This pulls out the kinds that
mean something is wrong with the patch and merges them across runs.

    python tools/issues_report.py [--all] [--out test_reports/issues.md]
"""
import argparse
import collections
import glob
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
# Worth acting on, most serious first. "untranslated" and "nonascii" are left out
# unless --all: the game is mostly untranslated, so they are the background.
ACTIONABLE = ('crash', 'gameover', 'garbage', 'not-inserted', 'truncated', 'overflow',
              'codes', 'stuck-text', 'unmatched', 'route')


def parse(path):
    """-> [(kind, detail)] from a report's '== kind (n)' sections."""
    out, kind = [], None
    for line in open(path, encoding='utf-8'):
        m = re.match(r'== (\S+)', line)
        if m:
            kind = m.group(1)
            continue
        if line.startswith('--- '):
            kind = None
        elif kind and line.startswith('  ['):
            out.append((kind, line.strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true', help='include untranslated/nonascii')
    ap.add_argument('--min-run', type=int, default=0,
                    help='only runs numbered >= this (older reports predate the fixes)')
    ap.add_argument('--out', default=os.path.join('test_reports', 'issues.md'))
    args = ap.parse_args()
    found = collections.defaultdict(lambda: collections.defaultdict(set))
    runs = 0
    for path in sorted(glob.glob(os.path.join(HERE, 'test_reports', '*_report.txt'))):
        run = os.path.basename(path)[:-len('_report.txt')]
        m = re.search(r'(\d+)$', run)
        if args.min_run and not (m and int(m.group(1)) >= args.min_run):
            continue
        runs += 1
        for kind, detail in parse(path):
            if args.all or kind in ACTIONABLE:
                found[kind][detail].add(run)
    order = [k for k in ACTIONABLE if k in found] + sorted(set(found) - set(ACTIONABLE))
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        def out(*t, **kw):
            print(*t, file=f, **kw)

        out('# Playtest findings worth acting on', end='\n\n')
        out('Merged from %d run report(s)%s. "untranslated" is left out;'
            % (runs, ' numbered %d and up' % args.min_run if args.min_run else ''))
        out('run `python tools/issues_report.py --all` to include it.', end='\n\n')
        total = 0
        for kind in order:
            items = found[kind]
            total += len(items)
            out('## %s (%d)' % (kind, len(items)), end='\n\n')
            for detail, in_runs in sorted(items.items()):
                out('- %s  _(%s)_' % (detail, ', '.join(sorted(in_runs)[:3])))
            out()
        out('%d distinct findings across %d kinds.' % (total, len(order)))
    print('%d runs, %d kinds, %d distinct findings -> %s'
          % (runs, len(order), sum(len(v) for v in found.values()), args.out))


if __name__ == '__main__':
    main()
