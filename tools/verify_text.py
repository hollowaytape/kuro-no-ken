"""Render every translated line in the game's own text box and check how it looks.

`kuro_test.lint_script` checks the workbook statically (counting characters against the
box size). This checks the same lines the only way that can't be wrong: it makes the
running game print them and reads the text layer back.

What gets rendered is `reinsert.typeset()`'s output - the exact bytes the patched disk
would hold, page breaks and all - so the result is what a player would see.

It uses `tools/bench.RenderBench`, which writes a synthetic script block into the
free space past the loaded map script, points the map's block-address table at it and
steps the player into a relocated trigger zone. The engine does the rest, so the line
wrapping, the control codes and the glyphs are the real ones.

    python tools/verify_text.py [--state STATE] [--files 02OLB02A.SCN,...] [--limit N]
                          [--workers W] [--out test_reports/render_check.txt]
                          [--changed-since OLD.xlsx] [--resume]

`--changed-since` renders only cells whose English is not already in another workbook
(e.g. the repo's, after merging a translator's sheet). Results are written as each cell
finishes, and `--resume` skips cells already in the output file, so a run that dies
part-way - a worker crash takes the whole pool with it on Windows - loses nothing.

Reports, per cell: rows and columns used, text that never reached the screen, and
anything the engine drew that the script didn't ask for.
"""
import argparse
import multiprocessing as mp
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

BOX_COLS = 50          # measured in game with a ruler string
BOX_ROWS = 5           # and the box holds 5 rows; a 6th line is silently dropped
DEFAULT_STATE = 'r03_manor_inside'
CODE = re.compile(r'\\[a-z](?:\d+(?:,\d+)*)?')      # \f \n \i2 \c09 \w80,4 ...

_B = None


def _init(state):
    global _B
    from bench import RenderBench
    _B = RenderBench(state)


def script_bytes(text):
    """The bytes reinsert would write for this workbook cell."""
    from reinsert import typeset
    out = typeset(text.encode('cp932', errors='replace'))[0]
    return out.encode('cp932', errors='replace') if isinstance(out, str) else out


def _render(job):
    """One workbook cell -> the pages the game drew for it."""
    fn, off, text = job
    try:
        pages = _B.render(script_bytes(text))
    except Exception as ex:
        return (fn, off, None, '%s: %s' % (type(ex).__name__, str(ex)[:60]))
    if not pages:
        return (fn, off, None, 'did not render')
    clean = []
    for lines in pages:
        # The readback can show the last row twice (it is left on both text pages).
        if len(lines) > 1 and lines[-1] == lines[-2]:
            lines = lines[:-1]
        clean.append([l.strip() for l in lines])
    return (fn, off, clean, None)


def flat(s):
    """Text with control codes and spacing removed, for comparing what the workbook
    says against what the screen actually showed."""
    return re.sub(r'\s+', '', CODE.sub('', s))


def check(text, pages):
    """What's wrong with this cell as drawn, if anything."""
    bad = []
    for n, lines in enumerate(pages):
        if len(lines) > BOX_ROWS:
            bad.append('page %d: %d rows (the box holds %d)' % (n + 1, len(lines), BOX_ROWS))
        for l in lines:
            if len(l) > BOX_COLS:
                bad.append('page %d: %d columns: %r' % (n + 1, len(l), l[:60]))
        if any('\ufffd' in l for l in lines):
            bad.append('page %d: garbled glyphs' % (n + 1))
    want = flat(text)
    got = flat(''.join(''.join(p) for p in pages))
    if want != got:
        if want.startswith(got):
            bad.append('%d characters never reached the screen (ends %r)'
                       % (len(want) - len(got), text[-50:]))
        else:
            bad.append('drawn text differs from the script: %r' % (got[:60]))
    return bad


def known_english(path):
    """(filename, English) pairs already in another workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    seen = set()
    for sheet in wb.sheetnames:
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            fn, off, jp, jl, en = (list(row) + [None] * 5)[:5]
            if fn and isinstance(en, str) and en.strip():
                seen.add((fn, en))
    return seen


def jobs(files=None, limit=None):
    import openpyxl
    from rominfo import DUMP_XLS_PATH
    wb = openpyxl.load_workbook(DUMP_XLS_PATH, read_only=True)
    out = []
    for sheet in wb.sheetnames:
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            fn, off, jp, jl, en = (list(row) + [None] * 5)[:5]
            if not fn or not isinstance(en, str) or not en.strip():
                continue
            if files and fn not in files:
                continue
            out.append((fn, off, en))
            if limit and len(out) >= limit:
                return out
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', default=DEFAULT_STATE)
    ap.add_argument('--files', help='comma-separated script filenames to check')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--out', default=os.path.join('test_reports', 'render_check.txt'))
    ap.add_argument('--changed-since', metavar='XLSX',
                    help='only render cells whose English is not already in this workbook')
    ap.add_argument('--resume', action='store_true',
                    help='skip cells already recorded in --out')
    args = ap.parse_args()
    todo = jobs(set(args.files.split(',')) if args.files else None, args.limit)
    src = {(fn, off): text for fn, off, text in todo}
    print('%d cells to render' % len(todo), flush=True)
    if args.changed_since:
        seen = known_english(args.changed_since)
        before = len(todo)
        todo = [j for j in todo if (j[0], j[2]) not in seen]
        print('%d of %d cells are new or changed since %s'
              % (len(todo), before, args.changed_since), flush=True)
    done = set()
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    progress = args.out + '.progress'
    if args.resume and os.path.exists(progress):
        for line in open(progress, encoding='utf-8'):
            done.add(tuple(line.rstrip('\n').split('\t', 1)))
        todo = [j for j in todo if (j[0], str(j[1])) not in done]
        print('resuming: %d already done, %d to go' % (len(done), len(todo)), flush=True)
    mode = 'a' if args.resume else 'w'

    t0 = time.time()
    bad_cells = failed = n = 0
    with open(args.out, mode, encoding='utf-8') as f, \
            open(progress, mode, encoding='utf-8') as prog, \
            mp.Pool(args.workers, initializer=_init, initargs=(args.state,)) as pool:
        for n, (fn, off, pages, err) in enumerate(pool.imap(_render, todo, chunksize=4), 1):
            if err:
                failed += 1
                f.write('%-14s %-8s !! %s\n' % (fn, off, err))
            else:
                bad = check(src[(fn, off)], pages)
                if bad:
                    bad_cells += 1
                    f.write('%-14s %-8s %s\n' % (fn, off, '; '.join(bad)))
                    for k, lines in enumerate(pages):
                        for l in lines:
                            f.write('      %d|%s\n' % (k + 1, l))
            prog.write('%s\t%s\n' % (fn, off))
            f.flush()
            prog.flush()
            if n % 50 == 0:
                print('  %d/%d  %.0fs' % (n, len(todo), time.time() - t0), flush=True)
    print('%d cells, %d with problems, %d could not render, %.0fs -> %s'
          % (n, bad_cells, failed, time.time() - t0, args.out), flush=True)


if __name__ == '__main__':
    main()
