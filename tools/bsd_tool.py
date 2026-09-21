"""
BSD (Battle Script) disassembler/reassembler for Kuro no Ken.

Parses BSD files into structured segments, allows text replacement,
and reassembles with all absolute offsets correctly relocated.

BSD file structure:
  0x00-0x05  Header (magic b4 0b 5c 99 d8 16, or zeroed)
  0x06-0x11  Resource offset table (up to 6 entries, 2B LE each)
  0x12-0x31  Event table (16 x86 handler entry points, 2B LE each)
  0x32-0x3c  Metadata
  0x3d+      Resource paths, x86 handler stubs, battle script + inline text

Text is embedded inline in battle script data, preceded by a preamble
sequence (typically ending with 5c 74 30 5c 6b 30 5c 66) and terminated
by a null byte.

x86 handler stubs begin with 1e 06 (PUSH DS; PUSH ES) and end with
cb (RETF). They contain CS:MOV WORD instructions that store absolute
file offsets to script data sections.
"""

import os
import struct
from collections import namedtuple
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

# A fixup is a location in the file containing an absolute offset that
# needs adjustment when text sizes change.
Fixup = namedtuple('Fixup', [
    'file_offset',    # where the value lives in the original file
    'size',           # 1 or 2 bytes
    'value',          # the current absolute offset stored there
    'kind',           # 'event_table', 'resource_offset', 'cs_mov_value', 'cs_mov_target', 'metadata',
                      # 'rel16' (a near call/jmp/jcc displacement; value = the target,
                      # file_offset = the displacement, which ends where the instruction ends),
                      # 'cs_disp' (a cs: memory operand's address), 'imm_ptr' (mov si/di/bx,
                      # offset), 'table_word' (an entry of a 0xffff-terminated offset table)
])

# A text region that can be replaced.
TextRegion = namedtuple('TextRegion', [
    'offset',         # start of SJIS text (after preamble)
    'end',            # end of text (the null terminator position)
    'text_bytes',     # original SJIS bytes (excluding null)
    'preamble_start', # start of the preamble before text
])

HEADER_SIZE = 0x06
RESOURCE_TABLE_START = 0x06
RESOURCE_TABLE_END = 0x12
EVENT_TABLE_START = 0x12
EVENT_TABLE_END = 0x32
METADATA_END = 0x3d  # first resource path typically starts here

# Known text preamble suffixes — the last bytes before SJIS text begins
TEXT_PREAMBLE_TAIL = bytes([0x5c, 0x74, 0x30, 0x5c, 0x6b, 0x30, 0x5c, 0x66])


def _is_sjis_lead(b):
    """Check if byte is a Shift-JIS lead byte."""
    return (0x81 <= b <= 0x9f) or (0xe0 <= b <= 0xef)


def _find_text_end(data, start):
    """Find the end of a SJIS text region starting at `start`.
    Returns the offset of the null terminator."""
    i = start
    while i < len(data):
        b = data[i]
        if b == 0x00:
            return i
        if _is_sjis_lead(b) and i + 1 < len(data):
            i += 2
        elif 0x20 <= b <= 0x7e:  # printable ASCII
            i += 1
        elif b == 0x0a:  # newline in some contexts
            i += 1
        else:
            # Not text — but we started after preamble, so this shouldn't happen
            # in well-formed data. Return current position.
            return i
    return len(data)


def _find_preamble_start(data, text_start):
    """Walk backwards from text_start to find where the preamble begins.
    The preamble is a sequence of 5c XX bytes before the text."""
    i = text_start
    # The preamble ends right before text_start. Walk back through 5c XX pairs.
    while i >= 2 and data[i - 1] in range(0x100) and data[i - 2] == 0x5c:
        i -= 2
    return i


