"""Builds nxdn/c/test_core.c with src/services/nxdn_core.c (gcc on the PC) and runs it on the radio's FM recordings
(nxdn/data/radio/*.af.npy, converted to raw 16-bit samples).

  python nxdn/c/run.py [names ...] [-v]       e.g. stab_00 stab_01; default: all stab_*
"""
import glob
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
DATA = os.path.join(ROOT, 'nxdn', 'data', 'radio')
GCC = os.environ.get('GCC', 'C:/msys64/ucrt64/bin/gcc.exe')


def main():
    args = [a for a in sys.argv[1:] if a != '-v']
    exe = os.path.join(DATA, 'test_core.exe')
    env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ['PATH'])
    subprocess.run([GCC, '-O2'] + (['-DNXDN_DEBUG'] if os.environ.get('NXDN_DEBUG') else []) + [ '-Wall', '-Wextra', '-I', os.path.join(ROOT, 'src', 'services'), '-o', exe,
                    os.path.join(HERE, 'test_core.c'), os.path.join(ROOT, 'src', 'services', 'nxdn_core.c'), '-lm'],
                   check=True, env=env)
    names = args or sorted(os.path.basename(p)[:-7] for p in glob.glob(os.path.join(DATA, 'stab_*.af.npy')))
    raws = []
    for n in names:
        x = np.load(os.path.join(DATA, n + '.af.npy'))
        raw = os.path.join(DATA, n + '.raw')
        np.clip(x, -32768, 32767).astype('<i2').tofile(raw)
        raws.append(raw)
    subprocess.run([exe] + (['-v'] if '-v' in sys.argv else []) + raws, env=env)


if __name__ == '__main__':
    main()
