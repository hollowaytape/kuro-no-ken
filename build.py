"""Build a playable patched disk from the workbook - one command, for the translator.

    python build.py            (or double-click build.bat)
    python build.py --gfx-dialogue     dialogue boxes in graphics mode (VWF groundwork)

1. checks the setup and says exactly what is missing, instead of a traceback
2. generates pointer sheets for every translated script (gen_pointers.py), keeping the
   hand-checked sheets for the scripts that were verified in game
3. reinserts every script that has English in the workbook (reinsert.py)
4. checks the result for the crash we know how to detect statically - a pointer left
   pointing at the old place (check_pointers.py, fix_pointers.py)

The patched disk is patched/Blade of Darkness (Kuro no Ken).hdi. Save the workbook in
Excel before building: the build reads the last saved copy.
"""
import glob
import importlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# romtools and NDC.EXE live in the sibling ../romtools folder; find them there so nobody
# has to edit PYTHONPATH or PATH by hand.
PARENT = os.path.dirname(HERE)
sys.path.insert(0, PARENT)
os.environ['PYTHONPATH'] = os.pathsep.join(p for p in (PARENT, os.environ.get('PYTHONPATH')) if p)
os.environ['PATH'] = os.pathsep.join((os.path.join(PARENT, 'romtools', 'bin'), os.environ.get('PATH', '')))

HDI = 'Blade of Darkness (Kuro no Ken).hdi'
WORKBOOK = 'KuroNoKen_dump.xlsx'
CURATED_PTRS = 'KuroNoKen_pointer_dump.xlsx'
FULL_PTRS = 'KuroNoKen_pointer_dump_full.xlsx'


def fail(msg):
    print('\nBUILD STOPPED: ' + msg)
    sys.exit(1)


def preflight():
    problems = []
    if sys.version_info < (3, 8):
        problems.append('Python 3.8 or newer is needed (this is %s).' % sys.version.split()[0])
    missing = []
    for mod, pip in (('openpyxl', 'openpyxl'), ('xlsxwriter', 'xlsxwriter'),
                     ('bitstring', 'bitstring'), ('capstone', 'capstone'), ('ndc', 'ndcpy')):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip)
    if missing:
        problems.append('Python packages missing: %s.  Fix:  pip install -r requirements.txt'
                        % ', '.join(missing))
    try:
        importlib.import_module('romtools')
    except ImportError:
        problems.append('The shared "romtools" folder was not found. It must sit next to '
                        'this project folder, as ..\\romtools')
    if not shutil.which('ndc'):
        problems.append('NDC.EXE (the disk-image tool) was not found. It should be at '
                        '..\\romtools\\bin\\NDC.EXE')
    if not os.path.exists(os.path.join('original', HDI)):
        problems.append('Your copy of the game is missing: original\\%s' % HDI)
    if not glob.glob(os.path.join('original', 'decompressed', '*.SCN')):
        problems.append('original\\decompressed\\ is empty - it needs the extracted game files.')
    for f in (WORKBOOK, CURATED_PTRS):
        if not os.path.exists(f):
            problems.append('Missing %s in the project folder.' % f)
    if problems:
        fail('the setup is incomplete:\n  - ' + '\n  - '.join(problems))
    lock = '~$' + WORKBOOK   # Excel's lock file; a crash can leave a stale one behind
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 12 * 3600:
        print('note: %s is open in Excel. That is fine, but only what you last SAVED is built.'
              % WORKBOOK)
    # reinsert copies your save files out of the previous patched disk; on the very first
    # build there isn't one yet, so start it from the original.
    os.makedirs('patched', exist_ok=True)
    if not os.path.exists(os.path.join('patched', HDI)):
        print('first build: copying the original disk to patched\\')
        shutil.copyfile(os.path.join('original', HDI), os.path.join('patched', HDI))


def run(step, args, env=None):
    print('\n== %s ==' % step)
    t = time.time()
    log = os.path.join('patched', 'build_%s.log' % step.split()[0].lower())
    with open(log, 'w', encoding='utf-8', errors='replace') as fh:
        p = subprocess.run([sys.executable] + args, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, env=env, text=True,
                           encoding='utf-8', errors='replace')
        fh.write(p.stdout)
    lines = p.stdout.rstrip().splitlines()
    print('\n'.join(lines[-6:]))
    print('(%.0fs, full output in %s)' % (time.time() - t, log))
    return p.returncode, p.stdout


def main():
    preflight()
    env = dict(os.environ)

    # Which scripts to build, and which keep their hand-checked pointer sheets.
    code, out = run('pointers', ['-c', (
        'import sys\n'
        'sys.path.insert(0, "tools")\n'
        'import rominfo, gen_pointers\n'
        'scn = sorted({f for f in rominfo.FILES_TO_REINSERT if f.endswith(".SCN")})\n'
        'keep = [f for f in rominfo.CURATED_FILES if f.endswith(".SCN")]\n'
        'sys.argv = ["gen_pointers", "--out", %r, "--only"] + scn + ["--keep"] + keep\n'
        'gen_pointers.main()\n') % FULL_PTRS], env)
    if code:
        fail('generating pointer sheets failed - see patched\\build_pointers.log')

    env['KURO_POINTER_XLS'] = FULL_PTRS
    extra = ['--gfx-dialogue'] if '--gfx-dialogue' in sys.argv else []   # see reinsert.py
    code, reinsert_out = run('reinsert', ['reinsert.py'] + extra, env)
    if code:
        tail = [l for l in reinsert_out.splitlines() if l.strip()][-1:] or ['']
        fail('reinsertion failed:\n    %s\nThe line above names the file and offset. If it '
             'says a line is over the Japanese length, that script has to keep every line '
             'at most as long as the Japanese for now - shorten it.' % tail[0])

    code, out = run('check pointers', [os.path.join('tools', 'check_pointers.py')], env)
    code2, out2 = run('stale pointers', [os.path.join('tools', 'fix_pointers.py')], env)
    stale = out2.strip().splitlines()[-1] if out2.strip() else ''
    print('\n' + '=' * 60)
    if code or not stale.startswith('0 '):
        print('BUILT, BUT A POINTER CHECK FAILED - the game may crash in the scripts listed')
        print('above. Send patched\\build_*.log to the project lead before testing there.')
    else:
        print('BUILD OK:  patched\\%s' % HDI)
    # An archive growing past its original size is normal (the disk has room). A script
    # past its RAM slot is not: the game would load it over its neighbour.
    for line in reinsert_out.splitlines():
        if 'exceeds RAM limit' in line or 'left in Japanese' in line:
            print(line)


if __name__ == '__main__':
    main()
