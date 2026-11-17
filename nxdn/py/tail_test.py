"""Does what comes just before the sync window move the HR_C7000's levels after the lock? Frames of
FSW + 14 outer symbols (the sync window: FSW + those 14) + a staircase + a tail of 24 symbols, the tail varied;
radio to radio, the staircase's levels as received.

  python nxdn/py/tail_test.py [trials]
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
W14 = [3, 3, -3, 3, -3, -3, 3, -3, 3, 3, 3, -3, -3, 3]
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 3   # 144
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}
TAILS = {
    'alternating': [3, -3] * 12,
    'all +3': [3] * 24,
    'all -3': [-3] * 24,
    'all +1': [1] * 24,
}


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    for name, tail in TAILS.items():
        sym = FSW + W14 + STAIR + tail
        assert len(sym) == 192, len(sym)
        v = 0
        for s in sym:
            v = (v << 2) | D[s]
        path = os.path.join(OUT, 'tail.txt')
        open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
        sv = 0
        for s in (FSW + W14):
            sv = (sv << 2) | D[s]
        for t in range(trials):
            out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'tail', '--frames', path,
                                  '--sync', '%012X' % sv, '--seconds', '3', '--blocks', '60'],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            m = re.search(r'rx (\d+) blocks', out)
            if not m or int(m.group(1)) == 0:
                print('%-12s #%d: no lock' % (name, t), flush=True)
                continue
            d = np.frombuffer(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'tail.dibits'), 'rb').read(), np.uint8)
            s = np.array([LEVEL[x] for x in d], float)
            # the frames found by the staircase (it is long and not shifted much): best match of the whole frame
            sent = np.array(sym, float)
            sw = np.lib.stride_tricks.sliding_window_view(s, 192)
            score = np.sum(np.sign(sw) == np.sign(sent), axis=1)
            hits = [i for i in range(len(score)) if score[i] >= 170 and score[i] == score[max(0, i - 96):i + 96].max()]
            if not hits:
                print('%-12s #%d: locked, frames not found' % (name, t), flush=True)
                continue
            got = np.concatenate([s[h + 24:h + 168] for h in hits])
            ref = np.concatenate([sent[24:168] for _ in hits])
            text = '  '.join('%+d->' % lv + '/'.join('%d' % round(100 * np.mean(got[ref == lv] == y))
                                                       for y in (3, 1, -1, -3)) for lv in (3, 1, -1, -3))
            print('%-12s #%d: %3d frames  %s   (%% as +3/+1/-1/-3)' % (name, t, len(hits), text), flush=True)


if __name__ == '__main__':
    main()
