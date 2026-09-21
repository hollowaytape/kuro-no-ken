"""
    Find pointers and write them to KuroNoKen_pointer_dump.xlsx.

    python find_pointers.py               regenerate every file in FILES_WITH_POINTERS
    python find_pointers.py A.SCN B.SCN   regenerate only those sheets, keeping the rest
"""

import regex as re
import os
import sys
from openpyxl import load_workbook
from collections import OrderedDict
from romtools.dump import BorlandPointer, PointerExcel
from romtools.disk import Gamefile

from rominfo import POINTER_CONSTANT, FILES_WITH_POINTERS, FILE_BLOCKS, FILE_STRING_LOCATIONS, POINTERS_TO_SKIP, POINTERS_TO_ADD, CONTROL_CODES
from rominfo import ZERO_POINTER_FIRST_BYTES

# POINTER_CONSTANT is the line where "Borland Compiler" appears, rounded down to the nearest 0x10.

pointer_regex = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])'
bd_pointer_regex_4 = r'\\x04\\x([0-f][0-f])\\x([0-f][0-f])\\x00'
bd_pointer_regex_5 = r'\\x05\\x([0-f][0-f])\\x([0-f][0-f])\\x00'
bd_pointer_regex_8 = r'\\x08\\x([0-f][0-f])\\x([0-f][0-f])\\x00'
#scn_pointer_regex = r'\\x09\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_0 = r'\\x([0-f][0-f])\\x00\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_1 = r'\\x01\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_4 = r'\\x04\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_9 = r'\\x09\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_ff = r'\\xff\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_892a = r'\\x89\\x2a\\x([0-f][0-f])\\x([0-f][0-f])'
scn_inner_pointer_regex_892c = r'\\x89\\x2c\\x([0-f][0-f])\\x([0-f][0-f])'
item_pointer_regex = r'\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
item_pointer_regex_9c = r'\\x9c\\x9c\\x9c\\x9c\\x9c\\x9c\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
item_pointer_regex_ba = r'\\x00\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\xff\\xff'

bsd_pointer_regex_c6_first = r'\\xc6\\x06\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
bsd_pointer_regex_c6_second = r'\\xc6\\x06\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
bsd_pointer_regex_c7_first = r'\\xc7\\x06\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'
bsd_pointer_regex_c7_second = r'\\xc7\\x06\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'

pointer_table = r''

# Opt-in "range scan" for words that look like addresses into a file's own text.
# DISABLED: it looked right for 02OLB02.SCN, but its hits there were variable/flag
# IDs (0x1e89, 0x2007, ...) that happen to fall in the same numeric range, not
# addresses; several pointed into the middle of a two-byte character. Changing them
# soft-locked the game. Numbers this large DO occur in the scripts, so pointers
# can't be told from values by range; that needs the script format decoded.
# `python find_pointers.py --scan-report` lists candidates for every file instead.
RANGE_SCAN_FILES = set()     # none yet: see the note below

_SPANS = None


def _text_spans(gamefile):
    """(start, end) byte ranges of every Japanese string the dump workbook knows
    in this file, so the range scan never reads text bytes as a pointer."""
    global _SPANS
    if _SPANS is None:
        from rominfo import DUMP_XLS_PATH
        _SPANS = {}
        wb = load_workbook(DUMP_XLS_PATH, read_only=True)
        for sheet in ('SCNs', 'BSDs'):
            for row in wb[sheet].iter_rows(min_row=2, values_only=True):
                fn, off, jp = row[0], row[1], row[2]
                if fn and isinstance(off, str) and off.startswith('0x') and isinstance(jp, str):
                    start = int(off, 16)
                    _SPANS.setdefault(fn, []).append((start, start + len(jp.encode('cp932', 'replace'))))
    return _SPANS.get(gamefile, [])


def capture_pointers_from_function(regex, hx): 
    return re.compile(regex).finditer(hx, overlapped=True)

def location_from_pointer(pointer, constant):
    try:
        result = '0x' + str(format((unpack(pointer[0], pointer[1]) + constant), '05x'))
    except:
        result = '0x' + str(format((unpack(hex(pointer[0]), hex(pointer[1])) + constant), '05x'))
    return result

