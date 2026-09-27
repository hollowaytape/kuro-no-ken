"""Add per-line context columns to the dump workbook, for the translator.

The dump is a flat list of strings in file order, which is enough to reinsert but not
enough to translate well: a cell gives no hint of who is speaking, who they are speaking
to, which conversation it belongs to, or what has to have happened for the player to see
it.

All of that is already derivable from the scripts, so this writes it into the workbook
next to each line (columns H onward, left of nothing the reinserter reads):

    Story order one number per row across the game: sort by it to read in play order
                (tools/story_order.py - the story counters and area hubs)
    Area        the place, from the filename prefix and the Names + Places glossary
    Scene       one continuous conversation - every line the game shows in an unbroken
                run of text boxes. Shaded in alternating bands so a scene reads as one
                block, with a rule above each new scene and a hairline where the game
                closes one text box and opens the next.
    Who         who is speaking and who they are speaking to ("Shinobu -> Innkeep").
                The speaker comes from the game's own name plate, held for the rest of
                its block; failing that from a short note the translator left in column G
                ("Innkeep", "Girl with dog"); failing that from the *map object* that
                speaks the block - its sprite and the tile it stands on, "sprite 8 @19,15"
                (tools/npcs.py), which becomes a name once that sprite is named in
                tools/npc_names.json.
    Shown when  what has to be true for the line to play, in the sheet's own terms:
                "visit 3 of 6", "first time only", "after 06BLK02A #4" (the scene that
                sets the flag this one tests) - and that one is a link to the scene, with
                its first lines on hover.
    Where it happens
                a photograph of the spot the scene plays on (tools/sprite_shots.py), on
                the row the scene starts on.

Gating comes from the interpreter's three flag instructions (docs/engine_notes.md). What
matters here is which way the *following* code runs, and that was settled by running it,
not by reading the handler: the manor Chancellor's three-page introduction
(03YSK01B 0x241, behind `0c 73 00 <addr>`) plays with flag 0x73 **clear**, and a single
line once it is set. So:

    0c <flag> <addr>   jumps to <addr> if SET   -> code up to <addr> runs when CLEAR
    0d <flag> <addr>   jumps to <addr> if CLEAR -> code up to <addr> runs when SET
    1d <flag>          set the flag

`0c ... 1d <same flag> ... text` is the "first time only" idiom: the lines play once, and
setting the flag skips them from then on.

A print at P is gated by every test at `at` whose jump target t satisfies at < P < t. A
flag is then named by *who sets it*: the same `1d <flag>` instructions, matched to the
scene they sit in, all over the game - so "after 06BLK02A #4" instead of "flag 0x73 set".

The rows are written in story order (tools/story_order.py), and the last word on that
order is not a heuristic but a rule: no conversation above anything it depends on
(`causal_pass`). tools/check_story_order.py verifies a finished workbook against it.

    python tools/translator_context.py                       # rewrite KuroNoKen_dump.xlsx in place
    python tools/translator_context.py --out annotated.xlsx  # or to a copy
    python tools/translator_context.py --files 03YSK01A.SCN  # just these, for a quick look
    python tools/translator_context.py --basis basis.txt     # the debug column, to a file

Re-running is idempotent: the columns are recomputed from the scripts, and the
translator's own columns (A-G) are never touched - not even their fills, which carry the
translator's own green/red marking.
"""
import argparse
import bisect
import collections
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

from copy import copy                                         # noqa: E402

import script_decode as sd                                    # noqa: E402
from script_map import slot_base, block_starts, strings       # noqa: E402

ORIG = os.path.join(HERE, 'original', 'decompressed')

TEST_CLEAR, TEST_SET, SET_FLAG = 0x0c, 0x0d, 0x1d

HEADERS = ['Story order', 'Area', 'Scene', 'Who', 'Shown when']

# The sheet as a translator reads it: what the line is and who says it first, the line
# itself next, and the machinery (which file, which offset) last. The row number is the
# story order - the rows are written in it - so there is no column for that and nothing to
# sort. romtools finds Japanese/English/Filename/Offset by their header, not their
# position, so the build reads this layout unchanged.
LAYOUT = ['Area', 'Scene', 'Who', 'Shown when', 'Japanese', 'JP_Len', 'English', 'EN_Len',
          'Comments', 'Filename', 'Offset']
#   Every column carries the scene's shade except the English one, which is where the
#   translator's own green and red live.
BAND_COLS = [i for i, h in enumerate(LAYOUT, 1) if h != 'English']
WIDTHS = {'Area': 20, 'Scene': 16, 'Who': 26, 'Shown when': 30, 'Japanese': 46,
          'JP_Len': 7, 'English': 52, 'EN_Len': 7, 'Comments': 30, 'Filename': 14,
          'Offset': 9}
ORDER_COL = 0        # the one story_order fills for every row, not per file
FIRST_COL = 8        # column H; A-G are the translator's own
NOT_TEXT = 'NOT TEXT - game code, leave blank'


def glossary(wb):
    """-> (area prefix -> name, Japanese character name -> English)."""
    areas, names = {}, {}
    if 'Names + Places' not in wb.sheetnames:
        return areas, names
    for row in wb['Names + Places'].iter_rows(min_row=2, values_only=True):
        src, jp, en, note = (list(row) + [None] * 4)[:4]
        label = en or note
        if src and label:
            areas[str(src).strip().upper()] = str(label).strip()
        elif jp and not src:
            names[str(jp).strip()] = str(en).strip() if en else ''
    return areas, names



#   The translator's own marking on the English column, in Google Sheets' palette. Green
#   was never a comment: those cells *were* formulas reading the name out of Names +
#   Places, so a character's English name is written once and shows up on all 1900 rows
#   that say it. Somewhere in the round trip through openpyxl the formulas were flattened
#   - a `data_only=True` load followed by a save keeps what a cell displayed and drops how
#   it got there, and for the rows Excel had never calculated it kept nothing at all,
#   which is why 785 of them came back blank. Pink is the translator's "not sure, come
#   back to this", and is carried through untouched on the row it was put on.
GREEN_MARK = {'FFB7E1CD', 'FFD9EAD3'}
GLOSSARY = 'Names + Places'


def glossary_rows(wb):
    """-> {name plate: (row in Names + Places, its English)}.

    Indexed both ways round, the same rule the build uses to fill a blank plate: the
    glossary holds full names, and the plates in the game are first names - it says
    シノブ・リュード where the game says シノブ.
    """
    out = {}
    if GLOSSARY not in wb.sheetnames:
        return out
    for n, row in enumerate(wb[GLOSSARY].iter_rows(min_row=2, values_only=True), 2):
        src, jp, en = (list(row) + [None] * 3)[:3]
        if src or not (jp and en):           # a row with a file prefix is a place, not a name
            continue
        jp, en = str(jp).strip(), str(en).strip()
        for key in (jp, jp.split('\u30fb')[0]):
            if key:
                out.setdefault(key, (n, en))
    return out



