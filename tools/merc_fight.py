"""Play from leaving the jewel room through the Mercenary's fight, on either disk.

    python tools/merc_fight.py original|patched [god]

Phases: 0 = the guards' fight (god mode on); 1 = the Mercenary's conversation;
2 = his fight (god mode off unless 'god' is given). Prints every page and battle
message in phase 1-2 and how it ends."""
import sys, os, json, time
sys.path.insert(0, '.')
from rominfo import SRC_DISK
from kuro_core import CoreEmu
from kuro_test import Tester

which = sys.argv[1]
keep_god = 'god' in sys.argv[2:]
e = CoreEmu(hdd=os.path.abspath(SRC_DISK) if which == 'original' else None)
t = Tester(emu=e)
t.log = lambda *a: None
r = json.load(open('routes/03_to_mercenary.json'))
r['steps'] = [s for s in r['steps'] if s['op'] != 'save_state']
i = next(k for k, s in enumerate(r['steps']) if s.get('kind') == 'bump' and s.get('index') == 9)
r['steps'] = r['steps'][:i + 3]
t0 = time.time()
t.play(r)
print('ROUTE DONE in', round(time.time() - t0), 's:', e.map_name(), e.state(), flush=True)

phase, fought = 0, False
seen = None
for half in range(3000):
    if phase < 2 or keep_god:
        e.heal()
    st = e.state()
    if st == 'battle':
        fought = True
        if phase == 1:
            phase = 2
            e.save_state(f'{which}_merc_fight_start')
            print('--- the Mercenary fight begins', flush=True)
        m = e.menu()
        if m and m['items']:
            t.select(m['items'][0][1]); e.wait(0.4)
            if e.menu() is None:
                e.press('SPACE', gap=0.3)
            continue
    elif st == 'dialogue':
        d = e.dialogue()
        if d and d['waiting']:
            text = ' / '.join(l.strip() for l in d['lines'])
            if phase == 0 and fought and not text.startswith(('Shinobu gained', 'シノブは')) \
                    and 'gold' not in text and 'EXP' not in text and '経験' not in text:
                phase = 1
                print('--- the Mercenary conversation', flush=True)
            if phase >= 1 and text != seen:
                print(f'{half/2:6.1f}s TEXT {text}', flush=True)
                seen = text
            e.press('SPACE', gap=0.3)
        else:
            e.wait(0.2)      # let the page finish (or its stale-text timer run out)
        continue
    elif st == 'menu':
        print('TITLE MENU (game over)'); break
    elif st == 'field' and phase == 2 and not e.map_name().startswith('bac'):
        print('FIELD', e.map_name(), e.pos()); break
    if st == 'dos':
        print('CRASH (DOS)'); break
    e.wait(0.5)
e.shot(f'scratch_emu/merc_{which}_end.png')
print('END', which, e.state(), e.map_name(), 'HP', e.word(0x16d80 + 0x1007), 'phase', phase,
      'after', half / 2, 'emulated s')
