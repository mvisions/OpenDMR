"""A/B: the same frames (FSW + a 24-symbol window W + a level staircase), only W changes: DMR's sync, P25's sync, the
real NXDN frame head, random outer symbols. W itself is the sync pattern. Radio to radio (radio_pair.py, UHF); after
each lock, the staircase's levels as received.

  python nxdn/py/ab_sync.py [trials]
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
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 4
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}


def symbols(hex48):
    v = int(hex48, 16)
    return [LEVEL[(v >> (46 - 2 * i)) & 3] for i in range(24)]


WINDOWS = {
    'DMR BS voice sync': symbols('755FD7DF75F7'),
    'P25 sync': symbols('5575F5FF77FF'),
    'NXDN frame head': [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3, -3, 3, 3, 3, -3, 3, 3, -3, -3, 1, -3, -3, -1, -1],
    'random outer': [3, 3, -3, 3, -3, -3, 3, -3, 3, 3, 3, -3, -3, 3, -3, -3, -3, 3, 3, -3, 3, -3, -3, 3],
}


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    only = sys.argv[2:]
    for name, w in WINDOWS.items():
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        sym = (FSW + w + STAIR)[:192]
        v = 0
        for s in sym:
            v = (v << 2) | D[s]
        path = os.path.join(OUT, 'ab.txt')
        open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
        sv = 0
        for s in w:
            sv = (sv << 2) | D[s]
        sent = np.array(sym, float)
        for t in range(trials):
            out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'ab', '--frames', path, '--sync',
                                  '%012X' % sv, '--seconds', '2', '--blocks', '40'],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            m = re.search(r'rx (\d+) blocks', out)
            txs = re.search(r'tx state (\d+), (\d+) blocks sent', out)
            gaps = re.search(r'gaps between blocks: (\d+) \.\. (\d+) us', out)
            kinds = re.search(r'RX_TYPE_INFO\[1:0\]: ([^(]*)', out)
            diag = 'tx %s; gaps %s; types %s' % ('/'.join(txs.groups()) if txs else '?',
                                                '-'.join(gaps.groups()) if gaps else '-',
                                                kinds.group(1).strip() if kinds else '-')
            if not m or int(m.group(1)) == 0:
                print('%-18s #%d: no lock   (%s)' % (name, t, diag), flush=True)
                continue
            d = np.frombuffer(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'ab.dibits'), 'rb').read(), np.uint8)
            s = np.array([LEVEL[x] for x in d], float)
            sw = np.lib.stride_tricks.sliding_window_view(s, 192)
            score = (sw == sent).sum(axis=1)
            i = int(np.argmax(score))
            got, ref = s[i + 34:i + 192], sent[34:192]
            text = '  '.join('%+d->' % lv + '/'.join('%d' % round(100 * np.mean(got[ref == lv] == y))
                                                       for y in (3, 1, -1, -3)) for lv in (3, 1, -1, -3))
            print('%-18s #%d: best frame %3d/192 right;  staircase %s   (%s)' % (
                name, t, score[i], text, diag), flush=True)


if __name__ == '__main__':
    main()
