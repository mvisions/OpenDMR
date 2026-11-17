"""The FM recordings (af_capture.py, af_stability.py) against the frames sent: where the symbol errors are (position in
the frame, level), and a linear receiver fitted on known frames (least squares: the symbols sent from the 24 kHz
samples around each symbol time), tried on other recordings.

  python nxdn/py/af_eq.py analyse nxdn/data/radio/stab_*.af.npy
  python nxdn/py/af_eq.py fit --train stab_0[0-4] --test stab_0[5-9] [--taps 31]
"""
import argparse
import glob
import os
import sys

import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demod as DM  # noqa: E402
from chip import reference_frames  # noqa: E402

FS, BAUD = 24000, 2400
SPS = FS / BAUD
REF = 'E:/exam/pistar-signal-gen/files/1031Hz_test_nxdn.txt'
DATA = os.path.join(HERE, '..', 'data', 'radio')


def prepare(path, tau=600):
    x = np.load(path)
    x = x - x.mean()
    t = tau * 1e-6 * 8000
    x = x + t * np.r_[0, np.diff(x)]
    return resample_poly(x, 3, 1)


def locate(x):
    """the frames: (start time in 24 kHz samples, symbol period, sign, index of the frame sent)"""
    f = DM.lowpass(x, FS, BAUD * 0.6)
    best = None
    for sign in (1, -1):
        for phase in np.arange(0, SPS, SPS / 20):
            idx = (phase + np.arange(int((len(f) - phase - 1) / SPS)) * SPS).astype(int)
            c = DM.norm_corr(sign * f[idx], DM.FSW_SYMBOLS)
            keep = []
            for h in np.where(c > 0.85)[0]:
                if keep and h - keep[-1] < 96:
                    if c[h] > c[keep[-1]]:
                        keep[-1] = h
                    continue
                keep.append(h)
            score = sum(1 for p, q in zip(keep, keep[1:]) if (q - p) % 192 in (0, 1, 191))
            if best is None or score > best[0]:
                best = (score, phase, sign, keep)
    _, phase, sign, hits = best
    k = np.arange(10)
    starts = []
    for h in hits:
        t0 = phase + h * SPS
        cands = [(np.corrcoef(sign * DM.interp(f, t0 + d + k * SPS), DM.FSW_SYMBOLS)[0, 1], t0 + d)
                 for d in np.arange(-SPS / 2, SPS / 2, SPS / 16)]
        starts.append(max(cands)[1])
    ref = reference_frames(REF)
    out = []
    for i, t0 in enumerate(starts):
        if t0 + 192 * SPS + 40 > len(x):
            continue
        period = SPS
        if i + 1 < len(starts) and abs((starts[i + 1] - t0) - 192 * SPS) < SPS:
            period = (starts[i + 1] - t0) / 192
        v = sign * DM.interp(f, t0 + np.arange(192) * period)
        r = int(np.argmax([np.sum(np.sign(v) == np.sign(rf)) for rf in ref]))
        out.append((t0, period, sign, r))
    return f, out, ref


def slice4(v):
    return np.where(v >= 2, 3, np.where(v >= 0, 1, np.where(v > -2, -1, -3)))


def analyse(paths):
    pos = np.zeros(192)
    cnt = 0
    conf = np.zeros((4, 4), int)
    idx = {3: 0, 1: 1, -1: 2, -3: 3}
    resid = []
    for p in paths:
        x = prepare(p)
        f, frs, ref = locate(x)
        for t0, period, sign, r in frs:
            v = sign * DM.interp(f, t0 + np.arange(192) * period)
            a, b = np.polyfit(ref[r], v, 1)       # with all the symbols known: the best scale and offset
            a0, b0 = np.polyfit(DM.FSW_SYMBOLS, v[:10], 1)   # what the demodulator does (FSW only)
            q = slice4((v - b0) / a0)
            e = q != ref[r]
            pos += e
            cnt += 1
            for s, g in zip(ref[r], q):
                conf[idx[int(s)], idx[int(g)]] += 1
            resid.append(((v - b) / a - ref[r]))
            print('%s frame %d: errors %3d   FSW fit a %.0f b %+.0f   all-symbol fit a %.0f b %+.0f   rms noise %.2f' % (
                os.path.basename(p)[:7], r, e.sum(), a0, b0, a, b, np.std((v - b) / a - ref[r])))
    print('errors by position (16 groups of 12 symbols): %s' % ' '.join('%d' % pos[i:i + 12].sum() for i in range(0, 192, 12)))
    for lv in (3, 1, -1, -3):
        row = conf[idx[lv]]
        print('sent %+d -> %s' % (lv, '  '.join('%+d %5.1f%%' % (y, 100 * row[idx[y]] / row.sum()) for y in (3, 1, -1, -3))))
    rs = np.concatenate(resid)
    print('noise after the best per-frame scale/offset: rms %.3f (level spacing 2)' % rs.std())


def design(paths, taps):
    """rows: the 24 kHz samples around each symbol time (taps of them, centred, by linear interpolation), a constant;
    target: the symbol sent"""
    rows, tgt = [], []
    half = (taps - 1) / 2
    for p in paths:
        x = prepare(p)
        f, frs, ref = locate(x)
        for t0, period, sign, r in frs:
            t = t0 + np.arange(192) * period
            m = np.array([sign * DM.interp(x, t + j - half) for j in range(taps)]).T
            # per-frame offset left to the constant column of this frame: the scale is fixed (FM deviation)
            rows.append(m)
            tgt.append(ref[r])
    return rows, tgt


def fit(train, test, taps):
    rows, tgt = design(train, taps)
    # one filter for all, an offset per frame
    nf = len(rows)
    A = np.zeros((nf * 192, taps + nf))
    for i, m in enumerate(rows):
        A[i * 192:(i + 1) * 192, :taps] = m
        A[i * 192:(i + 1) * 192, taps + i] = 1
    h, *_ = np.linalg.lstsq(A, np.concatenate(tgt), rcond=None)
    h = h[:taps]
    np.save(os.path.join(DATA, 'af_eq_h.npy'), h)
    print('filter (%d taps): %s' % (taps, ' '.join('%.3f' % v for v in h / np.abs(h).max())))
    for name, paths in (('train', train), ('test', test)):
        rows, tgt = design(paths, taps)
        e_fsw = e_ideal = n = 0
        for m, rf in zip(rows, tgt):
            v = m @ h
            b = np.mean(v[:10] - DM.FSW_SYMBOLS)          # offset from the FSW only, as the radio would
            e_fsw += np.sum(slice4(v - b) != rf)
            e_ideal += np.sum(slice4(v - np.mean(v - rf)) != rf)
            n += 192
        print('%s: %d frames, symbol errors %.2f %% (offset from the FSW), %.2f %% (best offset)' % (
            name, len(rows), 100 * e_fsw / n, 100 * e_ideal / n))


def expand(specs):
    out = []
    for s in specs:
        out += sorted(glob.glob(s if os.path.sep in s or '/' in s else os.path.join(DATA, s + '.af.npy')))
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    a = sub.add_parser('analyse')
    a.add_argument('paths', nargs='+')
    f = sub.add_parser('fit')
    f.add_argument('--train', nargs='+')
    f.add_argument('--test', nargs='+')
    f.add_argument('--taps', type=int, default=31)
    args = ap.parse_args()
    if args.cmd == 'analyse':
        analyse(expand(args.paths))
    else:
        fit(expand(args.train), expand(args.test), args.taps)


if __name__ == '__main__':
    main()
