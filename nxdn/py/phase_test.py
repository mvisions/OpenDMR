"""The HR_C7000's PHASE_OUT (the phase signal's maximum and minimum, 14 bits) and RECV_INFO_COUNT per received block,
recorded by the experimental firmware (p25_phy.c: in the block's sys / us2 fields), for a good lock (sync window after
the FSW) and a bad one (window starting at the FSW): the frames of window_test.py.

  python nxdn/py/phase_test.py
"""
import os
import re
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
OUT = os.path.join(ROOT, 'nxdn', 'data', 'patterns')
FSW = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3]
W = [3, 1, -3, 3, -3, -3, 3, -1, 3, 3, 3, -3, -3, 3, -3, -3, -3, 3, 3, 1, 3, -3, -1, -1]   # head-like +-1
STAIR = ([3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12) * 4
D = {3: 1, 1: 0, -1: 2, -3: 3}


def s14(x):
    return x - 0x4000 if x & 0x2000 else x


def run(name, sync_symbols):
    sym = (FSW + W + STAIR)[:192]
    v = 0
    for s in sym:
        v = (v << 2) | D[s]
    path = os.path.join(OUT, 'phase.txt')
    open(path, 'w', newline='\n').write(('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper()) * 4)
    sv = 0
    for s in sync_symbols:
        sv = (sv << 2) | D[s]
    out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'phase', '--frames', path,
                          '--sync', '%012X' % sv, '--seconds', '2', '--blocks', '40'],
                         capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    m = re.search(r'rx (\d+) blocks', out)
    print('== %s: sync %012X, %s' % (name, sv, m.group(0) if m else 'no reply'))
    raw = open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'phase.bin'), 'rb').read()
    rows = []
    for i in range(0, len(raw) - 87, 88):
        us, typ, ph, us2 = struct.unpack('<IIII', raw[i:i + 16])
        rows.append((s14((ph >> 16) & 0x3FFF), s14(ph & 0x3FFF), typ & 0xFF, us2))
    for k, (mx, mn, se, us2) in enumerate(rows[:12]):
        print('  block %2d: phase max %6d min %6d  centre %6d  span %6d   sync errors %3d' % (
            k, mx, mn, (mx + mn) // 2, mx - mn, se))


def main():
    run('good: the window after the FSW', W)
    run('bad: the window from the FSW', FSW + W[:14])


if __name__ == '__main__':
    main()
