"""NXDN48 from discriminator audio (8 kHz, as the radio's FM recording gives it, af_capture.py): resampled to 24 kHz
(10 samples a symbol), optionally the DC blocked, low-passed, FSWs searched in every timing phase and both polarities,
each frame timed and levelled on its FSW (demod.frames()), then decoded (frames.py: LICH, SACCH, VCH) and compared with
the frames sent.

  python nxdn/py/af_demod.py nxdn/data/radio/af_5F.af.npy [--reference frames.txt]
"""
import argparse
import os
import sys

import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demod as DM  # noqa: E402
import frames as F  # noqa: E402
import l2  # noqa: E402

FS = 24000
BAUD = 2400


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('npy')
    ap.add_argument('--reference')
    ap.add_argument('--tau', type=float, default=0.0, help='undo a de-emphasis of this time constant, us (0: none)')
    ap.add_argument('--hpf', type=float, default=0.0, help='undo a first-order high-pass of this corner, Hz (0: none)')
    ap.add_argument('--wander', type=float, default=0.0, help='remove the baseline wander: high-pass at this, Hz (0: none)')
    a = ap.parse_args()
    x = np.load(a.npy)
    x = x - np.mean(x)
    if a.tau > 0:                                    # de-emphasis 1 / (1 + s tau): undone by 1 + s tau
        t = a.tau * 1e-6 * 8000
        x = x + t * np.r_[0, np.diff(x)]
    if a.hpf > 0:                                    # high-pass s / (s + w): undone by adding w * the integral (leaky)
        w = 2 * np.pi * a.hpf / 8000
        acc = 0.0
        y = np.empty_like(x)
        for i, v in enumerate(x):
            acc = acc * (1 - w / 50) + v
            y[i] = v + w * acc
        x = y - np.mean(y)
    if a.wander > 0:
        from scipy.signal import butter, filtfilt
        b, c = butter(2, a.wander / 4000, 'high')
        x = filtfilt(b, c, x)
    x = resample_poly(x, 3, 1)                       # 8 kHz -> 24 kHz
    f = DM.lowpass(x, FS, BAUD * 0.6)
    sps = FS / BAUD
    best = None
    for sign in (1, -1):
        for phase in np.arange(0, sps, sps / 20):
            idx = (phase + np.arange(int((len(f) - phase - 1) / sps)) * sps).astype(int)
            s = sign * f[idx]
            c = DM.norm_corr(s, DM.FSW_SYMBOLS)
            hits = [h for h in np.where(c > 0.85)[0]]
            keep = []
            for h in hits:
                if keep and h - keep[-1] < 96:
                    if c[h] > c[keep[-1]]:
                        keep[-1] = h
                    continue
                keep.append(h)
            score = sum(1 for p, q in zip(keep, keep[1:]) if (q - p) % 192 in (0, 1, 191))
            if best is None or score > best[0]:
                best = (score, phase, sign, np.array(keep))
    score, phase, sign, hits = best
    print('%s: %d FSWs, %d a frame apart; phase %.1f, %s' % (os.path.basename(a.npy), len(hits), score, phase,
                                                            'normal' if sign > 0 else 'inverted'))
    if len(hits) == 0:
        return
    hits = hits[phase + (hits + 192) * sps < len(f) - 1]   # whole frames only (the recording ends inside the last)
    fr = DM.frames(sign * f, sps, phase, 1, hits)
    if a.reference:
        from chip import reference_frames
        ref = reference_frames(a.reference)
        q = np.where(fr >= 2, 3, np.where(fr >= 0, 1, np.where(fr > -2, -1, -3)))
        g, e = [], []
        for row in q:
            k = int(np.argmax([np.sum(np.sign(row) == np.sign(rf)) for rf in ref]))
            g.append(row)
            e.append(ref[k])
        g = np.concatenate(g)
        e = np.concatenate(e)
        print('against the frames sent: sign errors %.1f %%, magnitude errors %.1f %%' % (
            100 * np.mean(np.sign(g) != np.sign(e)), 100 * np.mean((np.abs(g) == 3) != (np.abs(e) == 3))))
    out = F.frames(fr, 0)
    ok = {'lich': 0, 'sacch': 0, 'vch': 0}
    for fx in out:
        sr, data, good = l2.sacch(fx['payload'][F.LICH:F.LICH + F.SACCH])
        ok['lich'] += fx['lich_ok']
        ok['sacch'] += good
        ok['vch'] += sum(1 for v in fx['vch'] if l2.to_bytes(v).hex() == 'cea8fe83acc458200a')
        print('  LICH %s %-22s SACCH SR %02X %s  VCH %s' % (format(fx['lich'], '07b'), F.LICH_NAMES.get(fx['lich'], '?'),
                                                            sr, 'ok ' if good else 'BAD',
                                                            l2.to_bytes(fx['vch'][0]).hex()))
    print('frames %d: LICH ok %d, SACCH CRC ok %d, VCH = 1031 Hz vector %d of %d' % (
        len(out), ok['lich'], ok['sacch'], ok['vch'], 4 * len(out)))


if __name__ == '__main__':
    main()
