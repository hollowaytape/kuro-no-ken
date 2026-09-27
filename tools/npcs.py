"""Who is each conversation with? Read the maps' object tables.

The scene scripts are only dialogue - the NPCs themselves are built by the *stage* script
(02OLB01.SCN, 06BLK02.SCN), one run of field writes per object:

    88 00 02        field 0x00 = 2      kind: 2 is a person you can talk to
    88 02 04        field 0x02 = 4      sprite (an index into the map's own sprite set)
    89 04 00d2      field 0x04 = 210    x, in pixels - tile 13
    89 06 00e2      field 0x06 = 226    y                  14
    88 0d 20
    89 1c 00c4 ...  the box it stands in
    89 2a 1a67      field 0x2a          -> its talk script

`89 2a` is the one field that holds an address (script_decode.OBJECT_SCRIPT_FIELDS), and
what it points at is a two-instruction stub:

    b0 00 00 3d     run the block at 0x3d00
    09 63 1a        then back to the next object

0x3d00 is the slot a *scene* script is loaded into, and a scene script begins with a table
of 3-byte jumps, so `(addr - 0x3d00) / 3` is its entry number - which is the conversation.
That is the whole chain: object -> talk stub -> entry -> the scene, and with it every line
of dialogue gets a speaker with a sprite and a place on the map, including the ones the
game never names.

Which scene script is in the slot is the one loose end. A stage script for a town swaps
them as the player moves between sub-maps (`04 <block>` -> `39 00 00 3d 02 "06blk02c"`),
so an object is matched to the scene script of the most recent such call before it - and
checked against that file's entry count, which is what the --check pass reports.

    python tools/npcs.py                    # write docs/npcs.json
    python tools/npcs.py --check            # how many entries resolve, and how well
    python tools/npcs.py --report 02OLB     # every NPC of an area, with their first line
    python tools/npcs.py --sprites          # the sprite table to name, with sample lines
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

import script_decode as sd                                     # noqa: E402
from script_map import slot_base, block_starts, strings        # noqa: E402

ORIG = os.path.join(HERE, 'original', 'decompressed')
OUT = os.path.join(HERE, 'docs', 'npcs.json')
NAMES = os.path.join(HERE, 'tools', 'npc_names.json')
LOAD = re.compile(rb'\x39\x00\x00([\x00\x18\x3d])\x02([0-9a-z]{3,10})\x00')
SCENE_SLOT = 0x3d00
# An object's x/y are in map units, and one unit is 8 screen pixels: the player object
# sits at camera + (0x28, 0x1c) and is drawn at the middle of the 640x400 screen, so
# 0x28 units = 320 px. A tile is 16 px, i.e. two units - measured in the emulator
# (states/albein_permit_arrival, r01_after_opening), not assumed.
TILE = 2

KIND = {2: 'person', 5: 'door or sign'}     # what the kinds seen so far look like


def _read(fn):
    with open(os.path.join(ORIG, fn), 'rb') as f:
        return f.read()


def load_blocks(fn, data, base):
    """{address of a block that loads a scene script: script name}.

    Each is its own little block - `39 00 00 3d 02 "06blk02o" 00 8d 07 83` - and the stage
    script calls it when the player walks into that sub-map.
    """
    out = {}
    for m in LOAD.finditer(data):
        if m.group(1)[0] << 8 != SCENE_SLOT:
            continue
        out[base + m.start()] = m.group(2).decode().upper()
    return out


_PAIRED = {}


def paired_scenes(fn):
    """Every scene script a hub loads beside this stage script.

    A town's hub loads the pair together - `39 ... 18 02 "02olb01"` then
    `39 ... 3d 02 "02olb01a"` - so the stage script itself never mentions the scene script
    it works with. Bigger towns instead swap scene scripts as the player walks between
    sub-maps, and those show up as `04 <load block>` calls inside the stage script; this is
    the fallback for the ones that do not.

    It is a *list*, because one stage script often has more than one: 02OLB01 is paired
    with 02OLB01A at one stage of the story and 02OLB01B at another. The two hold the same
    28 conversations at two moments - the same townspeople, a different exchange with
    Innes - so the objects belong to both, and attaching them only to the first (which is
    what this did at first) left every B scene with no-one standing in it.
    """
    if not _PAIRED:
        for path in sorted(glob.glob(os.path.join(ORIG, '*.SCN'))):
            data = open(path, 'rb').read()
            hits = [(m.start(), m.group(1)[0] << 8, m.group(2).decode().upper())
                    for m in LOAD.finditer(data)]
            for (at, slot, name), (at2, slot2, name2) in zip(hits, hits[1:]):
                if slot == 0x1800 and slot2 == SCENE_SLOT and at2 - at < 0x40:
                    got = _PAIRED.setdefault(name + '.SCN', [])
                    if name2 not in got:
                        got.append(name2)
    return _PAIRED.get(fn, [])


def field_runs(data, base):
    """Every run of object field writes in a file, read from the bytes.

    `88 <field> <byte>` and `89 <field> <word>` are fixed length, so a run of them parses
    without decoding the file around it - which matters, because the interpreter's own walk
    only reaches the blocks it can follow, and in the capital that left 38 of 39 objects
    unseen. A run has to end in `89 2a <address in this file>` and hold at least three
    fields to count, and runs inside a printed string are skipped, so the text cannot fake
    one.
    """
    said = strings(data)
    out, i = [], 0
    while i < len(data) - 3:
        if data[i] not in (0x88, 0x89) or any(a <= i <= b for a, b in said):
            i += 1
            continue
        start, fields = i, {}
        while i < len(data) - 3 and data[i] in (0x88, 0x89):
            field = data[i + 1]
            if data[i] == 0x88:
                fields[field] = data[i + 2]
                i += 3
            else:
                fields[field] = int.from_bytes(data[i + 2:i + 4], 'little')
                i += 4
        talk = fields.get(0x2a)
        if len(fields) >= 3 and talk is not None and base <= talk < base + len(data):
            out.append((start, i, fields))
    return out


def objects(fn):
    """[{kind, sprite, x, y, talk, at, scene}] for one stage script."""
    try:
        r = sd.analyse(fn)
    except Exception:
        r = None
    if not r or r.get('guessed_base'):
        return []
    base, data = r['base'], _read(fn)
    blocks = load_blocks(fn, data, base)
    # `04 <load block>` - where the stage script switches the scene script
    switches = sorted((at, blocks[v]) for at, op, vals in r['insns'] if op == 0x04
                      for _k, _l, v in vals if v in blocks)
    only = sorted(set(blocks.values()))
    default = only if len(only) == 1 else paired_scenes(fn)
    out = []
    for at, _end, fields in field_runs(data, base):
        before = [n for a, n in switches if a < at]
        o = dict(fields)
        #  The stub itself usually says which scene script it needs: its first
        #  instruction is `04 <load block>` - the call that swaps that script in before
        #  `b0` runs the entry (the capital: `04 9a 28` is 06BLK01B's load block; Sohagi
        #  and the pre-switch people of every town resolve this way). Only when the stub
        #  does not call a load block does the last switch before the object decide.
        stub = fields[0x2a] - base
        called = None
        if 0 <= stub < len(data) - 3 and data[stub] == 0x04:
            called = blocks.get(int.from_bytes(data[stub + 1:stub + 3], 'little'))
        o.update({'at': at, 'kind': fields.get(0x00), 'talk': fields[0x2a],
                  'scenes': [called] if called else ([before[-1]] if before else list(default))})
        out.append(o)
    return out


def step(data, at):
    """Decode one instruction from the bytes -> (opcode, [values], next offset).

    Lengths come from script_decode.LAYOUTS, so this needs no walk of the whole file -
    which is the point: the interpreter's own walk does not reach most talk stubs, and
    they are only ever two or three instructions long.
    """
    if not 0 <= at < len(data):
        return None, [], at
    op = data[at]
    layout = sd.LAYOUTS.get(op)
    if layout is None:
        return op, [], at + 1
    i, values = at + 1, []
    for kind in layout:
        if kind == 'byte':
            values.append(data[i] if i < len(data) else 0)
            i += 1
        elif kind == 'word':
            values.append(int.from_bytes(data[i:i + 2], 'little'))
            i += 2
        elif kind == 'tagged':
            tag = data[i] if i < len(data) else 2
            i += 1
            if tag < 2:
                values.append(int.from_bytes(data[i:i + 2], 'little'))
                i += 2
        elif kind == 'table':
            n = data[i] if i < len(data) else 0
            i += 1 + 3 * n
    return op, values, i


def talk_target(insns, data, base, addr):
    """What an object's talk script runs -> ('scene', entry) | ('here', offset) | None.

    The stub is a couple of instructions ending in `b0 <address>` ("run this block"), but
    what comes first varies: nothing (02OLB01), a call (`04 2790` in the castle, which
    turns the character to face the player), or a flag test (15MKR01B). And where it
    points varies too - at the scene slot 0x3d00, i.e. an entry of the scene script, or
    at a block of the stage script itself, which is where the smaller maps keep their
    dialogue. Both are followed here; only the shape of the jump differs.
    """
    at, hops = addr - base, 0
    for _n in range(8):
        op, vals, nxt = step(data, at)
        if op is None:
            return None
        if op == 0xb0 and vals:
            word = vals[0]
            if word & 0xff00 == SCENE_SLOT and not (word - SCENE_SLOT) % 3:
                return 'scene', (word - SCENE_SLOT) // 3
            if base <= word < base + len(data):
                return 'here', word - base
            return None
        if op == 0x09 and vals and hops < 2:       # a stub that is only a jump
            target = vals[0] - base
            if not 0 <= target < len(data):
                return None
            at, hops = target, hops + 1
            continue
        if op in (0x83, 0x40, 0x39):
            return None
        at = nxt
    return None


def scene_entries(fn):
    """The scene script's entry addresses, or [] when it has no entry table."""
    try:
        data = _read(fn)
    except OSError:
        return []
    base, entries = slot_base(data)
    return entries if base is not None else []


