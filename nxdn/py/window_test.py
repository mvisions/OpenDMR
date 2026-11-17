"""How inner levels (+-1) in the 24-symbol sync window shift what the HR_C7000 decides after the lock: frames of
FSW + window W (the sync pattern) + a level staircase, W with +-1 put in at chosen places; radio to radio
(radio_pair.py), the staircase's levels as received per level sent.

  python nxdn/py/window_test.py
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
BASE = [3, 3, -3, 3, -3, -3, 3, -3, 3, 3, 3, -3, -3, 3, -3, -3, -3, 3, 3, -3, 3, -3, -3, 3]
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 4
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}


def window(changes):
    w = list(BASE)
    for pos, v in changes:
        w[pos] = v
    return w


HEAD = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3, -3, 3, 3, 3, -3, 3, 3, -3, -3, 1, -3, -3, -1, -1]   # the real frame head
CASES = {
    'real head after FSW': [(i, v) for i, v in enumerate(HEAD)],
}


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    for name, ch in CASES.items():
        w = window(ch)
        sym = (FSW + w + STAIR)[:192]
        v = 0
        for s in sym:
            v = (v << 2) | D[s]
        path = os.path.join(OUT, 'win.txt')
        open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
        sv = 0
        for s in w:
            sv = (sv << 2) | D[s]
        for t in range(trials):
            extra = ['--rfmode', os.environ['RFMODE']] if os.environ.get('RFMODE') else []
            out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'win', '--frames', path,
                                  '--sync', '%012X' % sv, '--seconds', '3', '--blocks', '60'] + extra,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            m = re.search(r'rx (\d+) blocks', out)
            if not m or int(m.group(1)) == 0:
                print('%-14s #%d: no lock' % (name, t), flush=True)
                continue
            d = np.frombuffer(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'win.dibits'), 'rb').read(), np.uint8)
            s = np.array([LEVEL[x] for x in d], float)
            sw = np.lib.stride_tricks.sliding_window_view(s, 34)
            ref = np.array(FSW + w, float)
            hits = np.where(np.sum(sw == ref, axis=1) >= 28)[0]
            rows = {3: [], 1: [], -1: [], -3: []}
            for h in hits:
                if h + 192 > len(s):
                    continue
                got = s[h + 34:h + 192]
                sent = np.array(sym[34:192])
                for lv in rows:
                    rows[lv].append(got[sent == lv])
            if not hits.size:
                print('%-14s #%d: locked, frames not found' % (name, t), flush=True)
                continue
            text = []
            for lv in (3, 1, -1, -3):
                x = np.concatenate(rows[lv]) if rows[lv] else np.array([])
                if len(x):
                    text.append('%+d->' % lv + '/'.join('%d' % round(100 * np.mean(x == y)) for y in (3, 1, -1, -3)))
            print('%-14s #%d: %3d frames  %s   (%% received as +3/+1/-1/-3)' % (name, t, len(hits), '  '.join(text)),
                  flush=True)


if __name__ == '__main__':
    main()
