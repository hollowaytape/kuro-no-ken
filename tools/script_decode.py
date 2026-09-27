"""Decode a .SCN the way the game's own interpreter does, and list its real pointers.

`find_pointers`' byte patterns cannot tell an address from a number that looks like one,
which has cost this project four crashes and a soft-lock. The interpreter can: its main
loop (BD.BIN 0x33b2) dispatches through a 256-entry handler table at 0x22d0, and each
handler's `lodsb` / `lodsw` - plus a handful of shared operand readers - say exactly what
that opcode consumes.

Operands come in two shapes:

* **raw** bytes or words written straight into the instruction (a jump target),
* **tagged**, read by BD.BIN 0x17b8: a tag byte, then
  `00` an immediate word, `01` a word that is a *variable index*, `>=02` nothing.

So an address is an immediate (raw word, or tagged with tag 0) belonging to an opcode
whose operand is a script address. A variable index can never be one - that is the
distinction the regexes never had.

    python tools/script_decode.py 03YSK01B.SCN            # pointers, one per line
    python tools/script_decode.py 03YSK01B.SCN --listing  # the decoded script
    python tools/script_decode.py --check 03YSK01B.SCN    # vs what rominfo registers
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)

TABLE = 0x22d0
BD_PATH = os.path.join(HERE, 'original', 'decompressed', 'BD.BIN')
SLOT_BASES = (0x3d00, 0x1800, 0x0000)

# Operand layouts, read off each opcode's handler (tools/derive_layouts.py
# derives them; these are the ones checked by hand against the disassembly).
#   'byte' / 'word' - raw operand bytes in the instruction
#   'tagged'        - BD.BIN 0x17b8: a tag byte, then a word when the tag is 0
#                     (immediate) or 1 (a variable index), nothing when it is >= 2
#   'table'         - a count byte, then that many words: opcode 0x8b runs each of
#                     them as a block, so every entry is an address
LAYOUTS = {
    0x01: ['word'],                      # 1c36
    0x02: ['word'],                      # 1c5b -> 17c6/17cc
    0x04: ['word'],                      # 1c9d  call
    0x07: [],                            # 1cdc
    0x09: ['word'],                      # 1cee  jump
    0x0c: ['word', 'word'],              # 1d26  branch if flag <w0> SET -> <w1> (the `je` after
    0x0d: ['word', 'word'],              # 1d30  branch if flag <w0> CLEAR -> <w1>  `test` skips the jump)
    0x1d: ['word'],                      # 1dcb  set flag <w0>
    # 0x10-0x1b: compare, then branch to <w2> through 1d2d (`mov si, ax`), like 0c/0d.
    # Even opcodes compare variable <w0> with the constant <w1> (1daa), odd ones two
    # variables (1db6). 10 jumps if !=, 12 if ==, 14 <=, 16 <, 18 >, 1a >= (unsigned);
    # the odd ones likewise. `10 <stage var> <n> <next case>` is how every area hub
    # picks the scene scripts for story stage n - so until these were listed, decoding
    # stopped at the first stage check and the jump operands were never relocated.
    **{op: ['word', 'word', 'word'] for op in range(0x10, 0x1c)},
    # Variable arithmetic, read from BD.BIN 1dc3-1e8f. 17cc reads a variable index (word),
    # 17c6 a variable's value (index word), 17dd/17d7 a flag index (word). None of these
    # holds an address; they are listed so a walk continues past them - a stage advance
    # (`22 <stage var>`) used to stop it.
    0x1c: ['word'],                      # flag <w0> cleared
    0x1e: ['word', 'word'],              # flag <w0> copied from flag <w1>
    0x21: ['word', 'word'],              # var <w0> = var <w1>
    0x22: ['word'],                      # var <w0> += 1
    0x23: ['word'],                      # var <w0> -= 1
    0x24: ['word'],                      # flag <w0> toggled
    0x25: ['word'],                      # var <w0> = ~var <w0>
    0x27: ['word', 'word'],              # swap var <w0>, var <w1>
    **{op: ['word', 'word'] for op in range(0x28, 0x30)},   # +,-,&,| with a constant (even)
                                                            # or another variable (odd)
    0xb1: ['tagged'],                    # 2ab4  -> [0x93a]
    0x1f: ['word'],                      # 1de5 -> 17cc  variable index
    0x20: ['word', 'word'],              # 1ded
    0x40: ['tagged'],                    # 1f99  print; the string follows inline
    0x5a: ['tagged'],                    # 2118  int 60h service
    0x80: ['tagged', 'tagged'],          # 24d0  spawn object <t0>, script <t1>
    0x83: [],                            # 2531  end of block
    0x88: ['byte', 'byte'],              # 2569  var <b0> = byte <b1>
    0x89: ['byte', 'word'],              # 2571  var <b0> = word <w1>  (a VALUE)
    0x8b: ['tagged', 'table'],           # 2692  run each block in the table
    0x91: ['tagged', 'tagged'],          # 26cd
    0x95: ['tagged'],                    # 2753 (the word its handler reads
                                         # comes from data, not the script)
    0x9e: ['tagged', 'tagged', 'tagged', 'tagged'],  # 2837 -> 27fc: zone <t0>,
                                         # offsets <t1>,<t2>, then <t3> = the data it
                                         # reads through (an address in this file)
    0xb0: ['tagged'],                    # 2aa4  the block to run next
}

# Which operand of an opcode names a script address.
ADDRESS_OPS = {0x04: 0, 0x09: 0, 0x0c: 1, 0x0d: 1, 0x80: 1, 0xb0: 0,
               0xb1: 0, 0x9e: 3, **{op: 2 for op in range(0x10, 0x1c)}}
ADDRESS_TABLE_OPS = {0x8b}               # every entry of the table is an address

# `89 <var> <word>` writes a constant into a field of the *current object* (its handler
# resolves the index against bp). Most fields hold numbers, but +0x28 and +0x2a are the
# object's script pointers - the ones the object table shows 3 bytes apart - so a write
# to those is an address, not a value. This is the distinction that makes `89 2a <addr>`
# a pointer while `89 04 <number>` beside it is not.
OBJECT_SCRIPT_FIELDS = {0x28, 0x2a, 0x2c}


def _bd():
    with open(BD_PATH, 'rb') as f:
        return f.read()


VARIABLE_COUNT = 0x100
FLAG_COUNT = (0x951 - 0x8d2) * 8     # the flag bits end where the resource-name buffer starts

# Which operands of the opcodes added from BD.BIN name a variable (v) or a flag (f).
# (0c/0d/1d/1f/20 were listed before and are left as they were.)
OPERAND_KINDS = {0x1c: 'f', 0x1e: 'ff', 0x21: 'vv', 0x22: 'v', 0x23: 'v', 0x24: 'f',
                 0x25: 'v', 0x27: 'vv',
                 **{op: ('vv' if op & 1 else 'v') for op in range(0x28, 0x30)},
                 **{op: ('vv' if op & 1 else 'v') for op in range(0x10, 0x1c)}}


def compare_is_plausible(op, values):
    """Opcodes 10-2f name variables by index, resolved (BD.BIN 17cc) as the word at
    0x6d2 + 2*index - and the flag bit array starts at 0x8d2, so there are 0x100 of them.
    An index past that means the walk has fallen into bytes that are not script (15MKR01C
    0x365 read `10 53 5f ...` as a compare on "variable 0x5f53" and went on to decode
    overlapping nonsense). Before these opcodes were listed such a walk stopped at them;
    this keeps it stopping there. Flag operands are bounded the same way."""
    kinds = OPERAND_KINDS.get(op)
    if kinds is None:
        return True
    if len(values) < len(kinds):
        return False
    limit = {'v': VARIABLE_COUNT, 'f': FLAG_COUNT}
    return all(values[i][2] < limit[k] for i, k in enumerate(kinds))


_CODE_BYTES = {}


def code_bytes(fn):
    """Offsets the decoder proves are script instructions (opcodes and operands; a print's
    string is text, so not included). A dump row overlapping these is code the dumper read
    as Shift-JIS - 06BLK05J 0x1ad is the `94 40` jump address of `10 20 00 00 00 94 40` -
    and English written there would overwrite the instruction."""
    if fn not in _CODE_BYTES:
        out = set()
        try:
            r = analyse(fn)
        except Exception:
            r = None
        if r and not r.get('guessed_base'):
            for at, op, values in r['insns']:
                if op == 0x40:
                    continue
                out.add(at)
                for kind, vloc, _v in values:
                    out.add(vloc)
                    if kind != 'byte':
                        out.add(vloc + 1)
        _CODE_BYTES[fn] = out
    return _CODE_BYTES[fn]


_NO_TEXT = {}


def shows_no_text(fn, rows):
    """True when a file never prints: not one of its dump rows is inside a print.

    `rows` are the file's dump offsets. A print is `40 02 <string> 00`, so a row that is
    text starts just inside one (script_map.strings gives the spans). One row outside a
    span proves nothing - 05SKS04's menu choices are drawn another way and are real text -
    but a whole file outside them is 31END.SCN, which is x86 code, not script: its four
    "strings" are stray bytes, one of them `ab ab ab ab` filler.
    """
    key = (fn, tuple(sorted(rows)))
    if key not in _NO_TEXT:
        from script_map import strings
        path = os.path.join(HERE, 'original', 'decompressed', fn)
        try:
            said = strings(open(path, 'rb').read())
        except OSError:
            _NO_TEXT[key] = False            # not on disk: say nothing rather than guess
            return False
        # No print spans at all counts too: 06BLK07.SCN is a stage hub that only loads
        # other scripts, and its two "strings" are bytes of those load instructions. It is
        # the only file in the game with no print in it.
        _NO_TEXT[key] = bool(rows) and not any(
            any(a - 4 <= o <= b for a, b in said) for o in rows)
    return _NO_TEXT[key]


_TEXT_CHARS = set()


def text_chars(min_uses=3):
    """Every character the game really prints, from the `40 02 <string> 00` of every SCN.

    A character that appears three times or more in text the game prints is normal; one
    that never does is a sign the "string" is not text at all. 1600-odd characters.
    """
    if not _TEXT_CHARS:
        import collections
        from script_map import strings
        seen = collections.Counter()
        for path in glob.glob(os.path.join(HERE, 'original', 'decompressed', '*.SCN')):
            data = open(path, 'rb').read()
            for a, b in strings(data):
                seen.update(data[a:b + 1].decode('cp932', 'ignore'))
        _TEXT_CHARS.update(c for c, n in seen.items() if n >= min_uses)
    return _TEXT_CHARS


def in_a_print(fn, offset):
    """Is this offset inside one of the file's `40 02 <string> 00` prints?"""
    from script_map import strings
    try:
        said = strings(open(os.path.join(HERE, 'original', 'decompressed', fn), 'rb').read())
    except OSError:
        return True
    return any(a - 4 <= offset <= b for a, b in said)