def formula_cells(ws, cols, gloss_rows):
    """-> {(file, offset): formula} for the name plates that should read the glossary.

    Decided per *cell of the game*, not per row of the sheet: a few lines appear twice in
    the dump, and the two rows need not both be green. Converting one and leaving the
    other made the pair disagree - 02OLB03A @0x49f came out as `Keiuss` on one row and the
    formula on the other - which `ordered_dump` rightly refuses to build.

    So a cell gets the formula when at least one of its rows is marked green *and* no row
    says anything other than what the glossary says. A row with different English is the
    translator overriding the glossary for that line, and it keeps its wording.
    """
    fn_i, off_i = cols['Filename'], cols['Offset']
    en_i, jp_i = cols['English'], cols['Japanese']
    marked, override = {}, set()
    for n in range(2, ws.max_row + 1):
        key = (ws.cell(n, fn_i + 1).value, ws.cell(n, off_i + 1).value)
        cell = ws.cell(n, en_i + 1)
        jp = ws.cell(n, jp_i + 1).value
        got = gloss_rows.get((jp or '').strip().strip('\u3000').strip())
        fill = cell.fill
        green = (fill and fill.fill_type
                 and getattr(fill.start_color, 'rgb', None) in GREEN_MARK)
        if cell.value and (not got or str(cell.value).strip() != got[1]):
            override.add(key)
        if green and got:
            marked[key] = "='%s'!C%d" % (GLOSSARY, got[0])
    return {k: v for k, v in marked.items() if k not in override}


def plate_formula(japanese, rows):
    """The formula that reads this name plate out of the glossary, or None."""
    got = rows.get((japanese or '').strip().strip('\u3000').strip())
    if not got:
        return None
    return "='%s'!C%d" % (GLOSSARY, got[0])


def area_for(filename, areas):
    m = re.match(r'[0-9]*[A-Z]+', filename)
    if not m:
        return ''
    key = m.group(0)
    # 10TNII and 26KKRI are sub-areas of 10TNI / 26KKR; fall back to the shorter prefix.
    for k in (key, key[:-1]):
        if k in areas:
            return areas[k]
    return ''


def looks_like_name(jp, names, next_jp=''):
    """A speaker label: a bare name on its own line, not a sentence.

    Either a name from the glossary, or something short and unpunctuated that the *next*
    line answers with dialogue - which is how the game lays a name plate out. Without that
    second test the intro's narration ("Long ago...") was read as a speaker name.
    """
    if not jp:
        return False
    s = jp.strip().strip('　')
    if not s:
        return False
    if s in names:
        return True
    # Dialogue and narration carry quotes or sentence punctuation; a label does not.
    if len(s) > 7 or any(c in s for c in '「」。、・？！\\'):
        return False
    return '「' in (next_jp or '')


def flag_gates(insns, base):
    """-> [(at, flag, needs_set, until)] for every flag test, as file offsets.

    `needs_set` is the state the code *after* the test requires - the opposite of the
    state that takes the jump (see the module docstring for how that was confirmed).
    """
    out = []
    for at, op, vals in insns:
        if op in (TEST_CLEAR, TEST_SET) and len(vals) >= 2:
            flag = vals[0][2]
            target = vals[1][2] - base
            out.append((at, flag, op == TEST_SET, target))
    return out


def flags_set(insns):
    return {(at, vals[0][2]) for at, op, vals in insns if op == SET_FLAG and vals}


LOOSE_GAP = 0x40            # a real run of code between two lines, not just a text box


def page_continues(data, offset):
    """Does the game keep the text box open after the string at `offset`?

    `\\n` (5c 6e) continues the page, `\\f` (5c 66) or any opcode ends it. Same rule as
    reinsert.cell_ends_page, kept here so this tool does not import the reinserter. The
    workbook shows it as a hairline rule between text boxes rather than as a column.
    """
    i = offset
    while i < len(data):
        b = data[i]
        if 0x81 <= b <= 0x9f or b >= 0xe0:
            i += 2
            continue
        if b == 0x5c and i + 1 < len(data) and data[i + 1] == 0x6e:
            return True
        if b < 0x20 or b == 0x5c:
            return False
        i += 1
    return False


def conversations(rows, gap=LOOSE_GAP, starts=None):
    """Group a file's rows into continuous conversations.

    A conversation is a **script block**: everything the game plays from one trigger, which
    is exactly what a translator wants to read in one piece. Inside a block the speeches are
    separated by the 13 bytes that close one text box and open the next
    (` 00 09 15 30 04 06 30 40 02`), so they stay together; a bigger run of bytes is real
    code, and splits.

    Measuring gaps alone - the first version of this - said 8 bytes, because that is the
    largest gap *within a single speech*. It then cut a conversation into one scene per
    speech: the Shinobu/Innes exchange at the start of 02OLB01 came out as five scenes, and
    sorting by story order made that look like the order was broken when it was the
    grouping. Where a file's blocks cannot be decoded there is nothing to fall back on but
    the gap, and 0x40 is the value that does not cut between speeches.
    """
    def block_of(off):
        return max([s for s in starts if s <= off], default=None) if starts else None

    out, cur, end, here = [], [], None, None
    for off in sorted(rows):
        block = block_of(off)
        if cur and (off - end >= gap or (starts and block != here)):
            out.append(cur)
            cur = []
        cur.append(off)
        here = block
        end = off + len((rows[off] or '').encode('cp932', 'replace'))
    if cur:
        out.append(cur)
    return out


#   Compare-and-branch opcodes (script_decode): even ones compare a variable with a
#   constant. What matters here is the *lower bound* each side puts on the variable.
STAGE_JUMPS = {0x10: 'ne', 0x12: 'eq', 0x14: 'le', 0x16: 'lt', 0x18: 'gt', 0x1a: 'ge'}


def _stage_floor(kind, value, taken):
    """The smallest value the variable can have, or None when the test says nothing.

    `taken` is True for the code the jump skips (the condition's own side) and False for
    the code after the jump target, which is where the other case falls.
    """
    if kind == 'ne':                       # jumps away when var != value
        return value if taken else (1 if value == 0 else None)
    if kind == 'eq':                       # jumps away when var == value
        return None if taken else value
    if kind == 'gt':                       # jumps away when var > value
        return None if taken else value + 1
    if kind == 'ge':
        return None if taken else value
    return None


def block_conditions(info):
    """{block: {'stage': (var, floor), 'first_time': bool}} for blocks run by `b0`.

    A scene is often not gated where its text is, but where the *call* to it is. Innes's
    talk stub is the clearest case:

        10 84 00 00 00 <else>    if Albein's counter is not 0, go to <else>
        b0 00 18 3d              (counter 0) the first-meeting conversation
        <else> 0c 66 00 <done>   if flag 0x66 is set, skip
        1d 66 00                 set it
        b0 00 29 1c              -> the block where Innes admits the theft

    so the theft scene needs counter != 0 - after the manor - and plays once. Reading only
    the block's own bytes says none of that, which is how it came out ordered before the
    manor it talks about.
    """
    base, data = info['base'], info['data']
    if base is None:
        return {}
    starts = sorted(info['starts']) or [0]
    out = {}
    for at, op, vals in sorted(info['insns']):
        if op != 0xb0 or not vals:
            continue
        target = vals[0][2] - base
        if not 0 <= target < len(data):
            continue
        # the condition belongs to the *block* the call lands in, which is the unit the
        # dump groups by - the entry it jumps to is often a few bytes inside one
        target = max([t for t in starts if t <= target], default=target)
        cond = out.setdefault(target, {'stage': None, 'first_time': False})
        block_end = next((s for s in starts if s > at), len(data))
        for a2, op2, v2 in info['insns']:
            if op2 in STAGE_JUMPS and len(v2) >= 3:
                var, value, jump = v2[0][2], v2[1][2], v2[2][2] - base
                if a2 < at < jump:
                    floor = _stage_floor(STAGE_JUMPS[op2], value, True)
                elif jump <= at < block_end and a2 < at:
                    floor = _stage_floor(STAGE_JUMPS[op2], value, False)
                else:
                    continue
                if floor is not None and (cond['stage'] is None or floor > cond['stage'][1]):
                    cond['stage'] = (var, floor)
            elif op2 in (TEST_CLEAR, TEST_SET) and len(v2) >= 2:
                flag, jump = v2[0][2], v2[1][2] - base
                if a2 < at < jump and op2 == TEST_CLEAR and \
                        any(f == flag and a2 < s < jump for s, f in info['sets']):
                    cond['first_time'] = True
    return out

