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
    0x0c: ['word', 'word'],              # 1d26  branch if flag <w0> clear -> <w1>
    0x0d: ['word', 'word'],              # 1d30  branch if flag <w0> set -> <w1>
    0x1d: ['word'],                      # 1dcb  set flag <w0>
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
               0xb1: 0, 0x9e: 3}
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