def looks_like_garbage(jp):
    """Bytes that decoded as Japanese but are not - used only outside a print.

    Half-width katakana (the game writes its own kana another way, `85 <b>`), or a string
    with no kana at all that uses a character the game never prints. Checked against the
    67 rows in the game that sit outside every print: it takes all 39 of the mojibake
    (`ｨ尺ｹ`, `膿θ`, `看鐇`, `ﾀ諧諧諧諧`) and leaves all 28 real ones - the menu choices
    (`賄賂を渡す`, `サクッと斬る`), the `５つ`/`６つ` counters, 99CMN's `ＹＥＳ`/`ＮＯ`
    and 17DRL01B's two name plates.
    """
    if not jp:
        return False
    if any(0xff61 <= ord(c) <= 0xff9f for c in jp):
        return True
    kana = any(0x3041 <= ord(c) <= 0x30ff or 0xff01 <= ord(c) <= 0xff5e for c in jp)
    return not kana and any(c not in text_chars() for c in jp)


def is_code_row(fn, offset, length, rows=(), japanese=''):
    """Is this dump row script code rather than text?

    Three tests, each conservative, because a false positive deletes a line of the game:

    * the row overlaps bytes the decoder proves are an instruction (06BLK05J 0x1ad is the
      `94 40` jump address of `10 20 00 00 00 94 40`);
    * the file prints nothing at all (31END.SCN is x86 code; 06BLK07.SCN only loads other
      scripts) - `rows`, all of the file's dump offsets, enables this one;
    * the row is outside every print *and* reads as mojibake - `japanese` enables this one.
      Being outside a print is not enough on its own: menu choices and 99CMN's YES/NO are
      drawn another way and are real text.
    """
    if any(x in code_bytes(fn) for x in range(offset, offset + max(length, 1))):
        return True
    if rows and shows_no_text(fn, rows):
        return True
    return bool(japanese) and looks_like_garbage(japanese) and not in_a_print(fn, offset)


