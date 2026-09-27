"""Linear disassembly of a .SCN with the interpreter's operand layouts (script_decode's
plus the ones read off BD.BIN on 2026-09-26; docs/engine_notes.md "More of the opcode table").

    python tools/scn_disasm.py 07CSL02.SCN 0x1800 [lo hi]      (lo/hi are file offsets; the
    second argument is the slot the file loads at: 0 hub, 0x1800 stage, 0x3d00 scene)
"""
import re
import struct
import sys

sys.path.insert(0, 'tools')
import script_decode as sd  # noqa: E402

LAY = dict(sd.LAYOUTS)
# read off BD.BIN by hand (handlers 1c36 1c5b 1ca8 1cf9 1e92 1ea5 28af 28db 2537.. 2582..)
LAY.update({
    0x01: ['word'], 0x02: ['word'],                 # far call native code at script:addr / at var
    0x06: ['switch'], 0x0b: ['switch'],             # var, default(tagged), n, n x tagged(3)
    0x07: [],
    0xa1: ['tagged', 'tagged'], 0xa3: ['tagged', 'tagged', 'tagged'],
    0xbb: [],
    0x84: ['word', 'byte'], 0x85: ['word', 'byte'],   # var = cur obj field (byte/word)
    0x86: ['byte', 'word'], 0x87: ['byte', 'word'],   # cur obj field = var
    0x88: ['byte', 'byte'], 0x89: ['byte', 'word'],   # cur obj field = imm
    0xc8: ['word', 'tagged', 'byte'], 0xc9: ['word', 'tagged', 'byte'],   # var = obj[i].field
    0xca: ['tagged', 'byte', 'word'], 0xcb: ['tagged', 'byte', 'word'],   # obj[i].field = var
    0xcc: ['tagged', 'byte', 'byte'], 0xcd: ['tagged', 'byte', 'word'],   # obj[i].field = imm
    0x2f: ['word', 'word'], 0x30: ['word', 'word'], 0x31: ['word', 'word'], 0x32: ['word', 'word'],
    0x33: ['word', 'word'], 0x34: ['word', 'word'], 0x35: ['word', 'word'],
    0x0e: ['word', 'word', 'word'], 0x0f: ['word', 'word', 'word'],
    0xc0: ['tagged', 'tagged', 'tagged'], 0xc1: ['tagged', 'tagged', 'word'], 0xc2: ['tagged', 'tagged', 'word'],
    0xc3: ['tagged', 'tagged', 'word'], 0xc4: ['tagged', 'tagged', 'word'], 0xc6: ['word'], 0xc7: ['tagged', 'word'],
    0x8b: ['tagged', 'byte', 'word', 'byte', 'word', 'word'],
    0xa0: ['tagged'], 0xaa: ['tagged'], 0xab: ['tagged'], 0xb1: ['tagged'], 0x5a: ['tagged'], 0x3c: ['tagged'], 0x3f: ['tagged'],
    0xa2: ['tagged', 'tagged'], 0xad: ['tagged', 'tagged'], 0xae: ['tagged', 'tagged'], 0xbe: ['tagged', 'tagged'],
    0xa4: ['tagged'] * 5, 0xb7: ['tagged'] * 5, 0xa8: ['word', 'tagged'], 0xb2: ['word', 'tagged'],
    0xac: ['word', 'word'], 0xb6: ['tagged', 'byte'], 0xb8: ['word'], 0xbd: ['word'],
    0xba: [], 0xbc: [], 0x3a: [], 0x3b: [], 0x3e: [],
    0x39: ['tagged', 'str'],
})
NAMES = {0x01: 'native', 0x02: 'native@var', 0x04: 'call', 0x09: 'jmp', 0x0c: 'jf-set', 0x0d: 'jf-clear',
         0x10: 'jne', 0x12: 'je', 0x14: 'jle', 0x16: 'jl', 0x18: 'jg', 0x1a: 'jge',
         0x11: 'jne.v', 0x13: 'je.v', 0x15: 'jle.v', 0x17: 'jl.v', 0x19: 'jg.v', 0x1b: 'jge.v',
         0x1c: 'clr', 0x1d: 'set', 0x1f: 'var=0', 0x20: 'var=', 0x21: 'var=var', 0x22: 'var++', 0x23: 'var--',
         0x28: 'var+=', 0x2a: 'var-=', 0x2c: 'var&=', 0x2e: 'var|=', 0x06: 'switch', 0x0b: 'switch',
         0x83: 'end', 0xb0: 'run', 0x80: 'spawn', 0x88: 'obj.b=', 0x89: 'obj.w=', 0x84: 'var=obj.b', 0x85: 'var=obj.w',
         0x86: 'obj.b=var', 0x87: 'obj.w=var', 0xc8: 'var=o[].b', 0xc9: 'var=o[].w', 0xca: 'o[].b=var',
         0xcb: 'o[].w=var', 0xcc: 'o[].b=', 0xcd: 'o[].w=', 0xa1: 'pos', 0xa3: 'pos[]', 0x40: 'print', 0x39: 'load'}


def tagged(data, p):
    t = data[p]
    if t == 0:
        return ('#%04x' % struct.unpack('<H', data[p + 1:p + 3])[0], p + 3)
    if t == 1:
        return ('v%02x' % struct.unpack('<H', data[p + 1:p + 3])[0], p + 3)
    if t == 2:                                   # a string: 39 (load) and b6 (a graphic) take one
        e = data.index(bytes([0]), p + 1)
        return ('"%s"' % data[p + 1:e].decode('ascii', 'replace'), e + 1)
    return ('t%d' % t, p + 1)


def dis(data, base, lo, hi, out=print):
    at = lo
    while at < hi:
        op = data[at]
        lay = LAY.get(op)
        if lay is None:
            out('%04x/%04x: %02x ??' % (at, at + base, op))
            at += 1
            continue
        p = at + 1
        vals = []
        for kind in lay:
            if kind == 'word':
                vals.append('%04x' % struct.unpack('<H', data[p:p + 2])[0]); p += 2
            elif kind == 'byte':
                vals.append('%02x' % data[p]); p += 1
            elif kind == 'tagged':
                v, p = tagged(data, p); vals.append(v)
            elif kind == 'switch':
                var = struct.unpack('<H', data[p:p + 2])[0]; p += 2
                dflt, p = tagged(data, p)
                n = data[p]; p += 1
                ents = []
                for k in range(n):
                    v, p = tagged(data, p); ents.append(v)
                vals.append('v%02x default %s [%s]' % (var, dflt, ' '.join(ents)))
            elif kind == 'table':
                n = data[p]; p += 1
                vals.append('table[%d]' % n); p += 2 * n
            elif kind == 'str':
                p += 1
                e = data.index(bytes([0]), p)
                vals.append(data[p:e].decode('ascii', 'replace')); p = e + 1
            else:  # string / unknown kinds in sd
                e = data.index(b'\x00', p)
                vals.append(repr(data[p:e])[:30]); p = e + 1
        out('%04x/%04x: %02x %-9s %s' % (at, at + base, op, NAMES.get(op, ''), ' '.join(vals)))
        at = p


if __name__ == '__main__':
    fn, base = sys.argv[1], int(sys.argv[2], 16)
    data = open('original/decompressed/' + fn, 'rb').read()
    lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0
    hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else len(data)
    dis(data, base, lo, hi)
