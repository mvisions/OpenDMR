"""Which symbols of the real NXDN frame head make the HR_C7000 lock badly? From a window that locks well (head-like),
the positions where the real head differs are put in by halves (a bisection): a window locks well when, after the
lock, the staircase decodes (frames found, >= 95 % of the symbols right).

  python nxdn/py/bisect_test.py
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
GOOD = list(BASE)
for p, v in [(1, 1), (8, -1), (19, 1), (22, -1), (23, -1)]:
    GOOD[p] = v
HEAD = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3, -3, 3, 3, 3, -3, 3, 3, -3, -3, 1, -3, -3, -1, -1]
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 4
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}


def trial(w, name):
    sym = (FSW + w + STAIR)[:192]
    v = 0
    for s in sym:
        v = (v << 2) | D[s]
    path = os.path.join(OUT, 'bis.txt')
    open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
    sv = 0
    for s in w:
        sv = (sv << 2) | D[s]
    out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'bis', '--frames', path, '--sync',
                          '%012X' % sv, '--seconds', '2', '--blocks', '40'],
                         capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    m = re.search(r'rx (\d+) blocks', out)
    if not m or int(m.group(1)) == 0:
        return 'no lock', False
    d = np.frombuffer(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'bis.dibits'), 'rb').read(), np.uint8)
    s = np.array([LEVEL[x] for x in d], float)
    sent = np.array(sym, float)
    if len(s) < 192:
        return 'short', False
    sw = np.lib.stride_tricks.sliding_window_view(s, 192)
    best = (sw == sent).sum(axis=1).max() / 192
    return 'best frame %.0f %%' % (100 * best), best >= 0.95


def good(w, name, tries=2):
    results = [trial(w, name) for _ in range(tries)]
    ok = any(r[1] for r in results)
    print('  %-34s %s -> %s' % (name, ', '.join(r[0] for r in results), 'GOOD' if ok else 'bad'), flush=True)
    return ok


def main():
    diff = [i for i in range(24) if GOOD[i] != HEAD[i]]
    print('positions where the real head differs from the good window:', diff)
    print('good window:', GOOD)
    print('real head:  ', HEAD)
    if not good(GOOD, 'good window'):
        print('the good window does not lock well now: stop')
        return
    suspects = diff
    while len(suspects) > 1:
        half = suspects[:len(suspects) // 2]
        w = list(GOOD)
        for i in half:
            w[i] = HEAD[i]
        if not good(w, 'head at %s' % half):
            suspects = half
        else:
            rest = suspects[len(suspects) // 2:]
            w = list(GOOD)
            for i in rest:
                w[i] = HEAD[i]
            if not good(w, 'head at %s' % rest):
                suspects = rest
            else:
                print('neither half alone makes it bad: an interaction of %s' % suspects)
                break
    print('suspects:', suspects)


if __name__ == '__main__':
    main()