def collect():
    """-> {scene script: {entry: npc}} over every stage script in the game."""
    out = collections.defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(ORIG, '*.SCN'))):
        fn = os.path.basename(path)
        try:
            r = sd.analyse(fn)
        except Exception:
            continue
        if not r or r.get('guessed_base'):
            continue
        data, base = _read(fn), r['base']
        for o in objects(fn):
            # A run with no sprite and no position used to be dropped as "not a person"
            # (54 of them, all at (0,0)). The capital showed otherwise: 26 of its 38
            # people are built that way, the sprite coming from the slot's previous
            # occupant, and they stand and talk like anyone else. They are kept, marked
            # `unplaced`, for what needs only the talk stub -> scene link
            # (tools/npc_photos.py); the workbook's Who column leaves them out.
            target = talk_target(r['insns'], data, base, o['talk'])
            if not target:
                continue
            where, value = target
            if where == 'scene':
                holders = []
                for scene in o.get('scenes') or []:
                    entries = scene_entries(scene + '.SCN')
                    if value < len(entries):
                        holders.append((scene + '.SCN', entries[value]))
            else:
                holders = [(fn, value)]      # the dialogue is in the stage script itself
            for holder, block in holders:
                out[holder][block] = {
                    'sprite': o.get(0x02), 'x': o.get(0x04, 0), 'y': o.get(0x06, 0),
                    'kind': KIND.get(o.get('kind'), 'kind %s' % o.get('kind')),
                    'from': fn, 'block': block,
                    'unplaced': o.get(0x02) is None,
                    # the talk stub's address: the one field of a live object (RAM, +0x2a)
                    # that names this record exactly, however far the person has walked
                    'talk': o['talk'],
                }
    return out


