"""
    
"""

import regex as re
import os
from collections import OrderedDict
from romtools.dump import BorlandPointer, PointerExcel
from romtools.disk import Gamefile

from rominfo import POINTER_CONSTANT, FILES_WITH_POINTERS, FILE_BLOCKS, POINTERS_TO_SKIP, CONTROL_CODES
from rominfo import ZERO_POINTER_FIRST_BYTES

# POINTER_CONSTANT is the line where "Borland Compiler" appears, rounded down to the nearest 0x10.

pointer_regex = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])'
bd_pointer_regex = r'\\x08\\x([0-f][0-f])\\x([0-f][0-f])\\x00'
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

def capture_pointers_from_function(regex, hx): 
    return re.compile(regex).finditer(hx, overlapped=True)

def location_from_pointer(pointer, constant):
    return '0x' + str(format((unpack(pointer[0], pointer[1]) + constant), '05x'))

def unpack(s, t=None):
    if t is None:
        t = str(s)[2:]
        s = str(s)[0:2]
    s = int(s, 16)
    t = int(t, 16)
    value = (t * 0x100) + s
    return value

pointer_count = 0

try:
    os.remove('KuroNoKen_pointer_dump.xlsx')
except FileNotFoundError:
    pass

PtrXl = PointerExcel('KuroNoKen_pointer_dump.xlsx')

for gamefile in FILES_WITH_POINTERS:
    print(gamefile)
    pointer_locations = OrderedDict()
    gamefile_path = os.path.join('original', 'decompressed', gamefile)
    GF = Gamefile(gamefile_path, pointer_constant=POINTER_CONSTANT[gamefile])
    with open(gamefile_path, 'rb') as f:
        bs = f.read()
        target_areas = FILE_BLOCKS[gamefile]
        #print(target_areas)
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
            relevant_regexes = [pointer_regex, bd_pointer_regex]
        elif gamefile.endswith('.SCN'):
            relevant_regexes = [scn_inner_pointer_regex_0, 
                               scn_inner_pointer_regex_1, scn_inner_pointer_regex_4, scn_inner_pointer_regex_9,
                               scn_inner_pointer_regex_ff, scn_inner_pointer_regex_892a, scn_inner_pointer_regex_892c]
        elif gamefile.endswith(".BSD"):
            relevant_regexes = [bsd_pointer_regex_c6_first, bsd_pointer_regex_c6_second,
                bsd_pointer_regex_c7_first, bsd_pointer_regex_c7_second]
        else:
            relevant_regexes = [pointer_regex,]

        for relevant_regex in relevant_regexes:
            print("Using", relevant_regex)
            pointers = capture_pointers_from_function(relevant_regex, only_hex)

            for p in pointers:
                #print(p)
                if relevant_regex == pointer_regex:
                    pointer_location = p.start()//4 + 1
                elif relevant_regex == bd_pointer_regex:
                    pointer_location = p.start()//4 + 1
                elif relevant_regex == item_pointer_regex:
                    pointer_location = p.start()//4 + 7
                elif relevant_regex == item_pointer_regex_9c:
                    pointer_location = p.start()//4 + 6
                elif relevant_regex == item_pointer_regex_ba:
                    pointer_location = p.start()//4 + 1
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
                    else:
                        text_location = int(location_from_pointer((p.group(1), p.group(2)), GF.pointer_constant), 16)
                except ValueError:
                    #print("Bad value")
                    continue
                print(pointer_location, hex(text_location))

                if all([not t[0] <= text_location<= t[1] for t in target_areas]):
                    print("It's not in any of the blocks, so skipping it")
                    continue
                #print("It was in a block")

                if (gamefile, text_location) in POINTERS_TO_SKIP:
                    print("Skipping this one")
                    continue

                if relevant_regex == scn_inner_pointer_regex_0:
                    print(p.group(1))
                    if int(p.group(1), 16) not in ZERO_POINTER_FIRST_BYTES:
                        print("Not a proper zero pointer first byte")
                        continue

                #if gamefile.endswith('.SCN') and any([t[0] <= int(pointer_location, 16) <= t[1] for t in target_areas]):
                #    print("That pointer is probably just a text control code, skipping it")
                #    continue

                all_locations = [int(pointer_location, 16),]

                #print(pointer_locations)

                if (GF, text_location) in pointer_locations:
                    all_locations = pointer_locations[(GF, text_location)]
                    if int(pointer_location, 16) not in all_locations:
                        all_locations.append(int(pointer_location, 16))
                    print(all_locations)
                    #print("More than one pointer to this location")

                print(pointer_location, hex(text_location))
                pointer_locations[(GF, text_location)] = all_locations
                #print(pointer_locations[(GF, text_location)])
                #print((GF, text_location) in pointer_locations)

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

    # Setup the worksheet for this file
    worksheet = PtrXl.add_worksheet(GF.filename)

    row = 1

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