def unpack(s, t=None):
    if t is None:
        t = str(s)[2:]
        s = str(s)[0:2]
    s = int(s, 16)
    t = int(t, 16)
    value = (t * 0x100) + s
    return value

def merge_sheets(src_path, dest_path):
    """Replace dest's sheets with src's same-named sheets (values only)."""
    src = load_workbook(src_path)
    dest = load_workbook(dest_path)
    for ws in src.worksheets:
        if ws.title in dest.sheetnames:
            del dest[ws.title]
        new_ws = dest.create_sheet(ws.title)
        for row in ws.iter_rows(values_only=True):
            new_ws.append(row)
    dest.save(dest_path)

pointer_count = 0

POINTER_DUMP_PATH = 'KuroNoKen_pointer_dump.xlsx'
target_files = sys.argv[1:] or FILES_WITH_POINTERS
for f in target_files:
    assert f in FILES_WITH_POINTERS, '%s is not in FILES_WITH_POINTERS' % f
out_path = POINTER_DUMP_PATH if not sys.argv[1:] else 'KuroNoKen_pointer_dump_partial.xlsx'

try:
    os.remove(out_path)
except FileNotFoundError:
    pass

PtrXl = PointerExcel(out_path)

for gamefile in target_files:
    print(gamefile)
    pointer_locations = OrderedDict()
    gamefile_path = os.path.join('original', 'decompressed', gamefile)
    GF = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gamefile])
    with open(gamefile_path, 'rb') as f:
        bs = f.read()
        target_areas = FILE_BLOCKS[gamefile]
        if gamefile.endswith(".BSD"):
            target_areas = [(0x0, len(GF.filestring)+1)]

        string_locations = []
        if gamefile in FILE_STRING_LOCATIONS:
            string_locations = FILE_STRING_LOCATIONS[gamefile]

        if os.environ.get('KURO_VERBOSE'):
            print(target_areas)
        # target_area = (GF.pointer_constant, len(bs))
        #print(hex(target_area[0]), hex(target_area[1]))

        only_hex = u""
        for c in bs:
            only_hex += u'\\x%02x' % c

        #print(only_hex)
        if gamefile.endswith('SMI'):
            relevant_regexes = [item_pointer_regex, item_pointer_regex_9c,
                               item_pointer_regex_ba]
        elif gamefile.endswith('.BIN'):
            relevant_regexes = [pointer_regex, bd_pointer_regex_4, bd_pointer_regex_5, bd_pointer_regex_8]
        elif gamefile.endswith('.SCN'):
            relevant_regexes = [scn_inner_pointer_regex_0, 
                               scn_inner_pointer_regex_1, scn_inner_pointer_regex_4, scn_inner_pointer_regex_9,
                               scn_inner_pointer_regex_ff, scn_inner_pointer_regex_892a, scn_inner_pointer_regex_892c]
        elif gamefile.endswith(".BSD"):
            relevant_regexes = [bsd_pointer_regex_c6_first, bsd_pointer_regex_c6_second,
                bsd_pointer_regex_c7_first, bsd_pointer_regex_c7_second,
                pointer_table]
        else:
            relevant_regexes = [pointer_regex,]

        for relevant_regex in relevant_regexes:
            print("Using", relevant_regex)

            if relevant_regex == pointer_table:
                pointers = range(0x12, 0x32, 0x2)
            else:
                pointers = capture_pointers_from_function(relevant_regex, only_hex)

            for p in pointers:
                # Handle all cases where the pointer signature begins is more than 1 byte long
                if relevant_regex == item_pointer_regex:
                    pointer_location = p.start()//4 + 7
                elif relevant_regex == item_pointer_regex_9c:
                    pointer_location = p.start()//4 + 6
                elif relevant_regex == scn_inner_pointer_regex_0:
                    pointer_location = p.start()//4 + 2
                elif relevant_regex == scn_inner_pointer_regex_892a:
                    pointer_location = p.start()//4 + 2
                elif relevant_regex == scn_inner_pointer_regex_892c:
                    pointer_location = p.start()//4 + 2
                elif relevant_regex in (bsd_pointer_regex_c6_first, bsd_pointer_regex_c7_first):
                    pointer_location = p.start()//4 + 2
                elif relevant_regex in (bsd_pointer_regex_c6_second, bsd_pointer_regex_c7_second):
                    pointer_location = p.start()//4 + 4
                elif relevant_regex == pointer_table:
                    pointer_location = p
                else:
                    pointer_location = p.start()//4 + 1

                pointer_location = '0x%05x' % pointer_location
                #print("looking at ", pointer_location)
                try:
                    # SIPR0 begins with an extra group, so need different indices
                    if relevant_regex == scn_inner_pointer_regex_0:
                        text_location = int(location_from_pointer((p.group(2), p.group(3)), GF.pointer_constant), 16)
                    elif relevant_regex in (bsd_pointer_regex_c6_second, bsd_pointer_regex_c7_second):
                        text_location = int(location_from_pointer((p.group(3), p.group(4)), GF.pointer_constant), 16)
                    elif relevant_regex == pointer_table:
                        print(hex(p), bs[p], bs[p+1])
                        text_location = int(location_from_pointer((bs[p], bs[p+1]), GF.pointer_constant), 16)
                    else:
                        text_location = int(location_from_pointer((p.group(1), p.group(2)), GF.pointer_constant), 16)
                except ValueError:
                    #print("Bad value")
                    continue
                print(pointer_location, hex(text_location))

                if all([not t[0] <= text_location <= t[1] for t in target_areas]):
                    print("It's not in any of the blocks, so skipping it")
                    continue

                if any([t[0] <= pointer_location <= t[1] for t in string_locations]):
                    print("It's in the middle of real text, so skipping it")
                    continue

                if (gamefile, text_location) in POINTERS_TO_SKIP or (gamefile, int(pointer_location, 16), 'pointer_location') in POINTERS_TO_SKIP:
                    print("Skipping this one")
                    continue

                if relevant_regex == scn_inner_pointer_regex_0:
                    print(p.group(1))
                    if int(p.group(1), 16) not in ZERO_POINTER_FIRST_BYTES:
                        print("Not a proper zero pointer first byte")
                        continue

                all_locations = [int(pointer_location, 16),]

                if (GF, text_location) in pointer_locations:
                    all_locations = pointer_locations[(GF, text_location)]
                    if int(pointer_location, 16) not in all_locations:
                        all_locations.append(int(pointer_location, 16))
                    print(all_locations)
                    #print("More than one pointer to this location")

                print(pointer_location, hex(text_location))
                pointer_locations[(GF, text_location)] = all_locations

                if relevant_regex in [item_pointer_regex, item_pointer_regex_ba, item_pointer_regex_9c]:

                    # Item pointer regex also includes pointer to that item's description. Add it too
                    if relevant_regex == item_pointer_regex:
                        pointer_location = p.start()//4 + 9
                    elif relevant_regex == item_pointer_regex_9c:
                        pointer_location = p.start()//4 + 8
                    elif relevant_regex == item_pointer_regex_ba:
                        pointer_location = p.start()//4 + 3

                    pointer_location = '0x%05x' % pointer_location
                    text_location = int(location_from_pointer((p.group(3), p.group(4)), GF.pointer_constant), 16)
                    all_locations = [int(pointer_location, 16),]
                    if (GF, text_location) in pointer_locations:
                        all_locations = pointer_locations[(GF, text_location)]
                        if int(pointer_location, 16) not in all_locations:
                            all_locations.append(int(pointer_location, 16))
                    pointer_locations[(GF, text_location)] = all_locations

        # Range scan for scripts loaded at 26d8:1800 or 26d8:3d00: the byte patterns
        # above are an opcode allow-list, and script opcodes 02/07/83/88 and most
        # "xx 00 <ptr>" forms weren't on it, so e.g. 02OLB02.SCN's town-entry script
        # jumped to 0x807 after the text grew and the game exited to DOS. For these
        # slots a stored address into the file's own text block is >= 0x1800 +
        # (first text offset), far above any count/coordinate/flag the scripts use,
        # so every such word outside the strings themselves is taken as a pointer.
        # 03YSK01A.SCN is excluded for now: the scan's hits there include an
        # 'xx 00 <word> 1d 6f' table, and with them a text edit at 0xbf9 lands on the
        # wrong bytes. Its regex-found pointers pass every playtest so far.
        # Only for files whose hits have been checked in play (see RANGE_SCAN_FILES).
        if gamefile in RANGE_SCAN_FILES and -GF.pointer_constant >= 0x1800:
            spans = _text_spans(gamefile)
            base = -GF.pointer_constant
            first_text = min((a for a, b in spans), default=0)
            for i in range(1, len(bs) - 1):
                if any(a <= i < b or a <= i + 1 < b for a, b in spans):
                    continue
                # Precision guards (a false positive corrupts code or text):
                #  - the byte before must be an opcode seen taking an address (02 07 1b
                #    83 88 89 in 02OLB02.SCN, all confirmed by the Albein exit) or the 00 of
                #    the "xx 00 <addr>" form, or the word before must itself be an address
                #    into this file (address pairs: "81 1b 07 20" = 0x1b81, 0x2007);
                #  - the value's low byte isn't 00: "00 22" / "00 2a" runs are data
                #    tables (03YSK01A 0xaf4, 0xb05, 0xb23);
                #  - the target is at or after the file's first text.
                prev_word = (bs[i - 2] | (bs[i - 1] << 8)) if i >= 2 else 0
                prev_is_addr = base <= prev_word < base + len(bs)     # address pairs (if/else targets)
                if (bs[i - 1] not in (0x00, 0x02, 0x07, 0x1b, 0x83, 0x88, 0x89) and not prev_is_addr)                         or bs[i] == 0x00:
                    continue
                if bs[i + 1] == 0x40 and i + 2 < len(bs) and bs[i + 2] == 0x02:
                    # "xx 40 02" is the tail of a text control code's render sync
                    # (\n 00 40 02, \f 00 3b 40 02, [New] ... 30 40 02); for scripts at
                    # 0x3d00 its 0x40xx value looks like a pointer into the text
                    continue
                value = bs[i] | (bs[i + 1] << 8)
                text_location = value - base
                if text_location < first_text or all(not t[0] <= text_location <= t[1] for t in target_areas):
                    continue
                if (gamefile, text_location) in POINTERS_TO_SKIP or (gamefile, i, 'pointer_location') in POINTERS_TO_SKIP:
                    continue
                locs = pointer_locations.setdefault((GF, text_location), [])
                if i not in locs:
                    locs.append(i)
                    print('range scan: %#05x -> %#05x' % (i, text_location))

    # A real script pointer never targets the middle of a string. Those that do are
    # values that happen to look like pointers (02OLB02.SCN's "00 89 1e" is a variable
    # ID, and "relocating" it made the game exit to DOS); drop them.
    spans = _text_spans(gamefile)
    for key in [k for k in pointer_locations if any(a < k[1] < b for a, b in spans)]:
        print('dropping "pointer(s)" into the middle of a string: %s -> %#05x' % (pointer_locations[key], key[1]))
        del pointer_locations[key]

    # Setup the worksheet for this file
    worksheet = PtrXl.add_worksheet(GF.filename)

    row = 1

    for pta in POINTERS_TO_ADD:
        filename, pointer_location, text_location = pta
        if filename == gamefile:
            print("Adding a manually defined pointer:", pta)
            if (GF, text_location) in pointer_locations:
                pointer_locations[(GF, text_location)].append(pointer_location)
            else:
                pointer_locations[(GF, text_location)] = [pointer_location,]

    for (gamefile, text_location), pointer_locations in sorted((pointer_locations).items()):
        obj = BorlandPointer(gamefile, pointer_locations, text_location, separator=b'\f')
        #print(text_location)
        #print(pointer_locations)
        for pointer_loc in pointer_locations:
            worksheet.write(row, 0, hex(text_location))
            worksheet.write(row, 1, hex(pointer_loc))
            worksheet.write(row, 2, obj.value)
            try:
                worksheet.write(row, 3, obj.text(CONTROL_CODES))
            except:
                worksheet.write(row, 3, u'')

            row += 1

PtrXl.close()

if out_path != POINTER_DUMP_PATH:
    merge_sheets(out_path, POINTER_DUMP_PATH)
    os.remove(out_path)
    print('Merged sheets %s into %s' % (target_files, POINTER_DUMP_PATH))