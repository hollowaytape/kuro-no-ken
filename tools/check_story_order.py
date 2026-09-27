"""Is the context workbook in causal order? Nothing above what it depends on.

The rule the reading order has to satisfy: **no conversation sits above anything it
depends on**. A line the game only shows after a counter has been advanced, a flag set,
or a script loaded at a later stage, must come below the conversation that does that.
`story_order.dependencies` lists every such need, read off the scripts; this maps them
onto the rows of a context workbook and reports every one the row order breaks.

A need is satisfied by *any one* of its satisfiers (a flag set in three places is set
once the first of them has run), so a need is broken only when the row is above all of
them. A satisfier with no text of its own (a stage script that only sets flags) cannot
be placed by rows, and a need with such a satisfier is not checked - that is reported as
"unverifiable" rather than as a pass.

Also reported, as softer evidence:

* visits: an area's stage n scenes below its stage n-1 scenes;
* the recorded playthrough (docs/video_anchors.json): anchors whose row order disagrees
  with the order they were played in. One player's route, so a disagreement is a lead,
  not a fault;
* "before X": a line shown only until scene X happens, placed below X. Harmless to the
  reader, but odd.

    python tools/check_story_order.py KuroNoKen_dump_context.xlsx
    python tools/check_story_order.py KuroNoKen_dump_context.xlsx --all   # every row, not one per scene

Exit status is the number of hard violations (0 = in order).
"""
import argparse
import bisect
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))