def read_file(filename, rows):
    """Everything one script's annotation needs, read once.

    -> dict(data, base, starts, insns, gates, sets, code, not_text, groups, scenes)
    or None when the file is not on disk.
    """
    path = os.path.join(ORIG, filename)
    if not os.path.exists(path):
        return None
    data = open(path, 'rb').read()
    base, entries = slot_base(data)
    starts = block_starts(data, base, entries) if base is not None else []
    said = strings(data)
    try:
        r = sd.analyse(filename)
        insns = r['insns'] if r and not r.get('guessed_base') else []
    except Exception:
        insns = []
    groups = conversations(rows, LOOSE_GAP, starts)
    stem = filename.rsplit('.', 1)[0]
    info = {
        'data': data, 'base': base, 'entries': entries, 'starts': starts,
        'insns': insns,
        'gates': flag_gates(insns, base) if base is not None else [],
        'sets': flags_set(insns),
        'code': sd.code_bytes(filename),
        # A file with no print instruction at all displays nothing: 31END.SCN is the
        # ending sequence, x86 code rather than script, and the four "strings" the dumper
        # found in it are stray bytes (`ab ab ab ab`, and one inside a `call`).
        'not_text': not any(any(a - 4 <= o <= b for a, b in said) for o in rows),
        'groups': groups,
        'scenes': ['%s #%d' % (stem, i + 1) for i in range(len(groups))],
    }
    info['conditions'] = block_conditions(info)
    return info


RAW_SET = re.compile(rb'\x1d(..)', re.S)


def flag_index(files):
    """-> {flag: [scene name, ...]} - which scene sets each flag, over the whole game.

    A `1d <flag>` belongs to the conversation it sits in or follows, so the scene with the
    largest start at or before it. That is what turns "flag 0x73 set" into the name of a
    scene the translator can go and read.

    The decoder only sees code it can walk into, and 71 of the 206 flags the game tests
    have no decoded setter - yet 68 of those do appear as the bytes `1d <flag>` somewhere.
    So after the decoded pass, a raw byte search fills in the rest, but only for a flag
    that is actually tested and has no decoded setter, which keeps the false positives
    a byte pattern would otherwise invite out of it.
    """
    out = collections.defaultdict(list)
    wanted = set()

    def scene_at(fn, info, at):
        starts = [g[0] for g in info['groups']]
        i = bisect.bisect_right(starts, at) - 1
        return info['scenes'][max(i, 0)] if info['scenes'] else fn.rsplit('.', 1)[0]

    for fn, info in sorted(files.items()):
        for at, flag in sorted(info['sets']):
            name = scene_at(fn, info, at)
            if name not in out[flag]:
                out[flag].append(name)
        for _at, flag, _needs, _until in info['gates']:
            wanted.add(flag)
    for fn, info in sorted(files.items()):
        for m in RAW_SET.finditer(info['data']):
            flag = int.from_bytes(m.group(1), 'little')
            if flag in out or flag not in wanted:
                continue
            name = scene_at(fn, info, m.start())
            if name not in out[flag]:
                out[flag].append(name)
    return out


ORDINALS = ['0th', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th', '10th',
            '11th', '12th']


def visit_of(scripts):
    """-> {script: (n, total)} - which of an area's visits a script belongs to.

    An area's hub switches on its own stage counter (var 0x82 + the area number - see
    docs/engine_notes.md) and loads a different set of scene scripts for each value: the
    capital's 42 scripts are six visits, the castle's 28 are eight. The scenes those
    stage scripts load in turn belong to the same visit.
    """
    import story_order as so
    out, by_stage = {}, {}
    for hub, data in scripts.items():
        if not re.fullmatch(r'\d\d[A-Z]+', hub):
            continue
        var = so.stage_var(hub)
        stages = collections.defaultdict(set)
        for v, val, child in so.hub_cases(data):
            if v == var:
                stages[val].add(child)
        # Consecutive stage values that load the same scripts are one visit, not several:
        # the capital's counter runs 0..11 but stages 6-11 all load 06BLK07, so it is six
        # visits, not twelve. Counting the raw values said "visit 4 of 12" for what the
        # player experiences as the fourth of six.
        merged, seen = {}, {}
        for val in sorted(stages):
            key = frozenset(stages[val])
            if key not in seen:
                seen[key] = len(seen) + 1
            merged.setdefault(seen[key], set()).update(stages[val])
        stages = merged
        if len(stages) < 2:
            continue
        for n, val in enumerate(sorted(stages), 1):
            by_stage[(var, n - 1)] = (n, len(stages))      # stage value -> which visit
            for child in stages[val]:
                # loaded on several visits, a script is labelled by the first; a block of
                # it that only plays later is relabelled by its gate (context_for)
                out.setdefault(child, (n, len(stages)))
                for m in so.LOAD.finditer(scripts.get(child, b'')):
                    kid = m.group(1).decode().upper()
                    if kid != child and kid not in out:
                        out[kid] = (n, len(stages))
    return out, by_stage


_NPCS = {}


def npcs_by_block():
    """{script: {block offset: npc}} - who stands where, from tools/npcs.py.

    The scene scripts are dialogue only; the NPCs are objects the *stage* script builds,
    each with a sprite, a place on the map and a pointer to the block it speaks. That
    pointer is what attaches a face to a conversation the game never names.
    """
    if not _NPCS:
        try:
            with open(os.path.join(HERE, 'docs', 'npcs.json'), encoding='utf-8') as fh:
                import json
                _NPCS.update({k: {int(b): v for b, v in d.items()}
                              for k, d in json.load(fh).items()})
        except OSError:
            _NPCS['__missing__'] = {}
    return _NPCS