def first_lines(fn, entry_addr, n=1):
    """The first line(s) the game prints from a scene's entry block - what the NPC says."""
    try:
        data = _read(fn)
    except OSError:
        return []
    base, entries = slot_base(data)
    if base is None:
        return []
    starts = block_starts(data, base, entries)
    said = [(a, b) for a, b in strings(data) if a >= entry_addr]
    block_end = next((s for s in sorted(starts) if s > entry_addr), len(data))
    out = []
    for a, b in said[:6]:
        if a > block_end + 0x200:
            break
        text = data[a:b + 1].decode('cp932', 'replace').strip()
        # 25TOU is one of the files the decoder cannot follow, and a "print" found in it
        # can be bytes rather than a line; skipping those keeps the naming sheet readable
        if not text or '�' in text or sd.looks_like_garbage(text):
            continue
        out.append(text)
        if len(out) >= n:
            break
    return out


def names():
    try:
        with open(NAMES, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def name_of(npc, area):
    """A sprite's name from tools/npc_names.json, if it has been given one.

    Keyed "<area> <sprite>" ("02OLB 4"), because the sprite number is an index into the
    map's own set - the same number means a different person in another town.
    """
    table = names()
    return table.get('%s %s' % (area, npc.get('sprite')), '')


HELP = ('Name each sprite here and the workbook uses it: the key is "<area> <sprite>", '
        'the sprite being an index into that map\'s own set, so the same number is a '
        'different person in another town. A name is what the player sees - "old man in '
        'green", "barmaid" - because the position (@x,y) is what tells two of them apart. '
        'docs/sprites.md lists them with a line each of them says. Run '
        '`python tools/npcs.py --names` to add any new ones without losing these.')


def write_naming_sheet(found):
    """tools/npc_names.json (keep what is named, add what is not) + docs/sprites.md."""
    rows = collections.defaultdict(list)
    for scene, blocks in found.items():
        for block, npc in blocks.items():
            rows[(scene[:5], npc['sprite'])].append((scene, block, npc))
    have = names()
    out = {'_help': HELP}
    for area, sprite in sorted(rows, key=lambda k: (k[0], k[1] if k[1] is not None else -1)):
        key = '%s %s' % (area, sprite)
        out[key] = have.get(key, '')
    with open(NAMES, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write('\n')

    md = [('# The game\'s sprites, to name\n\n'
           'Every person on a map is an object with a sprite number - an index into that\n'
           'map\'s own set, so `02OLB 4` and `06BLK 4` are different people. Put a name in\n'
           '`tools/npc_names.json` and the context workbook shows it in the **Who** column\n'
           'instead of the number, with the place they stand (`@13,14`, in tiles) after it.\n\n'
           '`count` is how many people in that area use the sprite; the line is one of\n'
           'theirs, to recognise them by.\n\n'
           '| area | sprite | count | stands at | says | picture |\n|---|---|---|---|---|---|')]
    for area, sprite in sorted(rows, key=lambda k: (k[0], k[1] if k[1] is not None else -1)):
        rs = rows[(area, sprite)]
        scene, block, npc = rs[0]
        line = (first_lines(scene, block) or [''])[0]
        line = re.sub(r'\\[a-z]\d*|[\u300c\u300d]', '', line).strip()[:38]
        where = ' '.join('%d,%d' % (n['x'] // TILE, n['y'] // TILE) for _s, _b, n in rs[:4])
        shot = 'sprite_img/%s_%s.png' % (area, sprite)
        md.append('| %s | %s | %d | %s | %s | %s |'
                  % (area, sprite, len(rs), where, line.replace('|', '/'),
                     '![](%s)' % shot if os.path.exists(os.path.join(HERE, 'docs', shot)) else ''))
    with open(os.path.join(HERE, 'docs', 'sprites.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(md) + '\n')
    write_page(rows, have)
    print('%d sprites over %d areas -> %s, docs/sprites.md and docs/sprites.html'
          % (len(rows), len({a for a, _s in rows}), NAMES))


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Sprites to name</title>
<style>
 :root {{ --bg:#fff; --fg:#1a1a1a; --dim:#666; --line:#e3e3e3; --band:#fafafa; --accent:#1155cc; }}
 @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
   --bg:#1b1b1d; --fg:#e8e8e8; --dim:#a0a0a0; --line:#333; --band:#212123; --accent:#7aa7ff; }} }}
 body {{ background:var(--bg); color:var(--fg); margin:0; padding:24px 16px 60px;
        font:15px/1.55 -apple-system,"Segoe UI",system-ui,sans-serif; }}
 main {{ max-width:1100px; margin:0 auto; }}
 h1 {{ font-size:22px; margin:0 0 10px; }}
 p.intro {{ color:var(--dim); max-width:70ch; margin:0 0 18px; }}
 code {{ background:var(--band); border:1px solid var(--line); border-radius:4px;
        padding:1px 4px; font-size:13px; }}
 .bar {{ display:flex; gap:10px; align-items:center; margin:0 0 14px; flex-wrap:wrap; }}
 input {{ font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--line);
        border-radius:6px; padding:6px 9px; }}
 input[type=search] {{ min-width:220px; }}
 button {{ font:inherit; background:var(--accent); color:#fff; border:0; border-radius:6px;
          padding:7px 13px; cursor:pointer; }}
 button.ghost {{ background:transparent; color:var(--accent); border:1px solid var(--line); }}
 table {{ border-collapse:collapse; width:100%; }}
 th, td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--line);
          vertical-align:top; }}
 th {{ position:sticky; top:0; background:var(--bg); font-size:12px; letter-spacing:.04em;
      text-transform:uppercase; color:var(--dim); cursor:pointer; user-select:none; }}
 tbody tr:nth-child(even) {{ background:var(--band); }}
 td.n, td.w {{ font-variant-numeric:tabular-nums; color:var(--dim); white-space:nowrap; }}
 td.jp {{ font-family:"Yu Gothic","Hiragino Kaku Gothic ProN","MS Gothic",sans-serif; }}
 td.pic {{ width:84px; padding:4px 6px; }}
 td.pic img {{ image-rendering:pixelated; height:76px; display:block; margin:0 auto; }}
 td input {{ width:100%; min-width:150px; }}
 .count {{ color:var(--dim); font-size:13px; }}
 @media (max-width:720px) {{ td.w {{ white-space:normal; }} body {{ padding:16px 12px 40px; }} }}
</style>
<main>
<h1>The game&#39;s sprites, to name</h1>
<p class="intro">Every person on a map is an object with a sprite number &mdash; an index into
that map&#39;s own set, so <code>02OLB 4</code> and <code>06BLK 4</code> are different people.
Name one here and the <b>Who</b> column of the workbook shows the name instead of the number,
with the tile they stand on after it. <b>count</b> is how many people in that area share the
sprite; the line is one of theirs, to recognise them by. When you are done, copy the JSON and
paste it into <code>tools/npc_names.json</code>.</p>
<div class="bar">
  <input type="search" id="q" placeholder="filter by area, sprite or line">
  <button id="copy">Copy names as JSON</button>
  <button class="ghost" id="clear">Clear filter</button>
  <span class="count" id="count"></span>
</div>
<table>
<thead><tr><th></th><th>area</th><th>sprite</th><th>count</th><th>stands at</th><th>says</th><th>name</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</main>
<script>
const q = document.getElementById('q'), rows = [...document.querySelectorAll('tbody tr')];
const count = document.getElementById('count');
function show() {{
  const t = q.value.trim().toLowerCase();
  let n = 0;
  for (const r of rows) {{
    const hit = !t || r.textContent.toLowerCase().includes(t) ||
                (r.querySelector('input').value || '').toLowerCase().includes(t);
    r.hidden = !hit; if (hit) n++;
  }}
  count.textContent = n + ' of ' + rows.length + ' sprites';
}}
q.addEventListener('input', show);
document.getElementById('clear').onclick = () => {{ q.value = ''; show(); }};
document.getElementById('copy').onclick = async () => {{
  const out = {{}};
  for (const i of document.querySelectorAll('td input')) out[i.dataset.key] = i.value || '';
  const text = JSON.stringify(out, null, 1);
  const b = document.getElementById('copy');
  try {{ await navigator.clipboard.writeText(text); b.textContent = 'Copied'; }}
  catch (e) {{ const w = window.open(); w.document.body.innerText = text; }}
  setTimeout(() => b.textContent = 'Copy names as JSON', 1500);
}};
document.querySelectorAll('th').forEach((th, i) => th.onclick = () => {{
  const dir = th.dataset.dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
  const body = document.querySelector('tbody');
  const val = r => {{ const c = r.children[i], v = c.querySelector('input');
                     return (v ? v.value : c.textContent).trim(); }};
  [...rows].sort((a, b) => {{
    const x = val(a), y = val(b), nx = parseFloat(x), ny = parseFloat(y);
    const c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : x.localeCompare(y, 'ja');
    return dir === 'asc' ? c : -c;
  }}).forEach(r => body.appendChild(r));
}});
show();
</script>
"""


def write_page(rows, have):
    """docs/sprites.html - the same table, but filterable, sortable and fillable.

    The point is the last column: type a name, press "Copy names as JSON", paste into
    tools/npc_names.json. Reading 121 sprites in a plain table and editing a JSON file
    beside it is the part that would otherwise be tedious.
    """
    import html as html_mod
    tr = []
    for area, sprite in sorted(rows, key=lambda k: (k[0], k[1] if k[1] is not None else -1)):
        rs = rows[(area, sprite)]
        scene, block, npc = rs[0]
        line = (first_lines(scene, block) or [''])[0]
        line = re.sub(r'\\[a-z]\d*|[\u300c\u300d]', '', line).strip()[:46]
        where = ' '.join('%d,%d' % (n['x'] // TILE, n['y'] // TILE) for _s, _b, n in rs[:4])
        key = '%s %s' % (area, sprite)
        e = html_mod.escape
        # The picture is inlined, not linked: the page is read from a preview pane and
        # from wherever it gets sent, and a relative path resolves in neither.
        shot = os.path.join(HERE, 'docs', 'sprite_img', '%s_%s.png' % (area, sprite))
        pic = ''
        if os.path.exists(shot):
            import base64
            with open(shot, 'rb') as fh:
                pic = ('<img src="data:image/png;base64,%s" alt="sprite %s">'
                       % (base64.b64encode(fh.read()).decode(), e(str(sprite))))
        tr.append('<tr><td class="pic">%s</td><td>%s</td><td class="n">%s</td>'
                  '<td class="n">%d</td><td class="w">%s</td><td class="jp">%s</td>'
                  '<td><input data-key="%s" value="%s" placeholder="name this sprite"></td></tr>'
                  % (pic, e(area), e(str(sprite)), len(rs), e(where), e(line), e(key),
                     e(have.get(key, ''))))
    with open(os.path.join(HERE, 'docs', 'sprites.html'), 'w', encoding='utf-8') as fh:
        fh.write(PAGE.format(rows=''.join(tr)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--report', help='an area prefix, e.g. 02OLB')
    ap.add_argument('--sprites', action='store_true')
    ap.add_argument('--names', action='store_true',
                    help='write the sprite list to name: tools/npc_names.json + docs/sprites.md')
    ap.add_argument('--out', default=OUT)
    args = ap.parse_args()

    found = collect()
    if args.names:
        write_naming_sheet(found)
        return
    if args.check:
        total = sum(len(v) for v in found.values())
        print('%d NPCs matched to a scene entry, over %d scene scripts' % (total, len(found)))
        by_stage = collections.Counter(n['from'] for v in found.values() for n in v.values())
        print('stage scripts that build them: %d' % len(by_stage))
        kinds = collections.Counter(n['kind'] for v in found.values() for n in v.values())
        print('kinds: %s' % dict(kinds))
        return
    if args.sprites:
        rows = collections.defaultdict(list)
        for scene, ents in found.items():
            for block, npc in ents.items():
                rows[(scene[:5], npc['sprite'])].append((scene, block, npc))
        print('%-7s %-7s %-5s %s' % ('area', 'sprite', 'count', 'a line one of them says'))
        for (area, sprite), rs in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1)):
            scene, block, npc = rs[0]
            line = (first_lines(scene, block) or [''])[0]
            print('%-7s %-7s %-5d %s' % (area, sprite, len(rs), line[:46]))
        return
    if args.report:
        for scene in sorted(found):
            if not scene.startswith(args.report):
                continue
            for block, npc in sorted(found[scene].items()):
                line = (first_lines(scene, block) or [''])[0]
                print('%-14s %#06x sprite %-3s tile (%2d,%2d)  %-12s %s'
                      % (scene, block, npc['sprite'], npc['x'] // TILE, npc['y'] // TILE,
                         npc['kind'], line[:40]))
        return

    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump({k: {str(e): v for e, v in sorted(d.items())} for k, d in sorted(found.items())},
                  fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    print('%d NPCs over %d scene scripts -> %s'
          % (sum(len(v) for v in found.values()), len(found), args.out))


if __name__ == '__main__':
    main()