def parse_bsd(data):
    """Parse a BSD file and return its structure.

    Returns dict with:
        'header': bytes (0x00-0x05)
        'resource_offsets': list of 2-byte LE values (0x06-0x11)
        'event_table': list of 2-byte LE values (0x12-0x31)
        'metadata': bytes (0x32-0x3c)
        'data': full file bytes (for reference)
        'fixups': list of Fixup namedtuples
        'text_regions': list of TextRegion namedtuples
        'x86_regions': list of (start, end) tuples for x86 code
    """
    result = {
        'header': data[0:HEADER_SIZE],
        'resource_offsets': [],
        'event_table': [],
        'metadata': data[EVENT_TABLE_END:METADATA_END],
        'data': data,
        'fixups': [],
        'text_regions': [],
        'x86_regions': [],
    }

    # Parse resource offset table
    for i in range(RESOURCE_TABLE_START, RESOURCE_TABLE_END, 2):
        val = struct.unpack_from('<H', data, i)[0]
        result['resource_offsets'].append(val)
        if val != 0 and val < len(data):
            result['fixups'].append(Fixup(i, 2, val, 'resource_offset'))

    # Parse event table
    for i in range(EVENT_TABLE_START, EVENT_TABLE_END, 2):
        val = struct.unpack_from('<H', data, i)[0]
        result['event_table'].append(val)
        if val < len(data):
            result['fixups'].append(Fixup(i, 2, val, 'event_table'))

    # Parse metadata pointers at 0x32, 0x34, 0x36
    # 0x32: always a pointer to battle stats block
    # 0x34: pointer to second battle stats block (0 = absent)
    # 0x36: pointer to AI/behavior data (0xFFFF = absent)
    meta32 = struct.unpack_from('<H', data, 0x32)[0]
    if 0 < meta32 < len(data):
        result['fixups'].append(Fixup(0x32, 2, meta32, 'metadata'))
    meta34 = struct.unpack_from('<H', data, 0x34)[0]
    if 0 < meta34 < len(data):
        result['fixups'].append(Fixup(0x34, 2, meta34, 'metadata'))
    meta36 = struct.unpack_from('<H', data, 0x36)[0]
    if meta36 not in (0, 0xffff) and 0 < meta36 < len(data):
        result['fixups'].append(Fixup(0x36, 2, meta36, 'metadata'))

    # Find x86 handler stubs and CS:MOV instructions
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    cs_mov_target_addr = None  # the address ALL CS:MOV WORDs write to (== file_size)

    for entry in result['event_table']:
        if entry >= len(data):
            continue
        if data[entry:entry + 2] == b'\xcb\x90':
            continue  # empty handler (RETF; NOP)
        if data[entry:entry + 2] != b'\x1e\x06':
            continue  # unexpected, skip

        code_end = entry
        for insn in md.disasm(data[entry:entry + 1024], entry):
            raw = data[insn.address:insn.address + insn.size]
            # CS:MOV WORD [addr], value — the VALUE is a script data pointer
            if raw[:3] == b'\x2e\xc7\x06' and insn.size == 7:
                addr = struct.unpack_from('<H', raw, 3)[0]
                val = struct.unpack_from('<H', raw, 5)[0]
                # The value is a pointer to script data
                if val < len(data):
                    result['fixups'].append(Fixup(
                        insn.address + 5, 2, val, 'cs_mov_value'))
                # The target address is file_size (scratch variable)
                cs_mov_target_addr = addr
                result['fixups'].append(Fixup(
                    insn.address + 3, 2, addr, 'cs_mov_target'))

            if insn.mnemonic == 'retf':
                code_end = insn.address + insn.size
                break

        if code_end > entry:
            result['x86_regions'].append((entry, code_end))

    # Deduplicate cs_mov_target fixups (all point to same addr)
    seen_targets = set()
    deduped = []
    for f in result['fixups']:
        if f.kind == 'cs_mov_target':
            if f.file_offset not in seen_targets:
                seen_targets.add(f.file_offset)
                deduped.append(f)
        else:
            deduped.append(f)
    result['fixups'] = deduped

    # Find text regions — look for the preamble pattern followed by SJIS text
    i = METADATA_END
    while i < len(data) - len(TEXT_PREAMBLE_TAIL) - 2:
        # Look for preamble tail
        if data[i:i + len(TEXT_PREAMBLE_TAIL)] == TEXT_PREAMBLE_TAIL:
            text_start = i + len(TEXT_PREAMBLE_TAIL)
            # Verify it's actually SJIS text
            if text_start < len(data) and (_is_sjis_lead(data[text_start]) or
                                            (0x20 <= data[text_start] <= 0x7e)):
                text_end = _find_text_end(data, text_start)
                if text_end > text_start:
                    preamble_start = _find_preamble_start(data, i)
                    result['text_regions'].append(TextRegion(
                        text_start, text_end,
                        data[text_start:text_end],
                        preamble_start))
                    i = text_end + 1
                    continue
        i += 1

    _find_relative_branches(data, result)
    return result