def npc_name(npc, area):
    """What to call an NPC the game never names: the name given to its sprite, or the
    sprite number - plus where it stands, which is what tells two of them apart."""
    if not npc or npc.get('unplaced'):        # no sprite of its own to name or to point at
        return ''
    import npcs as npcs_mod
    named = npcs_mod.name_of(npc, area)
    where = '@%d,%d' % (npc.get('x', 0) // npcs_mod.TILE, npc.get('y', 0) // npcs_mod.TILE)
    if named:
        return '%s %s' % (named, where)
    return 'sprite %s %s' % (npc.get('sprite'), where)


def speaker_note(comment):
    """A speaker's name out of the translator's own note in column G, or ''.

    The column holds three different things - a name ("Innkeep", "Girl with dog"), a note
    ("Missing a pointer to this one"), and sometimes a draft of the line itself, with
    "Name | the line" for both at once. Only the short, unpunctuated left-hand part is a
    name, so everything else is left alone.
    """
    if not comment:
        return ''
    s = str(comment).split('|')[0].strip()
    s = re.sub(r'^NEW SCENE\s*(\([^)]*\))?\s*', '', s).strip()
    if not s or len(s) > 28 or s[0] in '("　' or s[-1] in '.!?"…':
        return ''
    return s


def scene_plates(info, rows, english, names):
    """-> [[(offset, name), ...]] - the game's own name plates, per scene.

    A plate is preferred in the translator's own English, then the glossary, then the raw
    Japanese, so "Innes" reads as "Innes" once she has been named once.
    """
    out = []
    for group in info['groups']:
        here = []
        for n, off in enumerate(group, 1):
            jp = rows[off] or ''
            nxt = rows.get(group[n], '') if n < len(group) else ''
            is_code = info['not_text'] or any(
                x in info['code'] for x in range(off, off + len(jp.encode('cp932', 'replace'))))
            if not is_code and looks_like_name(jp, names, nxt):
                bare = jp.strip().strip('　')
                here.append((off, (english.get(off) or '').strip() or names.get(bare) or bare))
        out.append(here)
    return out


def context_for(filename, rows, english, comments, info, areas, names, sets_flag, visits,
                visit_at_stage=None):
    """-> {offset: [Area, Scene, Who, Shown when]}"""
    data, base = info['data'], info['base']
    area = area_for(filename, areas)
    visit = visits.get(filename.rsplit('.', 1)[0])
    plates_in = scene_plates(info, rows, english, names)
    # One script block is one interaction - talking to an NPC once - and a long speech runs
    # over several text boxes inside it. So a name plate holds for the rest of its block,
    # across scenes, and nothing is borrowed across a block boundary: the capital mayor's
    # plate in 06BLK04J #3 covers #4-#9, while the manor's unnamed Chancellor (03YSK01B
    # #4-#5, its own block) stays unnamed rather than inheriting the town chief two scenes
    # further on. Guessing across blocks was tried first and was wrong in both of those.
    bounds = list(zip(info['starts'], info['starts'][1:] + [len(data)])) or [(0, len(data))]
    block_of, plates_by_block, note_by_block = {}, collections.defaultdict(list), {}
    for si, scene_rows in enumerate(info['groups']):
        lo = scene_rows[0]
        b = next((s for s, e in bounds if s <= lo < e), lo)
        block_of[si] = b
        plates_by_block[b].extend(plates_in[si])
        if b not in note_by_block:
            note_by_block[b] = next((speaker_note(comments.get(off)) for off in scene_rows
                                     if speaker_note(comments.get(off))), '')
    by_offset = {}
    for si, scene_rows in enumerate(info['groups']):
        lo = scene_rows[0]
        scene = info['scenes'][si]
        block = next(((s, e) for s, e in bounds if s <= lo < e), (lo, scene_rows[-1] + 1))
        block_sets = sorted({f for at, f in info['sets'] if block[0] <= at < block[1]})

        # What the block that *calls* this one requires - the stage of the area's counter,
        # and whether it plays once. A scene is often gated at the call, not at the text.
        inherited = info.get('conditions', {}).get(block_of[si], {})
        scene_visit = visit
        if inherited.get('stage') and visit_at_stage:
            scene_visit = visit_at_stage.get(inherited['stage']) or visit
        plates = sorted(plates_by_block[block_of[si]])
        note = note_by_block.get(block_of[si], '')
        # the object that speaks this block, when the game builds one for it
        npc = npcs_by_block().get(filename, {}).get(block_of[si])
        cast = []
        for _off, who in plates:
            if who not in cast:
                cast.append(who)
        # The other side. Two names in one block is a scene between them; otherwise a
        # back-and-forth written as one block per speech (02OLB01A #10 Shinobu, #11 Innes,
        # #12 Shinobu ...), where the partner is the *immediately* next or previous scene's
        # plate - and only when this scene's own speaker is known.
        neighbours = []
        for step in (1, -1):
            j = si + step
            if 0 <= j < len(plates_in) and block_of.get(j) != block_of[si]:
                neighbours += [w for _o, w in plates_in[j] if w not in cast]

        for off in scene_rows:
            jp = rows[off] or ''
            jp_len = len(jp.encode('cp932', 'replace'))
            is_code = info['not_text'] or any(x in info['code'] for x in range(off, off + jp_len))
            here = [w for at, w in plates if at <= off]
            speaker = here[-1] if here else (note or npc_name(npc, filename[:5]))
            others = [w for w in cast if w != speaker] or (neighbours if speaker else [])
            who = ' -> '.join(x for x in (speaker, ' / '.join(others[:2])) if x)

            shown, links = [], []
            if scene_visit and scene_visit[1] > 1:
                shown.append('visit %d of %d' % scene_visit)
            if inherited.get('first_time'):
                shown.append('first time only')
            for at, flag, needs_set, until in info['gates']:
                if not at < off < until:
                    continue
                if not needs_set and flag in block_sets:
                    shown.append('first time only')
                else:
                    who_sets = [s for s in sets_flag.get(flag, ()) if not s.startswith(scene)]
                    where = (' or '.join(who_sets[:2]) + (', ...' if len(who_sets) > 2 else '')
                             if who_sets else 'something the scripts never name')
                    shown.append(('after ' if needs_set else 'before ') + where)
                    links += who_sets[:2]
            seen, uniq = set(), []
            for s in shown:
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
            by_offset[off] = [
                None,                   # Story order, filled for every row at the end
                area,
                scene,
                '' if is_code else who,
                NOT_TEXT if is_code else ('; '.join(uniq) or ('always' if info['insns'] else '')),
                [] if is_code else links,      # scenes the condition names, for the links
            ]
    return by_offset


PLACE_DIR = os.path.join(HERE, 'docs', 'npc_img')
SPRITE_DIR = os.path.join(HERE, 'docs', 'sprite_img')
PLACE_W, PLACE_H = 240, 180          # the crop is 320x240; this is what fits a sheet row
#   A picture sits on the row its scene starts on, in the column after the context
#   ones, and that row is grown to hold it.


def scene_of_shot(path, files):
    """Which scene a `<script>_<block>.png` from tools/sprite_shots.py belongs to.

    The picture is named after the script block the NPC's talk stub runs, and a block is
    where a conversation starts, so it is the scene whose first line sits in that block.
    """
    stem = os.path.basename(path)[:-4]
    script, _, block_hex = stem.rpartition('_')
    fn = script + '.SCN'
    info = files.get(fn)
    if not info:
        return None, None, None
    try:
        block = int(block_hex, 16)
    except ValueError:
        return None, None, None
    for si, group in enumerate(info['groups']):
        lo = group[0]
        starts = info['starts'] or [lo]
        if max([t for t in starts if t <= lo], default=lo) == block:
            return fn, info['scenes'][si], block
    #  a talk stub of a script that builds its own people (the manor, the rest house)
    #  points into the code just before the scene's first line, at no entry-table
    #  start: the scene is the one whose first row comes next, if no other scene's
    #  rows lie in between
    after = [(group[0], si) for si, group in enumerate(info['groups']) if group[0] >= block]
    if after:
        lo, si = min(after)
        prev_rows = [o for g in info['groups'] for o in g if block <= o < lo]
        if not prev_rows and lo - block < 0x100:
            return fn, info['scenes'][si], block
    return None, None, None


def inline_places(ws, files, scene_row, col):
    """Put each scene's photograph on the scene's own first row.

    The picture goes in the first empty column past the context ones, anchored to the row
    the scene starts on, and that row is made tall enough to hold it - which keeps the
    pictures from overlapping each other where two short scenes follow one another, and
    marks the start of a scene as clearly as the rule above it does.
    """
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.utils import get_column_letter
    letter = get_column_letter(col)
    ws.cell(1, col).value = 'Where it happens'
    ws.column_dimensions[letter].width = PLACE_W // 7
    done = 0
    for path in sorted(glob.glob(os.path.join(PLACE_DIR, '*.png'))):
        _fn, scene, _block = scene_of_shot(path, files)
        row = scene_row.get(scene)
        if not row:
            continue
        pic = XLImage(path)
        pic.width, pic.height = PLACE_W, PLACE_H
        ws.add_image(pic, '%s%d' % (letter, row))
        ws.row_dimensions[row].height = PLACE_H * 0.75      # points, not pixels
        done += 1
    return done


def note_scene(ws, refs, scene_row, rows_by_file, en_by_file, cells_by_file):
    """Link each "after/before <scene>" to that scene, and show it on hover.

    Two things, because neither survives everywhere: the cell gets a hyperlink to the
    scene's first row (Excel follows it; Google Sheets keeps it on import), and a note
    holding that scene's first lines - Japanese, plus the English if it has been written -
    which Sheets shows as a comment. The note is the one that always works.
    """
    from openpyxl.comments import Comment
    from openpyxl.styles import Font
    from openpyxl.worksheet.hyperlink import Hyperlink
    col = LAYOUT.index('Shown when') + 1
    scene_col = LAYOUT.index('Scene') + 1
    rows_of_scene = collections.defaultdict(list)
    for fn, cells in cells_by_file.items():
        for i, o in cells:
            name = ws.cell(i, scene_col).value
            if name:
                rows_of_scene[name].append((i, fn, o))
    link_font = Font(color='FF1155CC', underline='single')
    done = 0
    for i, names in refs.items():
        target = next((n for n in names if n in scene_row), None)
        if not target:
            continue
        preview = []
        for j, fn, o in sorted(rows_of_scene.get(target, []))[:4]:
            jp = (rows_by_file[fn].get(o) or '').strip()
            en = (en_by_file[fn].get(o) or '').strip()
            if jp:
                preview.append('%s%s' % (jp, '\n    %s' % en if en else ''))
        text = '%s (row %d)\n\n%s' % (target, scene_row[target], '\n'.join(preview))
        cell = ws.cell(i, col)
        cell.comment = Comment(text[:1500], 'context')
        # an internal link is `location`, not `target` - as a target Excel reads it as a
        # web address and refuses to follow it
        cell.hyperlink = Hyperlink(ref=cell.coordinate, location="SCNs!A%d" % scene_row[target],
                                   tooltip='go to %s' % target)
        cell.font = link_font
        done += 1
    return done


PICTURE_SCALE = 0.6          # the crop is 320x240 px; a hover box that size is too big


def picture_notes(ws, files, scene_row, col):
    """Hang each scene's photograph on its Who cell, as the comment's background.

    -> [(row, column, image path, width, height)] for embed_comment_pictures, which puts
    the pictures in after the workbook is saved. A column of images was clearer but cost
    240 px of width on every row of a sheet that is mostly text; a tooltip costs nothing
    until it is wanted.
    """
    from openpyxl.comments import Comment
    from PIL import Image
    out = []
    for path in sorted(glob.glob(os.path.join(PLACE_DIR, '*.png'))):
        _fn, scene, _block = scene_of_shot(path, files)
        row = scene_row.get(scene)
        if not row:
            continue
        cell = ws.cell(row, col)
        cell.comment = Comment('%s - where this happens' % scene, 'context')
        with Image.open(path) as img:
            w, h = img.width, img.height
        out.append((row, col, path,
                    int(w * 0.75 * PICTURE_SCALE), int(h * 0.75 * PICTURE_SCALE) + 14))
    return out


def embed_comment_pictures(path, items):
    """Put an image behind each listed comment, in the saved .xlsx.

    A comment's shape is a VML drawing, and a picture in one is a `<v:fill type="frame">`
    pointing at an image part - the same thing Excel writes for "Insert picture in
    comment". openpyxl has no API for it, so this is done to the saved file: the image
    parts are added to the zip, a rels file is written beside the VML, and each shape's
    fill is rewritten. Checked by opening the result in Excel itself, which reports the
    shape's fill as a picture and does not offer to repair the file.
    """
    import re
    import shutil
    import zipfile
    if not items:
        return 0
    zin = zipfile.ZipFile(path)
    parts = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    vml_name = next((n for n in parts if n.endswith('.vml')), None)
    if not vml_name:
        return 0
    vml = parts[vml_name].decode('utf-8')
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships">']
    want = {(row - 1, col - 1): (img, w, h) for row, col, img, w, h in items}
    chunks, n = re.split(r'(?=<[A-Za-z0-9]+:shape )', vml), 0
    for i, chunk in enumerate(chunks):
        at_row = re.search(r'<[A-Za-z0-9]+:Row>(\d+)</[A-Za-z0-9]+:Row>', chunk)
        at_col = re.search(r'<[A-Za-z0-9]+:Column>(\d+)</[A-Za-z0-9]+:Column>', chunk)
        if not (at_row and at_col):
            continue
        key = (int(at_row.group(1)), int(at_col.group(1)))
        if key not in want:
            continue
        img, w, h = want[key]
        n += 1
        name = 'comment_picture%d.png' % n
        parts['xl/media/' + name] = open(img, 'rb').read()
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships/image" Target="../media/%s"/>'
                    % (n, name))
        chunk = re.sub(r'<[A-Za-z0-9]+:fill[^>]*/>',
                       '<ns1:fill ns0:relid="rId%d" ns0:title="" recolor="t" rotate="t" '
                       'type="frame"/>' % n, chunk, count=1)
        chunk = re.sub(r'width:\d+px;height:\d+px', 'width:%dpt;height:%dpt' % (w, h),
                       chunk, count=1)
        chunks[i] = chunk
    if not n:
        return 0
    parts[vml_name] = ''.join(chunks).encode('utf-8')
    rels.append('</Relationships>')
    parts['xl/drawings/_rels/%s.rels' % os.path.basename(vml_name)] = \
        '\n'.join(rels).encode('utf-8')
    types = parts['[Content_Types].xml'].decode('utf-8')
    if 'Extension="png"' not in types:
        types = types.replace('>', '><Default Extension="png" ContentType="image/png"/>', 1)
        parts['[Content_Types].xml'] = types.encode('utf-8')
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    shutil.move(tmp, path)
    return n


