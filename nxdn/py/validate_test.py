"""Can the firmware tell a good lock from a bad one? Radio to radio NXDN96 (the 1031 Hz test frames), a relaxed sync
threshold so that it locks; for each lock: the known 18 symbols (FSW + LICH) in the lock block's sync field against
the pattern, and how well the capture then decodes (chip96.py).

  python nxdn/py/validate_test.py [trials] [--sync CDF59D5D7CFA] [--threshold 0150502F]
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from p25_phy import parse_full, bits_of  # noqa: E402

REF = 'E:/exam/pistar-signal-gen/files/1031Hz_test_nxdn.txt'
L = {1: 3, 0: 1, 2: -1, 3: -3}


def syms(bits):
    return [L[(bits[i] << 1) | bits[i + 1]] for i in range(0, len(bits), 2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trials', type=int, nargs='?', default=6)
    ap.add_argument('--sync', default='CDF59D5D7CFA')
    ap.add_argument('--threshold', default='0150502F')
    ap.add_argument('--known', type=int, default=18, help='symbols of the pattern known for sure')
    a = ap.parse_args()
    pat = syms([(int(a.sync, 16) >> (47 - i)) & 1 for i in range(48)])
    for t in range(a.trials):
        out = subprocess.run([sys.executable, os.path.join(HERE, 'radio_pair.py'), 'val', '--frames', REF, '--sync',
                              a.sync, '--threshold', a.threshold, '--seconds', '2', '--blocks', '60'],
                             capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        m = re.search(r'rx (\d+) blocks', out)
        if not m or int(m.group(1)) == 0:
            print('#%d: no lock' % t, flush=True)
            continue
        b = parse_full(open(os.path.join(ROOT, 'nxdn', 'data', 'radio', 'val.bin'), 'rb').read())
        _, kind, _, _, d, _ = b[0]
        bits = bits_of(d)
        field = syms(bits[24:72]) if (kind & 3) in (0, 1) else syms(bits[44:92])
        known = sum(1 for x, y in zip(field[:a.known], pat[:a.known]) if x == y)
        kinds2 = sum(1 for x in b if (x[1] & 3) == 2)
        q = subprocess.run([sys.executable, os.path.join(HERE, 'chip96.py'),
                            os.path.join(ROOT, 'nxdn', 'data', 'radio', 'val.dibits'), '--reference', REF],
                           capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        e = re.search(r'symbol errors ([\d.]+) %', q)
        dd = re.search(r'LICH ok (\d+), SACCH CRC ok (\d+), VCH = the 1031 Hz vector (\d+) of (\d+)', q)
        print('#%d: lock block: %2d of %d known symbols right; type-2 blocks %2d of %d;  %s  %s' % (
            t, known, a.known, kinds2, len(b), ('%s %% symbol errors' % e.group(1)) if e else 'frames not found',
            ('LICH %s SACCH %s VCH %s/%s' % dd.groups()) if dd else ''), flush=True)


if __name__ == '__main__':
    main()
