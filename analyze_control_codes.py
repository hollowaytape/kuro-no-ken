"""
    Comprehensive analysis of the BD.BIN control code dispatch table.

    The game's script engine dispatches on each byte read from the script stream
    via a 256-entry function pointer table at BD.BIN offset 0x22d0. This script
    classifies every entry by:
      - Handler type (NOP, pointer, table lookup, conditional, etc.)
      - Which shared subroutine it calls first
      - How many bytes the control code consumes from the stream
      - Whether it reads a pointer in the "CC 00 ptr_lo ptr_hi" pattern

    Usage:
        python analyze_control_codes.py
        python analyze_control_codes.py --verbose
"""

import os
import sys
from collections import OrderedDict

BD_BIN_PATH = os.path.join('original', 'decompressed', 'BD.BIN')
DISPATCH_TABLE_OFFSET = 0x22d0
DISPATCH_TABLE_SIZE = 0x200  # 256 entries * 2 bytes
DEFAULT_HANDLER = 0x0072

# Known shared subroutines and what they do
SUBROUTINE_INFO = {
    0x17b8: {
        'name': 'mode_dispatch',
        'doc': 'Reads mode byte from stream. mode==0: reads 2-byte pointer. '
               'mode==1: table lookup via 0x17cc. mode>1: returns 0.',
    },
    0x17c6: {
        'name': 'byte_read_branch',
        'doc': 'Reads a byte and branches based on its value.',
    },
    0x17cc: {
        'name': 'table_lookup',
        'doc': 'lodsw es: then uses word as index into table at 0x06d2. '
               'Reads 2 bytes (table index, NOT a text pointer).',
    },
    0x17d7: {
        'name': 'conditional_branch',
        'doc': 'Conditional pointer follow.',
    },
    0x17dd: {
        'name': 'conditional_flag',
        'doc': 'Conditional with flag bit manipulation.',
    },
    0x17f1: {
        'name': 'byte_read',
        'doc': 'Reads a single byte from the stream.',
    },
    0x180c: {
        'name': 'setup_a',
        'doc': 'Setup routine (saves registers, initializes state).',
    },
    0x181b: {
        'name': 'setup_b',
        'doc': 'Setup routine variant.',
    },
}


def read_bdbin():
    with open(BD_BIN_PATH, 'rb') as f:
        return f.read()


def get_dispatch_entries(contents):
    """Return list of (code_byte, handler_offset) for all 256 entries."""
    table = contents[DISPATCH_TABLE_OFFSET:DISPATCH_TABLE_OFFSET + DISPATCH_TABLE_SIZE]
    entries = []
    for i in range(256):
        lo = table[i * 2]
        hi = table[i * 2 + 1]
        entries.append((i, (hi * 0x100) + lo))
    return entries


def find_first_call_target(contents, func_offset, max_scan=80):
    """Find the target of the first CALL (0xe8) instruction in a function."""
    func_bytes = contents[func_offset:func_offset + max_scan]
    ret_pos = func_bytes.find(b'\xc3')
    scan_len = ret_pos if ret_pos > 0 else max_scan

    for j in range(scan_len - 2):
        if func_bytes[j] == 0xe8:
            rel = (func_bytes[j + 2] * 0x100) + func_bytes[j + 1]
            if rel > 0x7fff:
                rel -= 0x10000
            target = (func_offset + j + 3 + rel) & 0xffff
            return j, target
    return None, None


def find_all_call_targets(contents, func_offset, max_scan=80):
    """Find all CALL targets within a function body."""
    func_bytes = contents[func_offset:func_offset + max_scan]
    ret_pos = func_bytes.find(b'\xc3')
    scan_len = ret_pos if ret_pos > 0 else max_scan
    targets = []

    for j in range(scan_len - 2):
        if func_bytes[j] == 0xe8:
            rel = (func_bytes[j + 2] * 0x100) + func_bytes[j + 1]
            if rel > 0x7fff:
                rel -= 0x10000
            target = (func_offset + j + 3 + rel) & 0xffff
            targets.append((j, target))
    return targets