def _in_text(offset, regions):
    return any(r.preamble_start <= offset <= r.end for r in regions)


def _find_relative_branches(data, result):
    """Record every near call/jmp/jcc (16-bit relative displacement) in the
    handler code and in every subroutine it calls. Their displacements are
    relative, so they need fixing whenever a text region between the branch and
    its target changes size. (D010_X10.BSD crashed because a handler before its
    text did `call 0x0d1e` to code after it, and the call wasn't relocated.)"""
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    regions = result['text_regions']
    queue = [e for e in result['event_table']
             if e < len(data) and data[e:e + 2] == b'']
    seen_starts = set()
    seen_insns = set()
    while queue:
        start = queue.pop()
        if start in seen_starts or start >= len(data) or _in_text(start, regions):
            continue
        seen_starts.add(start)
        for insn in md.disasm(data[start:start + 2048], start):
            if insn.address in seen_insns or _in_text(insn.address, regions):
                break
            seen_insns.add(insn.address)
            raw = data[insn.address:insn.address + insn.size]
            rel = None
            if raw[0] in (0xe8, 0xe9) and insn.size == 3:
                rel = 1                     # call/jmp rel16
            elif raw[0] == 0x0f and 0x80 <= raw[1] <= 0x8f and insn.size == 4:
                rel = 2                     # jcc rel16
            _record_absolute_refs(data, result, insn, raw)
            if rel is not None:
                end = insn.address + insn.size
                target = (end + struct.unpack_from('<h', raw, rel)[0]) & 0xffff
                if target < len(data):
                    result['fixups'].append(Fixup(insn.address + rel, 2, target, 'rel16'))
                    if raw[0] == 0xe8 or raw[0] == 0x0f:
                        queue.append(target)     # the callee / the branch-taken path
                    elif raw[0] == 0xe9:
                        queue.append(target)
                        break                    # unconditional jump: nothing falls through
            elif insn.mnemonic in ('ret', 'retf', 'iret'):
                break
            elif insn.mnemonic == 'jmp':        # short jmp: follow it, nothing falls through
                queue.append(int(insn.op_str, 16) if insn.op_str.startswith('0x') else start)
                break
            elif insn.mnemonic.startswith('j') and insn.op_str.startswith('0x'):
                queue.append(int(insn.op_str, 16))   # short jcc: also scan the taken path


