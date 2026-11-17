"""A hotspot frame (48 bytes hex, from hs_trace.py / the MMDVMHost trace) against the frames our transmitter makes
(nxdn/c/test_tx.exe from check_tx.py): the first frame (VCALL) and the 4 voice frame headers (FSW, LICH, SACCH: the
first 48 symbols; the rest is the AMBE of the mic), wrong bits counted.

  python nxdn/py/hs_compare.py HEX [--src 12871] [--dst 9] [--ran 1]
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('hex', nargs='+')
    ap.add_argument('--src', type=int, default=12871)
    ap.add_argument('--dst', type=int, default=9)
    ap.add_argument('--ran', type=int, default=1)
    a = ap.parse_args()
    exe = os.path.join(ROOT, 'nxdn', 'data', 'test_tx.exe')
    bitfile = os.path.join(ROOT, 'nxdn', 'data', 'hs_zero.bit')
    open(bitfile, 'wb').write(bytes(9 * 16))
    env = dict(os.environ, PATH='C:/msys64/ucrt64/bin' + os.pathsep + os.environ['PATH'])
    d = subprocess.run([exe, bitfile, str(a.src), str(a.dst), str(a.ran)], capture_output=True, check=True,
                       env=env).stdout
    frames = [d[12 + 192 * k:12 + 192 * (k + 1)] for k in range(len(d[12:]) // 192)]

    def bits_of(dibits, n):
        return [(x >> s) & 1 for x in dibits[:n] for s in (1, 0)]

    for h in a.hex:
        raw = bytes.fromhex(h)
        got = [(b >> (7 - i)) & 1 for b in raw for i in range(8)]
        res = []
        for k, f in enumerate(frames[:6]):
            n = 192 if k == 0 or k == len(frames) - 1 else 48
            exp = bits_of(f, n)
            res.append('f%d %d/%d' % (k, sum(x != y for x, y in zip(exp, got)), 2 * n))
        print(h[:12], ' '.join(res))


if __name__ == '__main__':
    main()