def read_rows(path):
    """-> (header -> column, [row tuples]) of the SCNs sheet."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    it = wb['SCNs'].iter_rows(values_only=True)
    col = {h: i for i, h in enumerate(next(it)) if h}
    return col, list(it)


class Sheet:
    """The rows of a context workbook, addressable by script, block and entry."""

    def __init__(self, path):
        import story_order as so
        self.so = so
        self.col, self.rows = read_rows(path)
        self.scripts = so._scripts()
        self.blocks = {}
        self.entries = collections.defaultdict(list)
        for (sfn, entry) in so.all_conditions(self.scripts):
            self.entries[sfn[:-4]].append(entry)
        for v in self.entries.values():
            v.sort()
        self.first = {}          # ('script', n) / ('block', n, b) / ('entry', n, e) -> first row index
        self.info = []           # per row: (name, block, entry, offset, scene) or None
        for i, r in enumerate(self.rows):
            fn = r[self.col['Filename']]
            if not fn or not fn.endswith('.SCN'):
                self.info.append(None)
                continue
            name = fn[:-4]
            try:
                off = int(str(r[self.col['Offset']]), 16)
            except ValueError:
                self.info.append(None)
                continue
            block = self.block_of(name, off)
            entry = self.entry_of(name, off, block)
            self.info.append((name, block, entry, off, r[self.col['Scene']]))
            for key in (('script', name), ('block', name, block), ('entry', name, entry)):
                self.first.setdefault(key, i)

    def block_of(self, name, off):
        if name not in self.blocks:
            got = self.so._blocks_of(name)
            self.blocks[name] = got[2] if got else []
        return max([s for s in self.blocks[name] if s <= off], default=None)

    def entry_of(self, name, off, block):
        """The entry point a row is reached through: the last one at or before it in
        its own block (story_order.place_of)."""
        ents = self.entries.get(name, ())
        i = bisect.bisect_right(ents, off) - 1
        if i >= 0 and (block is None or ents[i] >= block):
            return ents[i]
        return None

    def where(self, name, block):
        """First row of a (script, block) satisfier; for a script with no text, of the
        first scene it loads (story_order.stand_ins); None when nothing stands for it."""
        if block is not None and ('block', name, block) in self.first:
            return self.first[('block', name, block)]
        if ('script', name) in self.first:
            return self.first[('script', name)]
        if not hasattr(self, 'stand_in'):
            self.stand_in = self.so.stand_ins(self.scripts)
        for group in (self.stand_in.get((name, block), self.stand_in.get(name, ())),
                      self.stand_in.get(('loader', name), ())):
            rows = [self.first[('script', k)] for k in group if ('script', k) in self.first]
            if rows:
                return min(rows)
        return None


def hard_violations(sheet, every_row=False):
    """[(row, name, scene, kind, label, satisfier name, satisfier block, its row)]"""
    deps = sheet.so.dependencies(sheet.scripts)
    out, unverifiable, seen = [], 0, set()
    for i, info in enumerate(sheet.info):
        if not info:
            continue
        name, block, entry, off, scene = info
        for key in (('script', name), ('block', name, block), ('entry', name, entry)):
            for kind, label, alts in deps.get(key, ()):
                if not every_row and (scene, key, kind, label) in seen:
                    continue
                seen.add((scene, key, kind, label))
                places = [(sheet.where(n, b), n, b) for n, b in alts]
                placed = [x for x in places if x[0] is not None]
                if placed and min(placed)[0] <= i:
                    continue                    # met by one that has text
                if len(placed) < len(places):
                    unverifiable += 1           # only a text-less one could meet it
                    continue
                p, n, b = min(placed)
                out.append((i, name, scene, kind, label, n, b, p))
    return out, unverifiable


def visit_order(sheet):
    """Stage n of an area below stage n - 1: [(hub, n, first row, n - 1, its first row)]."""
    so = sheet.so
    out = []
    for hub, d in sheet.scripts.items():
        if not re.fullmatch(r'\d\d[A-Z]+', hub):
            continue
        var = so.stage_var(hub)
        stages = collections.defaultdict(set)
        for v, val, child in so.hub_cases(d):
            if v == var:
                stages[val].add(child)
        rows = {}
        for val, kids in stages.items():
            at = [sheet.first[('script', k)] for k in kids if ('script', k) in sheet.first]
            if at:
                rows[val] = min(at)
        prev = None
        for val in sorted(rows):
            if prev is not None and rows[val] < rows[prev] and stages[val] != stages[prev]:
                out.append((hub, val, rows[val], prev, rows[prev]))
            prev = val
    return out


def norm(s):
    return re.sub(r'[\s　「」]|\\[a-z]\d*|\[[A-Z]+\]', '', s or '')


def anchors(sheet):
    """[(seconds, script, row or None, note)] for docs/video_anchors.json."""
    path = os.path.join(HERE, 'docs', 'video_anchors.json')
    if not os.path.exists(path):
        return []
    jp = sheet.col['Japanese']
    out, prev, series = [], 0, None
    #  one recorded playthrough at a time: each series is its own route
    for a in sorted(json.load(open(path, encoding='utf-8'))['anchors'],
                    key=lambda a: (a.get('series', 'twitch'), a['at'])):
        if a.get('series', 'twitch') != series:
            series, prev = a.get('series', 'twitch'), 0
        key = norm(a['line'].split(' (')[0])
        hit = next((i for i, r in enumerate(sheet.rows)
                    if sheet.info[i] and sheet.info[i][0] == a['script']
                    and key and key in norm(r[jp])), None)
        note = ''
        if hit is None:
            note = 'not found'
        elif hit < prev:
            note = '%d rows above the anchor before it' % (prev - hit)
        out.append((a['at'], '%s %s' % (series, a['script']), hit, note))
        if hit is not None:
            prev = max(prev, hit)
    return out


def before_after(sheet):
    """'before X' lines placed below X: [(row, scene, X, X's row)]."""
    scene_first = {}
    for i, info in enumerate(sheet.info):
        if info and info[4]:
            scene_first.setdefault(info[4], i)
    out, seen = [], set()
    sw = sheet.col.get('Shown when')
    if sw is None:
        return out
    for i, r in enumerate(sheet.rows):
        for m in re.finditer(r'before ([0-9A-Z]+ #\d+)', str(r[sw] or '')):
            ref = m.group(1)
            scene = sheet.info[i][4] if sheet.info[i] else None
            if ref in scene_first and scene_first[ref] < i and (scene, ref) not in seen:
                seen.add((scene, ref))
                out.append((i, scene, ref, scene_first[ref]))
    return out


def fmt_label(kind, label):
    if kind == 'flag':
        return 'flag %#x set' % label
    if kind == 'stage':
        return 'var %#x >= %d' % label
    if kind == 'load':
        return 'loaded at ' + ', '.join('%#x == %d' % vn for vn in label)
    if kind == 'step':
        return 'its own counter %#x >= %d' % label
    return 'the milestone before it'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('workbook')
    ap.add_argument('--all', action='store_true', help='report every row, not one per scene')
    ap.add_argument('--quiet', action='store_true', help='totals only')
    args = ap.parse_args()
    sheet = Sheet(args.workbook)
    hard, unverifiable = hard_violations(sheet, args.all)
    print('%d rows; %d causal violations (%d needs unverifiable: a satisfier with no text)'
          % (len(sheet.rows), len(hard), unverifiable))
    if not args.quiet:
        for i, name, scene, kind, label, n, b, p in hard:
            print('  row %5d %-13s needs %-26s -> %s%s at row %d (%d rows below)'
                  % (i + 2, scene or name, fmt_label(kind, label), n,
                     ' @%#x' % b if b is not None else '', p + 2, p - i))
    visits = visit_order(sheet)
    print('%d areas with a visit below the one before it' % len(visits))
    if not args.quiet:
        for hub, val, row, prev, prow in visits:
            print('  %-6s stage %d at row %d, stage %d at row %d' % (hub, val, row + 2, prev, prow + 2))
    anc = anchors(sheet)
    if anc:
        #  Script by script: where each script was first seen in the playthrough, in that
        #  order, against where the sheet has it. (Anchor by anchor is meaningless once a
        #  machine has read thousands of them - one revisit line lifts the bar for all that
        #  follow.)
        first = collections.OrderedDict()
        for at, script, row, note in anc:
            if row is not None:
                first.setdefault(script, (at, row))
        by_series = collections.defaultdict(list)
        for script, (at, row) in first.items():
            by_series[script.split()[0]].append((at, script, row))
        for series, seen in by_series.items():
            up = [(a, b) for a, b in zip(seen, seen[1:]) if b[2] < a[2]]
            print('%s: %d of %d scripts first seen sit above the script first seen before them'
                  % (series, len(up), len(seen)))
            if not args.quiet:
                for a, b in up:
                    print('  %6ds %-16s row %-5d above %-16s row %d' % (b[0], b[1], b[2] + 2, a[1], a[2] + 2))
    soft = before_after(sheet)
    print('%d scenes shown only *before* another scene sit below it' % len(soft))
    if not args.quiet:
        for i, scene, ref, p in soft[:40]:
            print('  row %5d %-13s before %-13s (row %d)' % (i + 2, scene, ref, p + 2))
        if len(soft) > 40:
            print('  ...')
    return len(hard)


if __name__ == '__main__':
    sys.exit(main())