def band(ws, rows, cols):
    """Shade each scene, alternating white and pale blue - nothing else.

    **Only fills, never borders.** Excel carries a cell's fill with it when the sheet is
    sorted, but leaves borders behind on the old rows - so a rule drawn at a scene start
    ends up in the middle of some unrelated conversation the moment the translator sorts by
    Story order, which is the one thing they do with this sheet. That is what "the lines are
    in weird places" was: the data and the shading were right and the rules had stayed put.

    The columns the translator owns (A-G) keep their own fills - green for a line that is
    done, red for one that needs work - so only the context columns are shaded. The rules
    span the whole row, which is what makes a conversation read as one block: a thick one
    where a conversation starts, and - only with --turn-rules - a hairline where the other
    person starts talking. That hairline is off by default: the Who column already says who
    is speaking on every row, so it mostly restated that while making a conversation look
    chopped up.
    """
    from openpyxl.styles import PatternFill
    shades = (PatternFill(fill_type=None), PatternFill('solid', start_color='FFE8ECF3'))
    code_fill = PatternFill('solid', start_color='FFFCE4E4')
    shade, prev_scene = 0, None
    for i, scene, _turn, is_code in rows:
        if scene != prev_scene:
            shade ^= 1               # the change of colour *is* the boundary
            prev_scene = scene
        fill = code_fill if is_code else shades[shade]
        for c in cols:
            ws.cell(i, c).fill = fill


