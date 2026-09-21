"""Build a test disk that runs a chosen battle script in place of a random encounter.

A .BSD cannot be called the way `verify_blocks.py` calls a .SCN block: the battle engine
runs it, there is no script opcode that says "run this battle", and swapping the loaded
bytes in RAM desyncs the engine from the graphics it already pulled in for the original
fight. What does work is substituting one file for another *on disk*, so the engine
loads it normally, resources and all: pick a battle that is easy to reach - a random
encounter on the world map - and give its slot the contents of the file to verify.

    python tools/bsd_stage.py D010_X10.BSD              # -> scratch_emu/bsd_test.hdi
    python tools/bsd_stage.py D010_X10.BSD --slot F011_A20.BSD

The slot must live in the archive the map mounts - the game mounts one .FA1 at a time -
but the contents can come from anywhere, since the member keeps the slot's name.
`--list` shows which archive holds each battle script; the world map mounts A.FA1.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project root; this file is in tools/
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))

DEFAULT_SLOT = 'F011_A20.BSD'          # a random encounter on the world map (stg.mpc)
TEST_DISK = os.path.join('scratch_emu', 'bsd_test.hdi')


def archive_of(name):
    import fa1
    for arc in fa1.ARCHIVES:
        d = open(os.path.join('original', arc.decode()), 'rb').read()
        end = int.from_bytes(d[4:7], 'little')
        c = end
        while d[c] == 0:
            c += 1
        t = bytes(b ^ 0xFF for b in d[c:])
        while len(t) >= 20:
            nm, ext = t[:8].decode('latin1').strip(), t[8:11].decode('latin1').strip()
            if not nm:
                break
            if nm + '.' + ext == name:
                return arc.decode()
            t = t[20:]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bsd', nargs='?')
    ap.add_argument('--slot', default=DEFAULT_SLOT)
    ap.add_argument('--out', default=TEST_DISK)
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()

    import fa1
    from rominfo import DEST_DISK
    from romtools.disk import Disk

    if args.list or not args.bsd:
        for f in sorted(fa1.BSD_FILES_WITH_TEXT):
            print('%-14s %s' % (f, archive_of(f)))
        return 0

    want, slot = args.bsd, args.slot
    arc_want, arc_slot = archive_of(want), archive_of(slot)
    if arc_slot is None:
        print('%s is not a member of any archive' % slot)
        return 1
    if arc_want != arc_slot:
        # Fine: the archive member keeps the slot's *name*, only its contents change.
        # What matters is that the slot is in the archive the map mounts.
        print('note: %s comes from %s, being staged into %s in %s'
              % (want, arc_want, slot, arc_slot))

    src = os.path.join('patched', want)
    if not os.path.exists(src):
        src = os.path.join('original', 'decompressed', want)
    data = open(src, 'rb').read()
    shutil.copyfile(os.path.join('patched', slot), os.path.join('patched', slot + '.bak'))
    open(os.path.join('patched', slot), 'wb').write(data)
    # repack only recompresses files it believes were reinserted
    fa1.BSD_FILES_WITH_TEXT.append(slot)
    try:
        fa1.repack(os.path.join('patched', arc_slot))
        shutil.copyfile(DEST_DISK, args.out)
        Disk(args.out).insert(os.path.join('patched', arc_slot), path_in_disk='B-DRKNS')
    finally:
        shutil.move(os.path.join('patched', slot + '.bak'), os.path.join('patched', slot))
        fa1.BSD_FILES_WITH_TEXT.remove(slot)
        fa1.repack(os.path.join('patched', arc_slot))    # put the real build back
    print('%s now plays as %s -> %s' % (want, slot, args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
