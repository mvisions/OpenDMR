"""Where the 24-symbol sync window starts in the frame (FSW + head-like window + staircase), and whether the HR_C7000
then locks well: the window slid from the FSW's first symbol on; radio to radio (radio_pair.py), lock and the
staircase's levels.

  python nxdn/py/slide_test.py [trials] [starts...]
"""
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
OUT = os.path.join(ROOT, 'nxdn', 'data', 'patterns')
FSW = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3]
W = [3, 1, -3, 3, -3, -3, 3, -1, 3, 3, 3, -3, -3, 3, -3, -3, -3, 3, 3, 1, 3, -3, -1, -1]
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 4
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}
SYM = (FSW + W + STAIR)[:192]


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    starts = [int(x) for x in sys.argv[2:]] or [0, 2, 4, 6, 8, 10]
    v = 0
    for s in SYM:
        v = (v << 2) | D[s]
    path = os.path.join(OUT, 'slide.txt')
    open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
    sent = np.array(SYM, float)
    for k in starts:
        win = SYM[k:k + 24]
        sv = 0
        for s in win:
            sv = (sv << 2) | D[s]
        for t in range(trials):
            out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'slide', '--frames', path,
                                  '--sync', '%012X' % sv, '--seconds', '2', '--blocks', '40'],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            m = re.search(r'rx (\d+) blocks', out)
            if not m or int(m.group(1)) == 0:
                print('start %2d #%d: no lock' % (k, t), flush=True)
                continue
            d = np.frombuffer(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'slide.dibits'), 'rb').read(), np.uint8)
            s = np.array([LEVEL[x] for x in d], float)
            sw = np.lib.stride_tricks.sliding_window_view(s, 192)
            score = (sw == sent).sum(axis=1)
            i = int(np.argmax(score))
            print('start %2d #%d: locked, best frame match %3d / 192 symbols' % (k, t, score[i]), flush=True)


if __name__ == '__main__':
    main()