def causal_pass(order, files, label_of):
    """Move every scene below whatever it depends on; the order is otherwise untouched.

    The keys above (rank, place, step) are heuristics, each read off one kind of
    evidence, and where two disagree a scene can land above the one that unlocks it -
    a stage script's arrival text after the scenes of the visit it starts, a milestone
    whose file has no block table left out of the network. The rule the sheet has to
    keep is simpler than any of the keys: **no conversation above anything it depends
    on**. `story_order.dependencies` lists those needs per script, block and entry
    point, and `story_order.causal_order` is a topological sort that breaks ties by the
    order given, so only a scene that sits above a need moves, and only as far as just
    below it. A need whose satisfier has no text of its own cannot be placed and is left
    alone; tools/check_story_order.py reports those as unverifiable.

    `order` is the sorted row list (rank, place, file, step, offset, source row); the
    unit is a scene, which sorts as one piece. -> (order, [(scene, what it waited for,
    scenes moved down by)], [scene in a cycle])
    """
    import story_order
    deps = story_order.dependencies()
    entries = collections.defaultdict(list)
    for (sfn, entry) in story_order.all_conditions():
        entries[sfn[:-4]].append(entry)
    for v in entries.values():
        v.sort()
    scene_of = {}
    for fn, info in files.items():
        for si, group in enumerate(info['groups']):
            for o in group:
                scene_of[(fn, o)] = si

    units, rows_of, unit_of = [], [], {}       # unit -> (fn, scene); unit -> rows; row -> unit
    for k, row in enumerate(order):
        fn, o = row[2], row[4]
        uid = (fn, scene_of.get((fn, o), ('row', o)))
        if not units or units[-1] != uid:
            units.append(uid)
            rows_of.append([])
        rows_of[-1].append(k)
        unit_of[k] = len(units) - 1
    by_block, by_script, last_of = {}, {}, {}    # the first unit that holds a satisfier
    for k, row in enumerate(order):
        fn, o = row[2], row[4]
        name = fn[:-4]
        starts = files[fn]['starts'] if fn in files else []
        block = max([s for s in starts if s <= o], default=None)
        by_block.setdefault((name, block), unit_of[k])
        by_script.setdefault(name, unit_of[k])
        last_of[name] = unit_of[k]

    stand_in = story_order.stand_ins()

    def satisfier(name, block):
        if block is not None and (name, block) in by_block:
            return by_block[(name, block)]
        if name in by_script:
            # the write is somewhere in the script (no block table: 25TOU00C): after
            # the whole of it, or what it unlocks lands between its own scenes
            return last_of[name] if block is None else by_script[name]
        # no text of its own: the first scene it (or its stage case) loads stands for it,
        # failing that the hub that loads it
        for group in (stand_in.get((name, block), stand_in.get(name, ())),
                      stand_in.get(('loader', name), ())):
            kids = [by_script[k] for k in group if k in by_script]
            if kids:
                return min(kids)
        return None

    needs, why = collections.defaultdict(list), collections.defaultdict(dict)
    for u, rows in enumerate(rows_of):
        for k in rows:
            fn, o = order[k][2], order[k][4]
            name = fn[:-4]
            starts = files[fn]['starts'] if fn in files else []
            block = max([s for s in starts if s <= o], default=None)
            ents = entries.get(name, ())
            i = bisect.bisect_right(ents, o) - 1
            entry = ents[i] if i >= 0 and (block is None or ents[i] >= block) else None
            for key in (('script', name), ('block', name, block), ('entry', name, entry)):
                for kind, label, alts in deps.get(key, ()):
                    where = [satisfier(n, b) for n, b in alts]
                    if None in where or u in where:
                        continue      # unverifiable (a satisfier with no text), or met by itself
                    alt = set(where)
                    if alt not in needs[u]:
                        needs[u].append(alt)
                        for w in alt:
                            why[u].setdefault(w, describe(kind, label))
    name = lambda u: label_of(order[rows_of[u][0]][2], order[rows_of[u][0]][4]) or '%s @%#x' % units[u]
    # What the scripts leave open, a player's knowledge settles: tools/play_order.json
    # lists scenes in the order they are likely met, as soft needs on top of the hard
    # ones. Sorted with the hard needs alone first, so an entry that contradicts one
    # (a cycle only the soft edges create) is dropped and named, never applied.
    def consistent(need):
        """Can every unit be emitted? (The fixpoint causal_order uses for cycles.)"""
        possible = set(range(len(units))) - set(need)
        while True:
            more = {u for u, alts in need.items() if u not in possible
                    and all(alt & possible for alt in alts)}
            if not more:
                return len(possible) == len(units)
            possible |= more

    by_label = {}
    for u in range(len(units)):
        by_label.setdefault(name(u), u)
    hard = {u: [set(a) for a in alts] for u, alts in needs.items()}
    if not consistent(hard):
        hard_cycles = set(story_order.causal_order(list(range(len(units))), dict(needs))[2])
    else:
        hard_cycles = set()
    #  One soft edge at a time, kept only while every unit can still be emitted: a
    #  single contradiction used to make everything downstream of it "impossible" and
    #  drop nearly every edge with it.
    soft, unknown, conflicts = [], [], []
    def add_soft(a, b):
        if a == b or {a} in needs[b]:
            return
        needs[b].append({a})
        if consistent({u: [set(x) for x in alts] for u, alts in needs.items()}):
            why[b].setdefault(a, 'the play order (tools/play_order.json)')
            soft.append((a, b))
        else:
            needs[b].pop()
            conflicts.append((a, b))

    for seq in play_order_sequences(by_label):
        groups = []
        for item in seq:
            labs = item if isinstance(item, list) else [item]
            unknown += [lab for lab in labs if lab not in by_label]
            g = [by_label[lab] for lab in labs if lab in by_label]
            if g:
                groups.append(g)
        #  a group (a whole script) after the group before it, with no order imposed
        #  inside either: everything in the later group follows the earlier group's
        #  last scene, and the later group's first scene follows all of the earlier
        for g1, g2 in zip(groups, groups[1:]):
            last1, first2 = max(g1), min(g2)
            for b in g2:
                add_soft(last1, b)
            for a in g1:
                add_soft(a, first2)
    ordered, moved, cycles = story_order.causal_order(list(range(len(units))), dict(needs))
    out = [order[k] for u in ordered for k in rows_of[u]]
    if unknown:
        print('play order names %d scene(s) the sheet does not have: %s'
              % (len(unknown), ', '.join(sorted(set(unknown))[:8])))
    if conflicts:
        print('%d play-order edges contradict a causal need and were dropped: %s'
              % (len(conflicts), ', '.join('%s > %s' % (name(a), name(b)) for a, b in conflicts[:6])))
    if soft:
        print('%d play-order edges applied from tools/play_order.json' % len(soft))
    return (out, [(name(u), name(behind), by, why[u].get(behind, '')) for u, behind, by in moved],
            [name(u) for u in cycles])


