"""
    Dumps text from decompressed files in Kuro no Ken.
"""
import datetime
import sys
import os
import xlsxwriter
from shutil import copyfile
from rominfo import FILE_BLOCKS, FILES_TO_DUMP, ORIGINAL_ROM_DIR, DUMP_XLS_PATH

COMPILER_MESSAGES = [b'Turbo', b'Borland', b'C++', b'Library', b'Copyright']

ASCII_MODE = 2
# 0 = none
# 1: punctuation and c format strings only (not implemented)
# 2: All ascii

THRESHOLD = 4


def dump(files):
    worksheet = workbook.add_worksheet('SCNs')
    worksheet.write(0, 0, 'Filename', header)
    worksheet.write(0, 1, 'Offset', header)
    worksheet.write(0, 2, 'Japanese', header)
    worksheet.write(0, 3, 'JP_len', header)
    worksheet.write(0, 4, 'English', header)
    worksheet.write(0, 5, 'EN_len', header)
    worksheet.write(0, 6, 'Comments', header)

    worksheet.set_column('A:A', 10)
    worksheet.set_column('B:B', 8)
    worksheet.set_column('C:C', 60)
    worksheet.set_column('D:D', 5)
    worksheet.set_column('E:E', 60)
    worksheet.set_column('F:F', 5)
    worksheet.set_column('G:G', 60)
    scn_row = 1

    for filename in FILES_TO_DUMP:
        clean_filename = filename

        if clean_filename.endswith('.SCN'):
            worksheet = workbook.get_worksheet_by_name('SCNs')
        else:
            # Create a new sheet
            worksheet = workbook.add_worksheet(clean_filename)
            worksheet.write(0, 0, 'Offset', header)
            worksheet.write(0, 1, 'Japanese', header)
            worksheet.write(0, 2, 'JP_len', header)
            worksheet.write(0, 3, 'English', header)
            worksheet.write(0, 4, 'EN_len', header)
            worksheet.write(0, 5, 'Comments', header)

            worksheet.set_column('A:A', 8)
            worksheet.set_column('B:B', 60)
            worksheet.set_column('C:C', 5)
            worksheet.set_column('D:D', 60)
            worksheet.set_column('E:E', 5)
            worksheet.set_column('F:F', 60)

        row = 1
        if filename in FILE_BLOCKS:
            blocks = FILE_BLOCKS[filename]
        else:
            # The whole file is a block
            blocks = [(0, 0xfffff)]

        if filename.endswith('BIN'):
            ASCII_MODE = 2
        else:
            ASCII_MODE = 0


        src_filepath = os.path.join(ORIGINAL_ROM_DIR, 'decompressed', filename)

        #if filename not in UNCOMPRESSED_FILES:
        #    src_filepath = 'original/decompressed/%s.decompressed' % filename
        #else:
        #    src_filepath = 'original/%s' % filename

        with open(os.path.join(src_filepath), 'rb') as f:
            contents = f.read()

            cursor = 0
            sjis_buffer = b""
            sjis_buffer_start = 0
            sjis_strings = []

            for c in COMPILER_MESSAGES:
                print(c)
                if c in contents:
                    #print(contents)
                    cursor = contents.index(c)
                    sjis_buffer_start = contents.index(c)
                    break

            for (start, stop) in blocks:
                print((hex(start), hex(stop)))
                cursor = start
                sjis_buffer_start = cursor

                while cursor <= stop:
                    # First byte of SJIS text. Read the next one, too
                    try:
                        if 0x80 <= contents[cursor] <= 0x9f or 0xe0 <= contents[cursor] <= 0xef:

                            # Weird KNK halfwidth kana
                            if contents[cursor] == 0x85:
                                #print("It's kana")
                                cursor += 1
                                buf = contents[cursor]
                                # Digits
                                #print(sjis_buffer)
                                if 0x50 <= buf <= 0x58:
                                    sjis_buffer += (contents[cursor] - 0x1f).to_bytes(1, byteorder='little')
                                # Halfwidth kana
                                else:
                                    try:
                                        sjis_buffer += (contents[cursor] + 2).to_bytes(1, byteorder='little')
                                    except OverflowError:
                                        print("Integer overflow, the halfwidth kana is probably garbage")
                                        sjis_buffer += (contents[cursor]).to_bytes(1, byteorder='little')
                                #sjis_buffer += (contents[cursor] + 2).to_bytes(1, byteorder='little')
                            else:
                                sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')
                                cursor += 1
                                sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        # Halfwidth katakana
                        elif 0xa1 <= contents[cursor] <= 0xdf:
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        # ASCII text
                        elif 0x20 <=contents[cursor] <= 0x7e and ASCII_MODE in (1, 2):
                            sjis_buffer += contents[cursor].to_bytes(1, byteorder='little')

                        # C string formatting with %
                        #elif contents[cursor] == 0x25:
                        #    #sjis_buffer += b'%'
                        #    cursor += 1
                        #    if contents[cursor]

                        # End of continuous SJIS string, so add the buffer to the strings and reset buffer
                        else:
                            sjis_strings.append((sjis_buffer_start, sjis_buffer, clean_filename))
                            sjis_buffer = b""
                            sjis_buffer_start = cursor+1
                        cursor += 1
                        #print(sjis_buffer)
                    except IndexError:
                        break

                # Catch anything left after exiting the loop
                if sjis_buffer:
                    sjis_strings.append((sjis_buffer_start, sjis_buffer, clean_filename))
                    sjis_buffer = b''


            if len(sjis_strings) == 0:
                continue

            for s in sjis_strings:
                #print(s)
                # Remove leading U's
                while s[1].startswith(b'U'):
                    s = (s[0] + 1, s[1][1:], s[2])
                    #s[1] = s[1][1:]
                    #s[0] += 1

                s = (s[0], s[1].rstrip(b'U'), s[2])

                if s[1].startswith(b'='):
                    s = (s[0], s[1].replace(b'=', b'[=]'), s[2])

                if len(s[1]) < THRESHOLD:
                    continue

                loc = '0x' + hex(s[0]).lstrip('0x').zfill(5)
                try:
                    jp = s[1].decode('shift-jis')
                except UnicodeDecodeError:
                    print("Couldn't decode that")
                    continue

                filename = s[2]

                if len(jp.strip()) == 0:
                    continue
                print(loc, jp)

                if clean_filename.endswith('SCN'):
                    worksheet.write(scn_row, 0, filename)
                    worksheet.write(scn_row, 1, loc)
                    worksheet.write(scn_row, 2, jp)
                    worksheet.write(scn_row, 3, '=LEN(C%s)' % str(scn_row+1))
                    worksheet.write(scn_row, 5, '=LEN(E%s)' % str(scn_row+1))
                    scn_row += 1
                else:
                    worksheet.write(row, 0, loc)
                    worksheet.write(row, 1, jp)
                    worksheet.write(row, 2, '=LEN(B%s)' % str(row+1))
                    worksheet.write(row, 4, '=LEN(D%s)' % str(row+1))
                    row += 1

    workbook.close()

if __name__ == '__main__':
    #backup_filename = DUMP_XLS_PATH.replace('.xlsx', '_backup_%s.xlsx' % datetime.datetime.now().strftime('%d/%m/%y_%H:%M'))
    backup_filename = DUMP_XLS_PATH.replace('.xlsx', '_backup.xlsx')
    print(DUMP_XLS_PATH)
    print(backup_filename)
    copyfile(DUMP_XLS_PATH, backup_filename)
    workbook = xlsxwriter.Workbook(DUMP_XLS_PATH)
    header = workbook.add_format({'bold': True, 'align': 'center', 'bottom': True, 'bg_color': 'gray'})
    #FILES = [f for f in os.listdir('patched') if os.path.isfile(os.path.join('patched', f))]
    #FILES = ['IDS.decompressed', 'IS2.decompressed']
    print(FILES_TO_DUMP)
    dump(FILES_TO_DUMP)

    #find_blocks('patched/IDS.decompressed')