def classify_entry(contents, code, func_offset):
    """Classify a dispatch table entry by its behavior."""
    if func_offset == DEFAULT_HANDLER:
        return {
            'type': 'nop',
            'handler': func_offset,
            'first_call': None,
            'calls_17b8_first': False,
            'has_pointer_mode': False,
            'reads_stream_word': False,
            'doc': 'Default/NOP handler — does nothing, returns immediately.',
        }

    func_bytes = contents[func_offset:func_offset + 80]
    ret_pos = func_bytes.find(b'\xc3')
    func_len = ret_pos if ret_pos > 0 else 80

    # Check for direct lodsw es: at start (26 ad = reads 2-byte value from stream)
    starts_with_lodsw = func_bytes[:2] == b'\x26\xad'

    # Check if it's a zero-length function (starts with RET)
    if func_bytes[0] == 0xc3:
        return {
            'type': 'nop',
            'handler': func_offset,
            'first_call': None,
            'calls_17b8_first': False,
            'has_pointer_mode': False,
            'reads_stream_word': False,
            'func_len': 0,
            'doc': 'Zero-length handler (immediate RET).',
        }

    # Find first call target
    first_call_pos, first_call_target = find_first_call_target(contents, func_offset)

    # Check if first instruction is call 0x17b8
    calls_17b8_first = (first_call_pos == 0 and first_call_target == 0x17b8)

    # Check for any call to known subroutines
    all_calls = find_all_call_targets(contents, func_offset)
    called_subroutines = set()
    for pos, target in all_calls:
        if target in SUBROUTINE_INFO:
            called_subroutines.add(target)

    # Check for lodsw es: anywhere in function
    has_lodsw = b'\x26\xad' in func_bytes[:func_len]
    has_lodsb = b'\x26\xac' in func_bytes[:func_len]

    # Classify by primary behavior
    if calls_17b8_first:
        entry_type = 'pointer_mode_dispatch'
        doc = ('Calls mode_dispatch (0x17b8) first. Pattern: CC MODE [ptr]. '
               'MODE=0x00: next 2 bytes are a pointer. '
               'MODE=0x01: table lookup. MODE>0x01: no pointer.')
    elif starts_with_lodsw:
        entry_type = 'direct_word_read'
        # Check if it's specifically 0x09 pattern (lodsw; mov si,ax = goto pointer)
        if func_bytes[:4] == b'\x26\xad\x8b\xf0':
            doc = 'Direct pointer: lodsw es:, mov si, ax — jumps to 2-byte pointer address.'
        else:
            doc = 'Reads a 2-byte value directly from stream via lodsw es:.'
    elif first_call_target == 0x17cc:
        entry_type = 'table_lookup'
        doc = 'Reads 2-byte index, looks up in data table at 0x06d2. NOT a text pointer.'
    elif first_call_target == 0x17d7:
        entry_type = 'conditional_branch'
        doc = 'Conditional branch — follows pointer only if condition met.'
    elif first_call_target == 0x17dd:
        entry_type = 'conditional_flag'
        doc = 'Conditional flag test with bit manipulation.'
    elif first_call_target == 0x180c:
        entry_type = 'setup'
        doc = 'Setup/initialization routine.'
    elif first_call_target == 0x181b:
        entry_type = 'setup'
        doc = 'Setup routine variant.'
    elif first_call_target == 0x17c6:
        entry_type = 'byte_dispatch'
        doc = 'Reads a byte from stream and dispatches on its value.'
    elif first_call_target == 0x17f1:
        entry_type = 'byte_read'
        doc = 'Reads a single byte from the stream.'
    else:
        entry_type = 'other'
        doc = 'Specialized handler.'

    return {
        'type': entry_type,
        'handler': func_offset,
        'first_call': first_call_target,
        'calls_17b8_first': calls_17b8_first,
        'has_pointer_mode': calls_17b8_first,
        'reads_stream_word': has_lodsw or calls_17b8_first,
        'reads_stream_byte': has_lodsb,
        'func_len': func_len,
        'called_subroutines': called_subroutines,
        'doc': doc,
    }


def analyze():
    """Run complete dispatch table analysis."""
    contents = read_bdbin()
    entries = get_dispatch_entries(contents)

    results = OrderedDict()
    for code, handler in entries:
        results[code] = classify_entry(contents, code, handler)

    return results


def get_zero_pointer_first_bytes(results):
    """Return the set of control codes that use the CC 00 ptr_lo ptr_hi pattern.

    These are codes whose handler calls 0x17b8 as its first instruction.
    0x17b8 reads a mode byte: if mode==0x00, the next 2 bytes are a raw pointer.
    """
    return sorted(code for code, info in results.items()
                  if info['calls_17b8_first'])


def get_direct_pointer_codes(results):
    """Return codes that read a 2-byte pointer directly (lodsw es:; mov si, ax)."""
    return sorted(code for code, info in results.items()
                  if info['type'] == 'direct_word_read')