PLAY_ORDER = os.path.join(HERE, 'tools', 'play_order.json')


def play_order_sequences(labels):
    """-> [[scene label, ...], ...] from tools/play_order.json, ranges expanded.

    '03YSK01A #9-#19' is every scene of that script from 9 to 19 that the sheet has,
    in numeric order; a bare script name is all of its scenes.
    """
    import json
    if not os.path.exists(PLAY_ORDER):
        return []
    spec = json.load(open(PLAY_ORDER, encoding='utf-8'))
    #  `labels` come in the sheet's current order, and a range or a bare script name
    #  keeps that order (it already respects the scripts' own gates and steps) rather
    #  than numeric scene order
    by_script = collections.defaultdict(list)
    for lab in labels:
        m = re.match(r'(\S+) #(\d+)$', lab or '')
        if m:
            by_script[m.group(1)].append(int(m.group(2)))
    #  A range and a bare script name are one *group*: a list inside the sequence,
    #  which the pass orders as a whole after the item before it and before the item
    #  after, without imposing any order among its own scenes.
    out = []
    for entry in spec.get('sequences', ()):
        seq = []
        for item in entry.get('scenes', ()):
            m = re.match(r'(\S+) #(\d+)-#(\d+)$', item)
            if m:
                lo, hi = int(m.group(2)), int(m.group(3))
                seq.append(['%s #%d' % (m.group(1), n) for n in by_script.get(m.group(1), ())
                            if lo <= n <= hi])
            elif ' #' not in item:
                seq.append(['%s #%d' % (item, n) for n in by_script.get(item, ())])
            else:
                seq.append(item)
        out.append(seq)
    return out