def opcode_layouts():
    """The curated table. Unlisted opcodes stop a walk rather than guess its length."""
    return dict(LAYOUTS)


def slot_base(data):
    addrs, i = [], 0
    while i + 3 <= len(data) and data[i] == 0x09:
        addrs.append(int.from_bytes(data[i + 1:i + 3], 'little'))
        i += 3
    if not addrs:
        return None, []
    for base in SLOT_BASES:
        if all(base <= a < base + len(data) for a in addrs):
            return base, [a - base for a in addrs]
    return None, []


def decode(data, base, layouts, starts):
    """Walk the script from `starts`, following jumps and calls.

    Returns (instructions, pointers): pointers are (location, target) of every operand
    that names a place inside this file.
    """
    seen, todo = set(), list(starts)
    insns, pointers = [], []
    while todo:
        at = todo.pop()
        while 0 <= at < len(data) and at not in seen:
            seen.add(at)
            op = data[at]
            kinds = layouts.get(op)
            if kinds is None:
                break
            i, values = at + 1, []
            for kind in kinds:
                if i >= len(data):
                    break
                if kind == 'byte':
                    values.append(('byte', i, data[i]))
                    i += 1
                elif kind == 'word':
                    values.append(('imm', i, int.from_bytes(data[i:i + 2], 'little')))
                    i += 2
                elif kind == 'table':
                    n = data[i]
                    i += 1
                    for k in range(n):
                        values.append(('entry', i, int.from_bytes(data[i:i + 2], 'little')))
                        i += 2
                else:                                    # tagged
                    tag = data[i]
                    i += 1
                    if tag in (0, 1):
                        values.append(('imm' if tag == 0 else 'var', i,
                                       int.from_bytes(data[i:i + 2], 'little')))
                        i += 2
                    else:
                        values.append(('zero', i, 0))
            if not compare_is_plausible(op, values):
                break                    # not a real compare: stop, as for an unknown opcode
            insns.append((at, op, values))
            if op == 0x40:                               # print: a string follows
                end = data.find(b'\x00', i)
                i = len(data) if end < 0 else end + 1
            if op == 0x89 and len(values) == 2 and values[0][2] in OBJECT_SCRIPT_FIELDS:
                kind, loc, val = values[1]
                target = val - base
                if 0 <= target < len(data):
                    pointers.append((loc, target))
                    todo.append(target)
            idx = ADDRESS_OPS.get(op)
            if idx is not None and idx < len(values):
                kind, loc, val = values[idx]
                if kind == 'imm':
                    target = val - base
                    if 0 <= target < len(data):
                        pointers.append((loc, target))
                        todo.append(target)
            if op in ADDRESS_TABLE_OPS:
                for kind, loc, val in values:
                    if kind != 'entry':
                        continue
                    target = val - base
                    if 0 <= target < len(data):
                        pointers.append((loc, target))
                        todo.append(target)
            if op in (0x83, 0x09):                       # end of block / jump away
                break
            at = i
    return insns, pointers