def _record_absolute_refs(data, result, insn, raw):
    """Absolute references to the file's own data in handler code, other than the
    `mov word cs:[x], imm` form parse_bsd already knows. Found in D010_X10.BSD (the
    Mercenary's fight): after its text shrank, the Run handler stored its text
    pointer at the new end of file but the display routine read it back with
    `mov si, cs:[0xd91]` (the old end), and drew garbage. Three kinds:
      - cs_disp:   a cs:-prefixed memory operand's 16-bit address (flags and the
                   end-of-file variable: cs:[0xc77], cs:[0x319], cs:[0xd91])
      - imm_ptr:   `mov si/di/bx, imm16` pointing into the file (mov si, 0x461)
      - table_word: the entries of a word table such a pointer walks, when they're
                   all offsets into the file and it ends in 0xffff (0x461's list of
                   text scripts)
    Values below METADATA_END are left alone: they're small constants, and
    nothing before the first text region moves anyway."""
    known = {f.file_offset for f in result['fixups']}
    limit = len(data) + 0x40            # the end-of-file variable, and a little slack

    def add(at, kind):
        if at in known:
            return
        val = struct.unpack_from('<H', data, at)[0]
        if METADATA_END <= val <= limit:
            result['fixups'].append(Fixup(at, 2, val, kind))
            known.add(at)

    if 0x2e in raw[:4]:                 # cs: segment override
        modrm_at = None
        i = 0
        while i < len(raw) and raw[i] in (0x26, 0x2e, 0x36, 0x3e, 0x66, 0x67, 0xf2, 0xf3):
            i += 1
        op = raw[i] if i < len(raw) else None
        if op == 0x0f:
            i += 1
        elif op in (0xa0, 0xa1, 0xa2, 0xa3):             # mov al/ax <-> moffs16
            add(insn.address + i + 1, 'cs_disp')
            op = None
        if op is not None and i + 1 < len(raw):
            modrm_at = i + 1
            modrm = raw[modrm_at]
            mod, rm = modrm >> 6, modrm & 7
            if (mod == 0 and rm == 6) or mod == 2:          # [disp16] or [reg+disp16]
                add(insn.address + modrm_at + 1, 'cs_disp')
    if 0xbb <= raw[0] <= 0xbf and len(raw) == 3 and raw[0] in (0xbb, 0xbe, 0xbf):
        # mov bx/si/di, imm16
        at = insn.address + 1
        ptr = struct.unpack_from('<H', data, at)[0]
        if METADATA_END <= ptr < len(data):
            add(at, 'imm_ptr')
            words = []
            for k in range(64):
                a = ptr + 2 * k
                if a + 2 > len(data):
                    break
                w = struct.unpack_from('<H', data, a)[0]
                if w == 0xffff:
                    if words and all(METADATA_END <= x < len(data) for _, x in words):
                        for a2, _ in words:
                            add(a2, 'table_word')
                    break
                words.append((a, w))


def compute_shift(original_offset, changes):
    """Compute cumulative byte shift at a given original file offset.

    `changes` is a sorted list of (change_offset, delta) where delta is
    the size change (positive = growth, negative = shrink).
    """
    shift = 0
    for change_off, delta in changes:
        if change_off <= original_offset:
            shift += delta
        else:
            break
    return shift


def reassemble(parsed, replacements=None):
    """Reassemble a BSD file with optional text replacements.

    Args:
        parsed: output of parse_bsd()
        replacements: dict mapping text region index to new bytes
                     (SJIS encoded, WITHOUT null terminator)

    Returns:
        New file bytes with all offsets updated.
    """
    if replacements is None:
        replacements = {}

    data = bytearray(parsed['data'])

    # Build the list of changes (offset, delta) sorted by offset
    changes = []
    for idx, region in enumerate(parsed['text_regions']):
        if idx in replacements:
            new_text = replacements[idx]
            old_len = region.end - region.offset  # original text length (excl null)
            new_len = len(new_text)
            delta = new_len - old_len
            if delta != 0:
                changes.append((region.offset, delta))

    changes.sort(key=lambda x: x[0])

    if not changes and not replacements:
        # Identity transform — return original
        return bytes(data)

    # Rebuild the file by constructing a new byte array
    # We process the original file, inserting/removing bytes at text regions
    output = bytearray()
    src_pos = 0

    # Sort text regions by offset
    text_by_offset = sorted(
        [(idx, r) for idx, r in enumerate(parsed['text_regions'])],
        key=lambda x: x[1].offset)

    for idx, region in text_by_offset:
        # Copy everything up to the text start
        output.extend(data[src_pos:region.offset])

        if idx in replacements:
            # Write replacement text + null terminator
            output.extend(replacements[idx])
        else:
            # Write original text
            output.extend(region.text_bytes)

        # Whatever ended the original text. It is a NUL for 213 of the 215 regions,
        # but C042_X10 ends one with 0x01 and D031_S10's last region runs to the end of
        # the file with no terminator at all - writing a NUL in either case destroys a
        # byte of script (or adds one).
        if region.end < len(data):
            output.append(data[region.end])
        src_pos = region.end + 1  # skip past original text + its terminator

    # Copy remainder
    output.extend(data[src_pos:])

    # Now fix up all absolute references
    new_file_size = len(output)

    for fixup in parsed['fixups']:
        if fixup.kind == 'cs_mov_target':
            # Target address should be new file size
            new_offset = fixup.file_offset + compute_shift(fixup.file_offset, changes)
            struct.pack_into('<H', output, new_offset, new_file_size)
        elif fixup.kind == 'rel16':
            # displacement = target - end of instruction, both of which may have moved
            insn_end = fixup.file_offset + 2
            new_disp_at = fixup.file_offset + compute_shift(fixup.file_offset, changes)
            new_end = insn_end + compute_shift(insn_end, changes)
            new_target = fixup.value + compute_shift(fixup.value, changes)
            struct.pack_into('<h', output, new_disp_at, new_target - new_end)
        else:
            # The fixup location itself may have shifted
            new_fixup_offset = fixup.file_offset + compute_shift(fixup.file_offset, changes)
            # The value it contains should be adjusted
            new_value = fixup.value + compute_shift(fixup.value, changes)
            struct.pack_into('<H', output, new_fixup_offset, new_value)

    return bytes(output)


