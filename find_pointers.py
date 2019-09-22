"""
    
"""

import re
import os
from collections import OrderedDict
from romtools.dump import BorlandPointer, PointerExcel
from romtools.disk import Gamefile

from rominfo import POINTER_CONSTANT, FILES_WITH_POINTERS, FILE_BLOCKS

# POINTER_CONSTANT is the line where "Borland Compiler" appears, rounded down to the nearest 0x10.

pointer_regex = r'\\xbe\\x([0-f][0-f])\\x([0-f][0-f])'
bd_pointer_regex = r'\\x08\\x([0-f][0-f])\\x([0-f][0-f])\\x00'
scn_pointer_regex = r'\\x09\\x([0-f][0-f])\\x([0-f][0-f])'
item_pointer_regex = r'\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])\\x([0-f][0-f])'

def capture_pointers_from_function(regex, hx): 
    return re.compile(regex).finditer(hx)

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
            relevant_regexes = [item_pointer_regex,]
        elif gamefile.endswith('.BIN'):
            relevant_regexes = [pointer_regex, bd_pointer_regex]
        elif gamefile.endswith('.SCN'):
            relevant_regexes = [scn_pointer_regex,]
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
                elif relevant_regex == scn_pointer_regex:
                    pointer_location = p.start()//4 + 1

                pointer_location = '0x%05x' % pointer_location
                try:
                    text_location = int(location_from_pointer((p.group(1), p.group(2)), GF.pointer_constant), 16)
                except ValueError:
                    print("Bad value")
                    continue
                print(pointer_location, hex(text_location))

                if all([not t[0] <= text_location<= t[1] for t in target_areas]):
                    print("It's not in any of the blocks, so skipping it")
                    continue
                #print("It was in a block")

                if gamefile.endswith('.SCN') and any([t[0] <= int(pointer_location, 16) <= t[1] for t in target_areas]):
                    print("That pointer is probably just a text control code, skipping it")
                    continue

                all_locations = [int(pointer_location, 16),]

                #print(pointer_locations)

                if (GF, text_location) in pointer_locations:
                    all_locations = pointer_locations[(GF, text_location)]
                    all_locations.append(int(pointer_location, 16))
                    #print("More than one pointer to this location")

                print(pointer_location, hex(text_location))
                pointer_locations[(GF, text_location)] = all_locations
                #print(pointer_locations[(GF, text_location)])
                #print((GF, text_location) in pointer_locations)

                if relevant_regex == item_pointer_regex:
                    # Item pointer regex also includes pointer to that item's description. Add it too
                    pointer_location = p.start()//4 + 9
                    pointer_location = '0x%05x' % pointer_location
                    text_location = int(location_from_pointer((p.group(3), p.group(4)), GF.pointer_constant), 16)
                    all_locations = [int(pointer_location, 16),]
                    if (GF, text_location) in pointer_locations:
                        all_locations = pointer_locations[(GF, text_location)]
                        all_locations.append(int(pointer_location, 16))
                    pointer_locations[(GF, text_location)] = all_locations

    # Setup the worksheet for this file
    worksheet = PtrXl.add_worksheet(GF.filename)

    row = 1

    for (gamefile, text_location), pointer_locations in sorted((pointer_locations).items()):
        obj = BorlandPointer(gamefile, pointer_locations, text_location)
        #print(text_location)
        #print(pointer_locations)
        for pointer_loc in pointer_locations:
            worksheet.write(row, 0, hex(text_location))
            worksheet.write(row, 1, hex(pointer_loc))
            try:
                worksheet.write(row, 2, obj.text())
            except:
                worksheet.write(row, 2, u'')
            row += 1

PtrXl.close()