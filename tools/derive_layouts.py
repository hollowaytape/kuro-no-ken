"""Derive every script opcode's operand layout, exploring all paths in its handler.

The first cut stopped at the first conditional branch, so any handler that decides what
to read gave a short (wrong) layout. This walks both sides of every branch and reports
the operand sequences each path consumes:

  * one sequence  -> the layout is unambiguous
  * several       -> the opcode's operands depend on a condition; printed for a human

Operand readers (subroutines that consume script bytes on the handler's behalf) are
resolved recursively, so `call 0x17b8` counts as the tagged operand it reads.

    python tools/derive_layouts.py            # every opcode
    python tools/derive_layouts.py 5a 9e 20   # just these
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import capstone                                        # noqa: E402

BD = open(os.path.join(HERE, '..', 'original', 'decompressed', 'BD.BIN'), 'rb').read()
TABLE = 0x22d0
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
MD.detail = False

# Subroutines that read script bytes. 'tagged' is BD.BIN 0x17b8's encoding: a tag byte,
# then a word when the tag is 0 (immediate) or 1 (variable index), nothing above that.
READERS = {
    0x17b8: ['tagged'], 0x17ba: ['tagged_notag'], 0x180c: ['tagged'],
    0x17f1: ['tagged'], 0x2579: ['byte'], 0x17cc: ['word'],
    0x17d7: ['word'], 0x17dd: ['word'],
}


def handler(op):
    return int.from_bytes(BD[TABLE + 2 * op:TABLE + 2 * op + 2], 'little')


def paths_for(start, budget=400):
    """All operand sequences a routine can consume, as tuples."""
    out = set()

    def walk(at, taken, seen, depth):
        if depth > 40 or len(out) > 24 or budget <= 0:
            out.add(tuple(taken))
            return
        while True:
            if at in seen:
                out.add(tuple(taken))
                return
            seen = seen | {at}
            ins = list(MD.disasm(BD[at:at + 16], at))
            if not ins:
                out.add(tuple(taken))
                return
            i = ins[0]
            m, ops = i.mnemonic, i.op_str
            if m == 'lodsb':
                taken = taken + ['byte']
            elif m == 'lodsw':
                taken = taken + ['word']
            elif m == 'call':
                try:
                    dest = int(ops, 16)
                except ValueError:
                    dest = None
                if dest in READERS:
                    taken = taken + READERS[dest]
                elif dest is not None:
                    # a call that might itself read: explore it, keeping the longest
                    sub = paths_for(dest, budget - 1) if dest != at else {()}
                    longest = max(sub, key=len) if sub else ()
                    taken = taken + list(longest)
            elif m == 'ret':
                out.add(tuple(taken))
                return
            elif m == 'jmp':
                try:
                    at = int(ops, 16)
                    continue
                except ValueError:
                    out.add(tuple(taken))
                    return
            elif m.startswith('j'):
                try:
                    walk(int(ops, 16), list(taken), seen, depth + 1)
                except ValueError:
                    pass
            at += i.size

    walk(start, [], frozenset(), 0)
    return out


def layout(op):
    h = handler(op)
    if not (0x100 < h < len(BD)):
        return None, None
    return h, paths_for(h)


def main():
    which = [int(a, 16) for a in sys.argv[1:]] or range(0x100)
    for op in which:
        h, paths = layout(op)
        if h is None:
            continue
        shapes = sorted({'+'.join(p) or '-' for p in paths})
        flag = '' if len(shapes) == 1 else '   AMBIGUOUS'
        print('%02x  handler %#06x  %s%s' % (op, h, ' | '.join(shapes)[:70], flag))


if __name__ == '__main__':
    main()