def reinsert_bsd(data, translations):
    """High-level reinsertion interface for the pipeline.

    Args:
        data: original BSD file bytes
        translations: list of (offset, jp_bytes, en_bytes) tuples
                     where offset is the text start in the original file

    Returns:
        New file bytes with translations applied and offsets relocated.
        Returns original data if no translations apply.
    """
    parsed = parse_bsd(data)

    if not parsed['text_regions'] and not translations:
        return data

    # A text region can hold several workbook rows (e.g. a speaker name, \n, and
    # their line). Replace each row's Japanese at its own position inside the
    # region; rows with no English keep the Japanese. (Replacing the whole region
    # with one row's English dropped D010_X10's first line entirely.)
    replacements = {}
    for idx, region in enumerate(parsed['text_regions']):
        rows = [(off, jp, en) for off, jp, en in translations
                if region.offset - 4 <= off < region.end]
        new = bytearray(region.text_bytes)
        changed = False
        for off, jp, en in sorted(rows, key=lambda r: r[0], reverse=True):
            if not en or en == jp:
                continue
            pos = off - region.offset
            if pos < 0 or bytes(new[pos:pos + len(jp)]) != jp:
                # offset slightly off (preamble boundary): find this row's Japanese
                found = bytes(new).find(jp)
                if found < 0:
                    print(f'WARNING: {jp!r} not found in text region at {region.offset:#x}')
                    continue
                pos = found
            new[pos:pos + len(jp)] = en
            changed = True
        if changed:
            replacements[idx] = bytes(new)

    if not replacements:
        return data

    return reassemble(parsed, replacements)


def dump_info(parsed):
    """Print a human-readable summary of a parsed BSD file."""
    data = parsed['data']
    print(f"File size: {len(data)} bytes (0x{len(data):04x})")
    print(f"Header: {parsed['header'].hex()}")
    magic = parsed['header'] == b'\xb4\x0b\x5c\x99\xd8\x16'
    print(f"  {'Standard magic' if magic else 'Zeroed/non-standard'}")

    print(f"\nResource offsets ({sum(1 for v in parsed['resource_offsets'] if v)} non-zero):")
    for i, val in enumerate(parsed['resource_offsets']):
        if val and val < len(data):
            end = data.find(b'\x00', val, val + 30)
            path = data[val:end] if end > val else b'?'
            print(f"  [{i}] 0x{val:04x} = {path}")
        elif val:
            print(f"  [{i}] 0x{val:04x} (data)")

    push_ds_es = b'\x1e\x06'
    active_count = sum(1 for e in parsed['event_table'] if data[e:e+2] == push_ds_es)
    print(f"\nEvent table ({active_count} active):")
    for i, entry in enumerate(parsed['event_table']):
        if entry >= len(data):
            status = "OUTSIDE"
        elif data[entry:entry + 2] == b'\xcb\x90':
            status = "empty (RETF;NOP)"
        elif data[entry:entry + 2] == b'\x1e\x06':
            status = "active"
        else:
            status = f"unknown ({data[entry:entry+2].hex()})"
        print(f"  [{i:2d}] 0x{entry:04x} {status}")

    print(f"\nFixups ({len(parsed['fixups'])}):")
    for f in sorted(parsed['fixups'], key=lambda x: x.file_offset):
        print(f"  0x{f.file_offset:04x}: {f.kind:20s} = 0x{f.value:04x}")

    print(f"\nText regions ({len(parsed['text_regions'])}):")
    for i, r in enumerate(parsed['text_regions']):
        text = r.text_bytes.decode('shift-jis', errors='replace')
        preview = text[:50] + ('...' if len(text) > 50 else '')
        print(f"  [{i:2d}] 0x{r.offset:04x}-0x{r.end:04x} ({r.end - r.offset:3d}B): {preview}")

    print(f"\nx86 regions ({len(parsed['x86_regions'])}):")
    for start, end in parsed['x86_regions']:
        print(f"  0x{start:04x}-0x{end - 1:04x} ({end - start} bytes)")


