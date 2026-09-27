"""Turn lines read off the recorded playthrough into video anchors.

The VOD is sampled in the browser (docs/engine_notes.md, "Ordering from a recorded
playthrough"): every frame with a text box is logged with its timestamp, the frames are
grouped into conversations, and a few frames of each are read. What is read is a
fragment of a line - a speaker name and the first dozen characters - and this finds the
dump row it belongs to and records it in docs/video_anchors.json, which
tools/play_tour.py --to-play-order then turns into the order the scenes were seen in.

    python tools/vod_read.py readings.json        # [{"part": 1, "t": 3000, "text": "用心棒 へへへ、まさか"}, ...]
    python tools/vod_read.py --check              # which anchors resolve to a scene

A reading is matched by the longest prefix of its text (speaker name stripped) that
occurs in exactly one script's rows; ambiguous or unmatched readings are listed, not
guessed. Parts are laid end to end: 'at' = the part's offset + t.
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'tools'))

VIDEO = os.path.join(HERE, 'docs', 'video_anchors.json')
#  each recorded playthrough is a series of parts laid end to end; 'at' counts seconds
#  from the start of its first part. Two series never share an 'at' axis: the play
#  order takes one sequence per series (play_tour.video_sequences).
PART_LEN = {'twitch': {1: 6858, 2: 24319, 3: 29698, 4: 32371},        # sqpat's VODs
            'werdna': {1: 16732, 2: 9404, 3: 13674, 4: 9908}}         # WERDNA's YouTube streams
PART_OFFSET = {}
for _series, _lens in PART_LEN.items():
    _off = 0
    for _p in sorted(_lens):
        PART_OFFSET[_series, _p] = _off
        _off += _lens[_p]


def norm(s):
    s = re.sub(r'[\s　「」『』\\]|\[[A-Z]+\]', '', s or '')
    return s.replace('〜', 'ー').replace('~', 'ー').replace('…', '・・・').replace('‥', '・・')


def rows_by_script():
    """script -> [(offset, normalized Japanese)] from the dump workbook."""
    import openpyxl
    from rominfo import DUMP_XLS_PATH
    out = collections.defaultdict(list)
    ws = openpyxl.load_workbook(os.path.join(HERE, DUMP_XLS_PATH), read_only=True)['SCNs']
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] and r[0].endswith('.SCN') and isinstance(r[2], str):
            out[r[0][:-4]].append((int(str(r[1]), 16), norm(r[2])))
    return out


def script_rows():
    """script -> its first row in the context workbook (the story order)."""
    import play_tour
    out = {}
    for (fn, _off), _label in play_tour.scene_labels(play_tour.newest_context_workbook()).items():
        pass
    import openpyxl
    ws = openpyxl.load_workbook(play_tour.newest_context_workbook(), read_only=True)['SCNs']
    it = ws.iter_rows(values_only=True)
    col = {h: i for i, h in enumerate(next(it)) if h}
    for i, r in enumerate(it):
        fn = r[col['Filename']]
        if fn and fn.endswith('.SCN'):
            out.setdefault(fn[:-4], i)
    return out


def match(text, rows, prefer=None, after=None, order=None):
    """-> (script, offset, fragment) or (None, reason, fragment).

    The speaker name, if any, is what comes before the first 「 or the first space;
    the fragment is then tried from long to short until it is found in one script.
    The same line in two scripts (a townsperson repeats it on the next visit, in the
    next visit's file) is settled by time: the playthrough moves forward, so the
    script nearest *after* the previous anchor's place in the story order wins."""
    body = text
    if '「' in text:
        body = text[text.index('「'):]
    elif ' ' in text.strip():
        body = text.strip().split(' ', 1)[1]
    n = norm(body)
    for k in range(min(14, len(n)), 5, -1):
        frag = n[:k]
        hits = [(s, off) for s, rs in rows.items() for off, jp in rs if frag in jp]
        scripts = {s for s, _o in hits}
        if len(scripts) == 1:
            s, off = min(hits, key=lambda h: h[1])
            return s, off, frag
        if len(scripts) > 1 and order and after is not None:
            s = _nearest(scripts, order, after)
            off = min(o for sc, o in hits if sc == s)
            return s, off, frag
        if prefer and prefer in scripts:
            off = min(o for s, o in hits if s == prefer)
            return prefer, off, frag
        if len(scripts) > 1 and k <= 8:
            return None, 'in %d scripts: %s' % (len(scripts), ', '.join(sorted(scripts)[:5])), frag
    return None, 'not found', n[:12]


class Fuzzy:
    """Match text read by tools/vod_ocr.py, which has gaps ('?') and wrong kanji.

    Every 4-gram of the dump's rows is indexed; a reading's 4-grams nominate candidate
    rows, and the candidate sharing the longest common substring with the reading wins,
    if that substring is long enough to be more than chance (6 characters, or the whole
    row when the row is shorter)."""

    def __init__(self, rows):
        self.rows = rows
        self.index = collections.defaultdict(set)
        for s, rs in rows.items():
            for k, (_off, jp) in enumerate(rs):
                for i in range(len(jp) - 3):
                    self.index[jp[i:i + 4]].add((s, k))

    @staticmethod
    def lcs(a, b):
        best, prev = 0, [0] * (len(b) + 1)
        for ca in a:
            cur = [0] * (len(b) + 1)
            for j, cb in enumerate(b):
                if ca == cb and ca != '?':
                    cur[j + 1] = prev[j] + 1
                    if cur[j + 1] > best:
                        best = cur[j + 1]
            prev = cur
        return best

    def match(self, text, after=None, order=None):
        """-> (script, offset, fragment) or (None, reason, fragment)."""
        n = norm(text).replace(' ', '')
        cands = set()
        for i in range(len(n) - 3):
            g = n[i:i + 4]
            if '?' not in g:
                cands |= self.index.get(g, set())
        if not cands:                                   # a short line: try its 3-grams
            for i in range(len(n) - 2):
                g = n[i:i + 3]
                if '?' not in g:
                    cands |= {sk for key, sks in self.index.items() if g in key for sk in sks}
        if not cands:
            return None, 'no 4-gram of it is in the dump', n[:12]
        scored = []
        for s, k in cands:
            off, jp = self.rows[s][k]
            m = self.lcs(n, jp)
            if m >= 6 or (m == len(jp) and m >= 4):
                #  six characters of hiragana ("れるそうです") are in half the game;
                #  a shared run has to carry two kanji or katakana, or be long
                shared = _shared(n, jp)
                solid = sum(1 for c in shared if 'ァ' <= c <= 'ヺ' or '一' <= c <= '鿿')
                if m >= 12 or solid >= 2:
                    scored.append((m, s, off, jp))
        if not scored:
            return None, 'nothing shared with any row', n[:12]
        top = max(m for m, _s, _o, _jp in scored)
        hits = [(s, off, jp) for m, s, off, jp in scored if m == top]
        scripts = {s for s, _o, _jp in hits}
        if len(scripts) > 1 and order and after is not None:
            pick = _nearest(scripts, order, after)
            hits = [h for h in hits if h[0] == pick]
        elif len(scripts) > 1:
            return None, 'in %d scripts: %s' % (len(scripts), ', '.join(sorted(scripts)[:5])), n[:12]
        s, off, jp = min(hits, key=lambda h: h[1])
        #  the fragment recorded is the shared substring, so play_tour can find the row
        frag = _shared(n, jp)
        return s, off, frag


def _nearest(scripts, order, after):
    """The script nearest the previous anchor's place in the story order.

    Nearest in either direction: the townspeople of 02OLB01A repeat their lines in
    02OLB01B (the next visit's file), and while the previous anchor was 02OLB01, a few
    rows *below* 02OLB01A, "at or after" chose the next visit - which then dragged
    Albein's second visit up into the manor's first."""
    return min(scripts, key=lambda x: (abs(order.get(x, 0) - after), order.get(x, 0)))


def _shared(a, b):
    best = ''
    for i in range(len(a)):
        for j in range(i + len(best) + 1, len(a) + 1):
            f = a[i:j]
            if '?' in f:
                break
            if f in b:
                best = f
            else:
                break
    return best


def add_anchors(readings, log=print):
    rows = rows_by_script()
    fuzzy = Fuzzy(rows)
    spec = json.load(open(VIDEO, encoding='utf-8')) if os.path.exists(VIDEO) else {'anchors': []}
    for a in spec['anchors']:
        a.setdefault('series', 'twitch')
    have = {(a['series'], a.get('part'), a.get('t')) for a in spec['anchors']}
    added, problems = 0, []
    order = script_rows()
    for r in sorted(readings, key=lambda r: (r.get('series', 'twitch'), int(r['part']), int(r['t']))):
        series, part, t, text = r.get('series', 'twitch'), int(r['part']), int(r['t']), r['text']
        if (series, part, t) in have:
            continue
        at = PART_OFFSET[series, part] + t
        before = [a for a in spec['anchors'] if a['series'] == series and a['at'] < at and a['script'] in order]
        after = order[max(before, key=lambda a: a['at'])['script']] if before else None
        if r.get('lines') is not None or '?' in text:       # read by the OCR, not by eye
            script, off, frag = fuzzy.match(text, after=after, order=order)
        else:
            script, off, frag = match(text, rows, after=after, order=order)
        if not script:
            problems.append('%s part %d %5ds  %-24s %s' % (series, part, t, text[:24], off))
            continue
        spec['anchors'].append({'series': series, 'at': at, 'part': part, 't': t,
                                'script': script, 'line': frag, 'read': text, 'offset': '%#x' % off})
        added += 1
    spec['anchors'].sort(key=lambda a: (a['series'], a['at']))
    with open(VIDEO, 'w', encoding='utf-8') as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=1)
    log('%d anchors added (%d now); %d readings not placed' % (added, len(spec['anchors']), len(problems)))
    for p in problems:
        log('   ' + p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('readings', nargs='?')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if args.readings:
        add_anchors(json.load(open(args.readings, encoding='utf-8')))
    if args.check:
        import play_tour
        labels = play_tour.scene_labels(play_tour.newest_context_workbook())
        seq = play_tour.video_sequence(labels)
        print('%d scenes in the playthrough sequence' % len(seq))
        print(' -> '.join(seq[:60]))


if __name__ == '__main__':
    main()