def analyse(fn):
    path = os.path.join(HERE, 'original', 'decompressed', fn)
    data = open(path, 'rb').read()
    base, entries = slot_base(data)
    if base is None:
        # A map script has no `09 <addr>` entry table at the top - its blocks are named
        # by the zone tables instead - so it was being skipped entirely. Those are the
        # files that hold the map exits, which is most of what one would want to decode.
        base, entries, guessed_base = 0x0000, [], True
    else:
        guessed_base = False
    layouts = opcode_layouts()
    # Blocks reached only from outside this file - a zone table in the map script, or
    # an object spawned elsewhere - are not linked from the entry table, so seed the
    # walk with every block start as well (a block follows the file's own end-of-block
    # jump, see script_map.block_starts).
    from script_map import block_starts
    roots = sorted(set(entries) | set(block_starts(data, base, entries)))
    insns, pointers = decode(data, base, layouts, roots)
    # the entry table itself is a list of pointers
    for i, target in enumerate(entries):
        pointers.append((1 + 3 * i, target))
    return {'file': fn, 'base': base, 'entries': entries, 'guessed_base': guessed_base,
            'insns': insns, 'pointers': sorted(set(pointers))}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    check = '--check' in sys.argv
    listing = '--listing' in sys.argv
    for fn in args:
        r = analyse(fn)
        if not r:
            print('%s: no entry table' % fn)
            continue
        print('%s: base %#06x, %d entries, %d instructions decoded, %d pointers'
              % (fn, r['base'], len(r['entries']), len(r['insns']), len(r['pointers'])))
        if listing:
            for at, op, values in r['insns'][:120]:
                shown = ' '.join('%s=%#06x' % (k, v) for k, _l, v in values)
                print('   %#06x  %02x  %s' % (at, op, shown))
        if check:
            from rominfo import POINTERS_TO_ADD
            import openpyxl
            from rominfo import POINTER_XLS_PATH
            registered = {loc for f, loc, _t in POINTERS_TO_ADD if f == fn}
            try:
                ws = openpyxl.load_workbook(POINTER_XLS_PATH, read_only=True)[fn]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row and row[1]:
                        registered.add(int(str(row[1]), 16))
            except KeyError:
                pass
            found = {loc for loc, _t in r['pointers']}
            missing = sorted(found - registered)
            extra = sorted(registered - found)
            print('   %d pointers the decoder finds are NOT registered:' % len(missing))
            for loc in missing:
                target = dict(r['pointers'])[loc]
                print("       ('%s', %#0x, %#0x)," % (fn, loc, target))
            print('   %d registered that the decoder does not see: %s'
                  % (len(extra), ' '.join('%#06x' % x for x in extra[:12])))


if __name__ == '__main__':
    main()