def describe(kind, label):
    """A dependency, in the words of tools/check_story_order.py."""
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
    ap.add_argument('--out', help='write here instead of in place')
    ap.add_argument('--files', nargs='*', help='only these scripts')
    ap.add_argument('--basis', help='write the story-order basis of every script here '
                                    '(it is debug detail, not a column in the workbook)')
    ap.add_argument('--no-format', action='store_true', help='skip the scene shading')
    ap.add_argument('--turn-rules', action='store_true',
                    help='also rule a hairline where the other person starts talking')
    ap.add_argument('--show-moves', type=int, default=8,
                    help='how many of the scenes the causal pass moved to list')
    args = ap.parse_args()

    import openpyxl
    from openpyxl.utils import get_column_letter
    from rominfo import DUMP_XLS_PATH
    wb = openpyxl.load_workbook(DUMP_XLS_PATH)
    areas, names = glossary(wb)
    print('%d areas, %d character names in the glossary' % (len(areas), len(names)))

    ws = wb['SCNs']
    # by header, not by position: this tool has to read its own output, which is laid out
    # for reading rather than for the dumper (see LAYOUT)
    from rominfo import sheet_columns
    col = sheet_columns(ws)
    FN, OFF = col.get('Filename', 0) + 1, col.get('Offset', 1) + 1
    JP, EN = col.get('Japanese', 2) + 1, col.get('English', 4) + 1
    NOTE = col.get('Comments', 6) + 1
    rows_by_file = collections.defaultdict(dict)
    en_by_file = collections.defaultdict(dict)
    note_by_file = collections.defaultdict(dict)
    cells_by_file = collections.defaultdict(list)
    for i in range(2, ws.max_row + 1):
        fn, off, jp = ws.cell(i, FN).value, ws.cell(i, OFF).value, ws.cell(i, JP).value
        if not fn or off is None:
            continue
        try:
            o = int(str(off), 16)
        except ValueError:
            continue
        rows_by_file[fn][o] = jp if isinstance(jp, str) else ''
        en_by_file[fn][o] = ws.cell(i, EN).value if isinstance(ws.cell(i, EN).value, str) else ''
        note_by_file[fn][o] = ws.cell(i, NOTE).value
        cells_by_file[fn].append((i, o))

    # Read every script first: a flag is named by the scene that sets it, which can be in
    # any file, so the index has to be complete even when --files narrows the output.
    files = {}
    for fn in sorted(rows_by_file):
        info = read_file(fn, rows_by_file[fn])
        if info:
            files[fn] = info
    sets_flag = flag_index(files)
    import story_order
    visits, visit_at_stage = visit_of(story_order._scripts())
    print('%d scripts read, %d flags traced to the scene that sets them, %d scripts '
          'belong to a numbered visit' % (len(files), len(sets_flag), len(visits)))

    wanted = set(args.files) if args.files else set(rows_by_file)

    # Everything the context columns will say, keyed by (file, offset).
    ctx_of, refs_of, filled, count = {}, {}, 0, 0
    for fn in sorted(wanted):
        if fn not in files:
            continue
        ctx = context_for(fn, rows_by_file[fn], en_by_file[fn], note_by_file[fn],
                          files[fn], areas, names, sets_flag, visits, visit_at_stage)
        if not ctx:
            continue
        count += 1
        for off, vals in ctx.items():
            ctx_of[(fn, off)] = vals
            if vals[-1]:
                refs_of[(fn, off)] = vals[-1]
            filled += 1

    # Reading order: the story order becomes the row order, so the row number *is* the
    # position in the game and there is nothing to sort. Rows keep their file's own order
    # within a script, which is offset order, so a conversation stays in one piece.
    places = story_order.script_places()
    # Every row is placed by what has to be true before the block it sits in can run -
    # the gate on whatever *calls* that block, followed across files
    # (story_order.block_places). A script the game loads at two points in the story, like
    # 02OLB01, is split by it: the first meeting stays before the manor and the scene where
    # Innes admits the theft moves after it.
    #  Two keys, in this order. The **rank** is which of the story's eleven moments the
    #  scene belongs to, read off the counter chains that cross areas
    #  (story_order.story_rank); the **place** is where it sits inside that moment, which
    #  is the area-by-area order and is good at exactly that. Sorting by place alone put
    #  every one of a town's five visits together, because the place is built area first.
    #  Inside one file, a scene's place in the file is not its place in the sequence: a
    #  script that covers a whole visit tracks where the player is with a counter of its
    #  own, and 03YSK01A's *first* block is the one for coming back after being teleported
    #  out at the end of it. `block_steps` reads that counter, so rows sort by the step
    #  they need before they sort by where they sit in the file.
    story_order.block_places()
    #  Rank, place and step are all read per *block*, and a scene can straddle two blocks
    #  where a file's blocks cannot be decoded and the scene had to be grouped by gaps
    #  instead. Whatever the key says, the scene sorts as one piece: every line of it takes
    #  the earliest key any of its lines has. Without that one scene came out in two halves
    #  at opposite ends of the sheet.
    steps, stepped = {}, 0
    for fn in cells_by_file:
        if not fn.endswith('.SCN'):
            continue
        _var, got = story_order.block_steps(fn[:-4])
        if got and any(got.values()):
            steps[fn] = got
            stepped += 1
    order, moved = [], 0
    for fn, cells in cells_by_file.items():
        place = places.get(fn[:-4], (float('inf'), 'unplaced'))[0] if fn.endswith('.SCN') \
            else float('inf')
        starts = sorted(files[fn]['starts']) if fn in files else []
        scene_of, keys = {}, {}
        for si, group in enumerate(files[fn]['groups'] if fn in files else []):
            for o in group:
                scene_of[o] = si
        for i, o in cells:
            block = max([t for t in starts if t <= o], default=None)
            at = story_order.place_of(fn, o, block, places)
            if at > place:
                moved += 1
                place_here = at
            else:
                place_here = place
            key = (story_order.rank_of(fn, block), place_here,
                   steps.get(fn, {}).get(block, 0))
            si = scene_of.get(o, ('row', o))
            keys[si] = min(keys[si], key) if si in keys else key
        for i, o in cells:
            rank, place_here, step = keys[scene_of.get(o, ('row', o))]
            order.append((rank, place_here, fn, step, o, i))
    order.sort()
    #  Then the one rule that is not a heuristic: nothing above what it depends on.
    label_of = lambda fn, o: (ctx_of.get((fn, o)) or [None] * 3)[2]
    order, shifted, cycles = causal_pass(order, files, label_of)
    if shifted:
        print('%d scenes moved below something they depend on, the furthest:' % len(shifted))
        for scene, behind, by, need in shifted[:args.show_moves]:
            print('    %-14s -> below %-14s (%d scenes down)  needs %s' % (scene, behind, by, need))
    if cycles:
        print('%d scenes wait on each other and stay where they were: %s'
              % (len(cycles), ', '.join(cycles[:6])))
    order = [(row[1], row[2], row[4], row[5]) for row in order]
    if moved:
        print('%d rows placed later than their script, by the gate on their block' % moved)
    if stepped:
        print('%d scripts ordered inside themselves by their own progress counter' % stepped)
    ranks = story_order.story_rank()
    print('story rank: %d moments, from %d counter chains'
          % (len({r for r, _w in ranks.values()}), len(story_order.stage_chain())))
    print('story order: %d rows, %d scripts placed by the scripts themselves, %d by area only'
          % (len(order), sum(1 for p, b in places.values() if 'unknown' not in b and 'not placed' not in b),
             sum(1 for p, b in places.values() if 'unknown' in b or 'not placed' in b)))
    if args.basis:
        #  rank first, then place: the order the rows sort in, with why for each
        with open(args.basis, 'w', encoding='utf-8') as fh:
            fh.write('rank (which moment of the story), place (where inside it), '
                     'script, how the place was found | how the rank was found\n')
            for n, (p, b) in sorted(places.items(),
                                    key=lambda kv: (ranks.get(kv[0], (0, ''))[0], kv[1][0], kv[0])):
                r, why = ranks.get(n, (0, 'unranked'))
                fh.write('%6.2f %8.3f  %-10s %s | %s\n' % (r, p, n, b, why))
        print('story-order basis -> %s' % args.basis)

    # The sheet, rebuilt in the order and the layout a translator reads in.
    sheet = wb.create_sheet('SCNs_')
    for c, head in enumerate(LAYOUT, 1):
        sheet.cell(1, c).value = head
    at = {}                                  # (file, offset) -> its row in the new sheet
    scene_row = {}
    gloss_rows = glossary_rows(wb)
    plate_cells = formula_cells(ws, col, gloss_rows)
    restored = []
    for n, (_place, fn, off, src) in enumerate(order, 2):
        vals = ctx_of.get((fn, off)) or [None] * 5
        jp = ws.cell(src, JP).value
        sheet.cell(n, LAYOUT.index('Area') + 1).value = vals[1]
        sheet.cell(n, LAYOUT.index('Scene') + 1).value = vals[2]
        sheet.cell(n, LAYOUT.index('Who') + 1).value = vals[3]
        sheet.cell(n, LAYOUT.index('Shown when') + 1).value = vals[4]
        sheet.cell(n, LAYOUT.index('Japanese') + 1).value = jp
        sheet.cell(n, LAYOUT.index('JP_Len') + 1).value = '=LEN(%s%d)' % (
            get_column_letter(LAYOUT.index('Japanese') + 1), n)
        english = sheet.cell(n, LAYOUT.index('English') + 1)
        english.value = ws.cell(src, EN).value
        source_en = ws.cell(src, EN)
        if source_en.fill and source_en.fill.fill_type:      # the translator's own marking
            english.fill = copy(source_en.fill)
        formula = plate_cells.get((fn, ws.cell(src, OFF).value))
        if formula:
            english.value = formula
            restored.append((fn, ws.cell(src, OFF).value))
        sheet.cell(n, LAYOUT.index('EN_Len') + 1).value = '=LEN(%s%d)' % (
            get_column_letter(LAYOUT.index('English') + 1), n)
        sheet.cell(n, LAYOUT.index('Comments') + 1).value = ws.cell(src, NOTE).value
        sheet.cell(n, LAYOUT.index('Filename') + 1).value = fn
        sheet.cell(n, LAYOUT.index('Offset') + 1).value = ws.cell(src, OFF).value
        at[(fn, off)] = n
        if vals[2]:
            scene_row.setdefault(vals[2], n)

    if restored:
        print('%d name plates read their English from %s again, by formula (%d cells)'
              % (len(restored), GLOSSARY, len(plate_cells)))

    if not args.no_format:
        shade_rows = []
        for fn in sorted(files):
            info = files[fn]
            plates = {o for scene in scene_plates(info, rows_by_file[fn], en_by_file[fn], names)
                      for o, _who in scene}
            for si, group in enumerate(info['groups']):
                for k, off in enumerate(group):
                    n = at.get((fn, off))
                    if n is None:
                        continue
                    jp = rows_by_file[fn][off] or ''
                    is_code = info['not_text'] or any(
                        x in info['code']
                        for x in range(off, off + len(jp.encode('cp932', 'replace'))))
                    turn = args.turn_rules and k > 0 and off in plates
                    shade_rows.append((n, info['scenes'][si], turn, is_code))
        shade_rows.sort()
        band(sheet, shade_rows, BAND_COLS)
        print('%d rows shaded by scene' % len(shade_rows))

    refs = {at[key]: names_of for key, names_of in refs_of.items() if key in at}
    if refs:
        linked = note_scene(sheet, refs, scene_row, rows_by_file, en_by_file, cells_by_file)
        print('%d conditions linked to the scene they name' % linked)

    pictures = picture_notes(sheet, files, scene_row, LAYOUT.index('Who') + 1)

    for head, width in WIDTHS.items():
        sheet.column_dimensions[get_column_letter(LAYOUT.index(head) + 1)].width = width
    sheet.freeze_panes = 'A2'
    del wb['SCNs']
    sheet.title = 'SCNs'
    wb.move_sheet('SCNs', offset=-(len(wb.sheetnames) - 1))
    out = args.out or DUMP_XLS_PATH
    wb.save(out)
    if pictures:
        print('%d scenes show a picture of where they happen, on the Who cell'
              % embed_comment_pictures(out, pictures))
    print('%d rows annotated across %d script(s) -> %s' % (filled, count, out))


if __name__ == '__main__':
    main()
