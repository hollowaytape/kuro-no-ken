"""Which area can run which battle scripts?

The game mounts one .FA1 at a time, so `bsd_play.py` can only start a battle whose file
is in the archive the current map has open. This tries one BSD from each archive in each
saved area state, and prints the mapping that `bsd_play --all` needs.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import bsd_play                                    # noqa: E402

PROBES = {'B.FA1': 'D010_X10.BSD', 'C.FA1': 'C021_X10.BSD',
          'D.FA1': 'C042_X10.BSD', 'E.FA1': 'DL30_X10.BSD'}


class Args:
    background = 'bac_11'
    seconds = 2.0
    quiet_for = 0.0
    no_force = True


def main():
    from bench import RenderBench
    states = sorted(n[:-len('.np2core')] for n in os.listdir(os.path.join(HERE, '..', 'states'))
                    if n.startswith('area_') and n.endswith('.np2core'))
    b = RenderBench(states[0])
    e = b.e
    out = {}
    for st in states:
        try:
            e.load_state(st)
            e.set_noclip(True)
            e.heal()
            b.base = e.m.save_state()
        except Exception as ex:
            print('%-10s could not load: %s' % (st, str(ex)[:40]))
            continue
        ok = []
        for arc, probe in PROBES.items():
            if bsd_play.run_one(b, probe, Args, verbose=False) is not None:
                ok.append(arc)
        out[st] = ok
        print('%-10s %-14s %s' % (st, e.map_name() or '?', ' '.join(ok) or '-'))
    print()
    for arc in PROBES:
        hosts = [s for s, v in out.items() if arc in v]
        print('%s: %s' % (arc, ' '.join(hosts) or 'NO AREA MOUNTS IT'))


if __name__ == '__main__':
    main()
