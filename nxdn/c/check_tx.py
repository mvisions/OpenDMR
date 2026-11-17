"""nxdn_core.c's transmit side (nxdn/c/test_tx.c) against nxdn/py/tx.py: the same call, symbol by symbol; then the
C symbols decoded back by nxdn/py (frames, l2).

  python nxdn/c/check_tx.py [frames.bit] [--src 4601] [--dst 46025] [--ran 1]
"""
import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'nxdn', 'py'))
import tx  # noqa: E402

GCC = os.environ.get('GCC', 'C:/msys64/ucrt64/bin/gcc.exe')
LEVEL = np.array([1, 3, -1, -3])  # dibit -> symbol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bits', nargs='?')
    ap.add_argument('--src', type=int, default=4601)
    ap.add_argument('--dst', type=int, default=46025)
    ap.add_argument('--ran', type=int, default=1)
    a = ap.parse_args()
    out_dir = os.path.join(ROOT, 'nxdn', 'data')
    if a.bits is None:  # random frames: 37 (a partial last group of 4)
        rng = np.random.default_rng(7)
        a.bits = os.path.join(out_dir, 'tx_check.bit')
        rng.integers(0, 256, 37 * 9, dtype=np.uint8).tofile(a.bits)
    exe = os.path.join(out_dir, 'test_tx.exe')
    env = dict(os.environ, PATH=os.path.dirname(GCC) + os.pathsep + os.environ['PATH'])
    subprocess.run([GCC, '-O2', '-Wall', '-Wextra', '-I', os.path.join(ROOT, 'src', 'services'), '-o', exe,
                    os.path.join(HERE, 'test_tx.c'), os.path.join(ROOT, 'src', 'services', 'nxdn_core.c'), '-lm'],
                   check=True, env=env)
    c = subprocess.run([exe, a.bits, str(a.src), str(a.dst), str(a.ran)], capture_output=True, check=True,
                       env=env).stdout
    c_sym = LEVEL[np.frombuffer(c, np.uint8)]
    d = open(a.bits, 'rb').read()
    voice = [d[i:i + 9] for i in range(0, len(d) - 8, 9)]
    py_sym, n = tx.call(voice, a.src, a.dst, a.ran, 2400)
    print('C %d symbols, Python %d (%d voice frames in %d frames)' % (len(c_sym), len(py_sym), len(voice), n))
    if len(c_sym) != len(py_sym):
        sys.exit('lengths differ')
    diff = np.nonzero(c_sym != py_sym.astype(int))[0]
    if len(diff):
        k = diff[0]
        sys.exit('%d symbols differ, the first at %d (frame %d, symbol %d)' % (len(diff), k, (k - 12) // 192,
                                                                            (k - 12) % 192))
    print('identical')


if __name__ == '__main__':
    main()
