"""Which dialogue strings print in graphics mode (the VWF) and which in text mode.

With `--gfx-dialogue`, a string is drawn with the variable-width font only if it prints
inside a box frame (tools/dialogue_gfx.py); text over the map, the location title and
battle windows stay in fixed-width text mode. Typesetting has to know which, because a
line set to the VWF's pixel width holds more characters than text mode's 50 columns.

That is measured, not guessed: tools/sweep_dialogue_gfx.py --record plays every block of
every script with the patches on and logs each print's string offset and mode. This
aggregates those logs into dialogue_modes.json (checked in, so the build does not need the
emulator), and answers "what mode does the text at this offset print in?".

    python tools/dialogue_modes.py scratch_emu/modes/m*.jsonl     # rebuild the json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PATH = os.path.join(HERE, 'dialogue_modes.json')
PRINT = b'\x40\x02'                  # print opcode, string tag: the string follows

_modes = None
_scripts = {}


def build(logs):
    out = {}
    for path in logs:
        for line in open(path):
            r = json.loads(line)
            seen = out.setdefault(r['file'], {}).setdefault(str(r['offset']), '')
            if r['mode'] not in seen:
                out[r['file']][str(r['offset'])] = ''.join(sorted(seen + r['mode']))
    with open(PATH, 'w') as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    return out


def string_start(data, location):
    """Offset of the print string that the text at `location` is part of: just after
    the `40 02` before it (Shift-JIS text holds no 00 or 02 bytes)."""
    i = location
    while i >= 2:
        if data[i - 2:i] == PRINT:
            return i
        if data[i - 1] == 0:
            return None
        i -= 1
    return None


def mode_of(filename, location):
    """'g' (always graphics: VWF), 't' (always text), 'gt' (both, depending on the
    path), or None (never reached by the sweep, or not inside a print)."""
    global _modes
    if _modes is None:
        _modes = json.load(open(PATH)) if os.path.exists(PATH) else {}
    if filename not in _scripts:
        p = os.path.join(PROJECT, 'original', 'decompressed', filename)
        _scripts[filename] = open(p, 'rb').read() if os.path.exists(p) else b''
    start = string_start(_scripts[filename], location)
    if start is None:
        return None
    return _modes.get(filename, {}).get(str(start))


if __name__ == '__main__':
    out = build(sys.argv[1:])
    counts = {}
    for f in out.values():
        for m in f.values():
            counts[m] = counts.get(m, 0) + 1
    print('%s: %d scripts, print strings by mode %s' % (PATH, len(out), counts))