def print_report(results, verbose=False):
    """Print human-readable analysis report."""
    # Group by type
    by_type = {}
    for code, info in results.items():
        t = info['type']
        by_type.setdefault(t, []).append(code)

    print("=" * 72)
    print("BD.BIN Control Code Dispatch Table Analysis")
    print("  Table location: 0x%04x-0x%04x" % (
        DISPATCH_TABLE_OFFSET, DISPATCH_TABLE_OFFSET + DISPATCH_TABLE_SIZE))
    print("  Default handler: 0x%04x" % DEFAULT_HANDLER)
    print("  Active codes: %d / 256" % sum(
        1 for info in results.values() if info['type'] != 'nop'))
    print("=" * 72)

    type_labels = {
        'pointer_mode_dispatch': 'Mode-dispatched pointer (CC MODE [ptr]) — calls 0x17b8 first',
        'direct_word_read': 'Direct word read (lodsw es:) — reads 2 bytes from stream',
        'table_lookup': 'Table lookup (calls 0x17cc) — reads 2-byte index, NOT a text pointer',
        'conditional_branch': 'Conditional branch (calls 0x17d7)',
        'conditional_flag': 'Conditional flag (calls 0x17dd)',
        'byte_dispatch': 'Byte dispatch (calls 0x17c6) — reads 1 byte, branches',
        'byte_read': 'Byte read (calls 0x17f1) — reads 1 byte from stream',
        'setup': 'Setup/init (calls 0x180c or 0x181b)',
        'other': 'Other specialized handlers',
        'nop': 'NOP / default handler (0x0072)',
    }

    for entry_type in ['pointer_mode_dispatch', 'direct_word_read', 'table_lookup',
                       'conditional_branch', 'conditional_flag', 'byte_dispatch',
                       'byte_read', 'setup', 'other', 'nop']:
        codes = by_type.get(entry_type, [])
        if not codes:
            continue
        print()
        print("--- %s (%d codes) ---" % (type_labels.get(entry_type, entry_type), len(codes)))

        for code in codes:
            info = results[code]
            if verbose or entry_type != 'nop':
                print("  0x%02x -> handler 0x%04x" % (code, info['handler']), end='')
                if info.get('func_len') is not None:
                    print("  [%db]" % info['func_len'], end='')
                if info.get('first_call'):
                    name = SUBROUTINE_INFO.get(info['first_call'], {}).get('name', '???')
                    print("  first_call=0x%04x (%s)" % (info['first_call'], name), end='')
                print()
            elif entry_type == 'nop' and code == codes[0]:
                print("  0x%02x ... 0x%02x  (all -> 0x%04x)" % (codes[0], codes[-1], DEFAULT_HANDLER))

    # Summary for pointer finder
    zpfb = get_zero_pointer_first_bytes(results)
    direct = get_direct_pointer_codes(results)

    print()
    print("=" * 72)
    print("POINTER PATTERN SUMMARY (for find_pointers.py)")
    print("=" * 72)
    print()
    print("Mode-dispatched pointers: CC 00 ptr_lo ptr_hi")
    print("  (codes that call 0x17b8 as first instruction)")
    print("  ZERO_POINTER_FIRST_BYTES = %s" % zpfb)
    print()
    print("Direct pointer reads: CC ptr_lo ptr_hi")
    print("  (codes starting with lodsw es:)")
    print("  Codes: %s" % [hex(x) for x in direct])
    print()

    # Compare with current ZERO_POINTER_FIRST_BYTES
    current_zpfb = set([
        0x00, 0x02, 0x03, 0x08, 0x39, 0x3f, 0x40, 0x41, 0x43, 0x46, 0x49,
        0x4c, 0x50, 0x50, 0x51, 0x52, 0x54, 0x55, 0x57,
        0x5a, 0x5d, 0x5e, 0x5f, 0x60, 0x61, 0x64, 0x65,
        0x66, 0x69, 0x6e, 0x6f, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76,
        0x77, 0x78, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7e, 0x7f, 0x8b, 0x90,
        0x94, 0x99, 0x9f, 0xa0, 0xa1, 0xa4, 0xa5, 0xa7,
        0xab, 0xaf, 0xb0, 0xb1, 0xb3, 0xb5, 0xb7, 0xbe, 0xc5, 0xcf, 0xff,
    ])
    new_zpfb = set(zpfb)

    should_remove = sorted(current_zpfb - new_zpfb)
    should_add = sorted(new_zpfb - current_zpfb)

    if should_remove:
        print("Entries to REMOVE from current ZERO_POINTER_FIRST_BYTES:")
        for code in should_remove:
            info = results[code]
            print("  0x%02x — %s" % (code, info['type']))

    if should_add:
        print()
        print("Entries to ADD to current ZERO_POINTER_FIRST_BYTES:")
        for code in should_add:
            info = results[code]
            print("  0x%02x — %s" % (code, info['type']))

    if not should_remove and not should_add:
        print("Current ZERO_POINTER_FIRST_BYTES matches analysis perfectly.")


def generate_zpfb_code(results):
    """Generate the Python code for the corrected ZERO_POINTER_FIRST_BYTES."""
    zpfb = get_zero_pointer_first_bytes(results)
    lines = ["# Codes that call 0x17b8 as their first instruction.",
             "# Pattern: CC 00 ptr_lo ptr_hi (mode byte 0x00 = raw pointer).",
             "# Generated by analyze_control_codes.py from BD.BIN dispatch table.",
             "ZERO_POINTER_FIRST_BYTES = ["]
    chunk = "    "
    for i, code in enumerate(zpfb):
        chunk += "0x%02x, " % code
        if (i + 1) % 10 == 0:
            lines.append(chunk.rstrip())
            chunk = "    "
    if chunk.strip():
        lines.append(chunk.rstrip())
    lines.append("]")
    return "\n".join(lines)


if __name__ == '__main__':
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    results = analyze()
    print_report(results, verbose=verbose)
    print()
    print("=" * 72)
    print("GENERATED CODE (paste into rominfo.py)")
    print("=" * 72)
    print(generate_zpfb_code(results))
