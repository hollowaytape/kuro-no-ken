from collections import OrderedDict
from romtools.dump import pack, unpack

# Need to find out what those pointer prefixes mean.
# They point to a particular function to call... need to figure out which ones of those start with lodsb es: (26ac).
# Those are pointers.

with open('original/decompressed/BD.BIN', 'rb') as f:
    contents = f.read()

byte_to_function_offset_table = contents[0x22d0:0x24d0]
byte_function_offsets = OrderedDict()
i = 0
while i <= 0xff:
    first = hex(byte_to_function_offset_table[i*2])
    second = hex(byte_to_function_offset_table[(i*2)+1])
    #print(first, second)
    function_offset = unpack(first, second)
    #print(hex(i), hex(function_offset))
    byte_function_offsets[i] = function_offset
    i += 1


for b in byte_function_offsets:
    offset = byte_function_offsets[b]
    #print(hex(b), hex(byte_function_offsets[b]), contents[offset:offset+10])

    # TODO: Now to translate function calls into the location they're at.
    # offset is 2aa4, function call bytes are e811ed, destination is 17b8.
    # e8 is "call"
    # ed11 = offset from something? 
            # ffff - ed11 = 12ee
            # 17b8 + 12ee = 2aa6 (offset of hte last byte in the function call)
    #print(contents[offset])
    if contents[offset] == 0xe8:
        base = offset + 2

        first = hex(contents[offset+1])
        second = hex(contents[offset+2])

        call_offset = unpack(first, second)
        call_destination = base - (0xffff - call_offset)
        #print(hex(base), hex(call_offset), hex(call_destination))

        #print(contents[call_destination:call_destination+10])
        called_func = contents[call_destination:call_destination+50]
        called_func = called_func.split(b'\xc3')[0]  # c3 is "ret", so go to the end of the function
        #print(called_func)
        if b'\x26\xac' in called_func:
            print(hex(b), hex(offset),  "is a pointer")
        else:
            print(hex(b), hex(offset))

    else:
        print(hex(b), hex(offset))
