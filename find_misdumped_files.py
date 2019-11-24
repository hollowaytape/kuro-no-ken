"""
    Dumps a file from a memory dump with the given name and start location.
"""

from rominfo import FILES

headers = {}

if __name__ == "__main__":
    for bodfile in FILES:
        name = bodfile.name.decode('ascii')

        if name.endswith(".SCN"):
            #print(name)
            with open('original/decompressed/%s' % name, 'rb') as g:
                header = g.read(500)

                if header in headers:
                    print("%s is a duplicate of %s" % (name, headers[header]))

                headers[header] = name