if __name__ == '__main__':
    import sys

    decomp_dir = 'original/decompressed'
    bsd_files = sorted(f for f in os.listdir(decomp_dir) if f.endswith('.BSD'))

    # Round-trip test: parse and reassemble with no changes
    print("=== Round-trip identity test (all BSD files) ===")
    pass_count = 0
    fail_count = 0
    fail_files = []

    for fname in bsd_files:
        path = os.path.join(decomp_dir, fname)
        data = open(path, 'rb').read()
        parsed = parse_bsd(data)
        rebuilt = reassemble(parsed)
        if rebuilt == data:
            pass_count += 1
        else:
            fail_count += 1
            fail_files.append(fname)
            if fail_count <= 5:
                # Show first difference
                for i in range(min(len(rebuilt), len(data))):
                    if rebuilt[i] != data[i]:
                        print(f"  FAIL {fname}: first diff at 0x{i:04x} "
                              f"(orig=0x{data[i]:02x}, rebuilt=0x{rebuilt[i]:02x})")
                        break
                if len(rebuilt) != len(data):
                    print(f"  FAIL {fname}: size mismatch "
                          f"(orig={len(data)}, rebuilt={len(rebuilt)})")

    print(f"\nResults: {pass_count}/{pass_count + fail_count} files pass identity round-trip")
    if fail_files:
        print(f"Failed: {fail_files[:10]}")

    if fail_count == 0:
        # Expansion test on D010_X10.BSD
        print("\n=== Text expansion test (D010_X10.BSD) ===")
        data = open(os.path.join(decomp_dir, 'D010_X10.BSD'), 'rb').read()
        parsed = parse_bsd(data)

        dump_info(parsed)

        # Replace first text with something longer
        if parsed['text_regions']:
            orig_text = parsed['text_regions'][0].text_bytes
            # Add 10 extra bytes
            new_text = orig_text + b'          '
            rebuilt = reassemble(parsed, {0: new_text})
            print(f"\nOriginal size: {len(data)}, Rebuilt size: {len(rebuilt)}")
            print(f"Delta: +{len(rebuilt) - len(data)} bytes")

            # Verify the new text is present
            if new_text in rebuilt:
                print("New text found in rebuilt file: OK")
            else:
                print("ERROR: New text NOT found in rebuilt file!")

            # Re-parse the rebuilt file and verify structure
            reparsed = parse_bsd(rebuilt)
            print(f"Re-parsed text regions: {len(reparsed['text_regions'])}")
            print(f"Re-parsed fixups: {len(reparsed['fixups'])}")

            # Check that all event table entries still point to valid handlers
            for i, entry in enumerate(reparsed['event_table']):
                if entry < len(rebuilt) and rebuilt[entry:entry + 2] not in (b'\xcb\x90', b'\x1e\x06'):
                    print(f"WARNING: Event [{i}] at 0x{entry:04x} has unexpected bytes: {rebuilt[entry:entry+2].hex()}")
