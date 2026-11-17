"""Which SACCH / FACCH1 coding reading fits the recording: every combination of interleave direction, puncture
pattern, generator tap order and dibit bit order; scored by the re-encoded bits' agreement with the received hard
bits (right reading: near 100 %), then the CRC (init ones / zeros, bit order).

  cd nxdn/py && python probe_l2.py "../data/iq/NXDN96 IQ.wav"

2026-11-16: "taps reversed" won (99.7 %): l2.py had the generator bits in the wrong order; fixed there since.
"""
import itertools
import sys

import numpy as np

import frames as F
import l2


def hard(v):
    return 0 if v > 0 else 1


def bits_of(symbols, order):
    out = []
    for v in symbols:
        b0 = 0 if v >= 0 else 1                 # the sign
        b1 = 1 if abs(v) >= 2 else 0            # outer
        out += [b0, b1] if order == 0 else [b1, b0]
    return out


def run(symbols, rows, cols, keep, n_in, transpose, taps):
    rx = bits_of(symbols, 0)
    soft = [1.0 - 2 * b for b in rx]
    if transpose:
        rows, cols = cols, rows
    de = l2.deinterleave(soft, rows, cols)
    dp = l2.depuncture(de, keep)
    g1, g2 = taps
    old = l2.G1, l2.G2
    l2.G1, l2.G2 = g1, g2
    dec = l2.viterbi(dp[:2 * n_in])
    enc = l2.conv_encode(dec)
    l2.G1, l2.G2 = old
    kept = [i for i, k in enumerate(keep * (len(enc) // len(keep) + 1)) if k][:len(de)]
    agree = np.mean([(enc[i] if i < len(enc) else 0) == hard(dp[i]) for i in kept if dp[i] != 0])
    return agree, dec


def rev5(x):
    return int(format(x, '05b')[::-1], 2)


def main():
    wav = sys.argv[1]
    fr = F.frames(np.load(wav + '.frames.npy'), 0)
    tests = [f['payload'][F.LICH:F.LICH + F.SACCH] for f in fr if (f['lich'] >> 5) == 0b10][:40]
    tap_sets = {'as written': (l2.G1, l2.G2), 'taps reversed': (rev5(l2.G1), rev5(l2.G2)),
                'G1/G2 swapped': (l2.G2, l2.G1), 'reversed+swapped': (rev5(l2.G2), rev5(l2.G1))}
    keeps = {'G2 of 3,6': l2.SACCH_KEEP, 'G1 of 3,6': [1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1],
             'G2 of 1,4': [1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1][::-1]}
    results = []
    for (tn, taps), (kn, keep), transpose in itertools.product(tap_sets.items(), keeps.items(), (False, True)):
        a = np.mean([run(s, 5, 12, keep, 36, transpose, taps)[0] for s in tests])
        results.append((a, tn, kn, transpose))
    for a, tn, kn, tr in sorted(results, reverse=True)[:6]:
        print('SACCH %.1f %% agree: taps %s, puncture %s, interleave %s' % (100 * a, tn, kn, 'transposed' if tr else 'rows'))


if __name__ == '__main__':
    main()
