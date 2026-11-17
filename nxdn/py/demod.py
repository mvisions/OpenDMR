"""NXDN from an IQ recording (stereo wav: I, Q): FM discriminator, symbol timing, 4-level symbols, and the frame sync
words (FSW, NXDN TS 1-A 4.4.4: 10 symbols, 0xCDF59) in the symbol stream. A frame is 384 bits = 192 symbols (80 ms
at 4800 bps / NXDN48, 40 ms at 9600 bps / NXDN96).

  python nxdn/py/demod.py "nxdn/data/iq/NXDN48 IQ.wav" 2400
  python nxdn/py/demod.py "nxdn/data/iq/NXDN96 IQ.wav" 4800

Writes <wav>.frames.npy: each frame's 192 symbols (about +-3, each frame timed and levelled on its FSW).
"""
import sys
import wave

import numpy as np

FSW_SYMBOLS = np.array([-3, 1, -3, 3, -3, -3, 3, 3, -1, 3], float)  # TS 1-A Table 4.4-2
FRAME_SYMBOLS = 192


def read_iq(path):
    w = wave.open(path)
    fs = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float).reshape(-1, 2)
    return fs, d[:, 0] + 1j * d[:, 1]


def lowpass(x, fs, cutoff, taps=95):
    t = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff / fs * t) * np.hamming(taps)
    return np.convolve(x, h / h.sum(), 'same')


def discriminator(fs, iq, baud):
    iq = lowpass(iq, fs, baud * 1.5)                 # the channel (6.25 / 12.5 kHz)
    f = np.angle(iq[1:] * np.conj(iq[:-1])) * fs / (2 * np.pi)   # Hz
    return lowpass(f, fs, baud * 0.6)


def norm_corr(s, ref):
    """Normalised correlation of every window of s with ref (-1 .. 1), the window's mean removed"""
    n = len(ref)
    r = (ref - ref.mean()) / np.linalg.norm(ref - ref.mean())
    win = np.lib.stride_tricks.sliding_window_view(s, n)
    win = win - win.mean(axis=1, keepdims=True)
    return (win @ r) / (np.linalg.norm(win, axis=1) + 1e-9)


def demod(path, baud):
    fs, iq = read_iq(path)
    f = discriminator(fs, iq, baud)
    sps = fs / baud
    best = None
    for phase in np.arange(0, sps, sps / 20):
        idx = (phase + np.arange(int((len(f) - phase - 1) / sps)) * sps).astype(int)
        s = f[idx]
        for sign in (1, -1):
            c = norm_corr(sign * s, FSW_SYMBOLS)
            hits = np.where(c > 0.9)[0]
            # hits closer than a frame: the best one only
            keep = []
            for h in hits:
                if keep and h - keep[-1] < FRAME_SYMBOLS // 2:
                    if c[h] > c[keep[-1]]:
                        keep[-1] = h
                    continue
                keep.append(h)
            score = sum(1 for a, b in zip(keep, keep[1:]) if (b - a) % FRAME_SYMBOLS in (0, 1, FRAME_SYMBOLS - 1))
            if best is None or score > best[0]:
                best = (score, phase, sign, np.array(keep), sign * s, c)
    score, phase, sign, hits, s, c = best
    # the levels: +-3 from the outer symbols of the FSWs found
    if len(hits):
        fsw = np.array([s[h:h + 10] for h in hits])
        outer = np.mean(np.abs(fsw[:, FSW_SYMBOLS.__abs__() == 3]))
        s = s * 3 / outer
    return dict(fs=fs, sps=sps, phase=phase, sign=sign, hits=hits, symbols=s, deviation=outer if len(hits) else 0)


def interp(f, t):
    """f at the fractional sample times t (linear)"""
    i = np.floor(t).astype(int)
    i = np.clip(i, 0, len(f) - 2)
    a = t - i
    return f[i] * (1 - a) + f[i + 1] * a


def frames(f, sps, phase, sign, hits):
    """Each frame sampled on its own: the FSW's start found to 1/16 symbol around the coarse hit, the symbol period
    from the distance to the next FSW (when it is the next frame), levels and offset fitted on the 10 FSW symbols.
    -> (n, 192) symbols, about +-3"""
    k = np.arange(10)
    starts = []
    for h in hits:
        t0 = phase + h * sps
        best = None
        for d in np.arange(-sps / 2, sps / 2, sps / 16):
            v = sign * interp(f, t0 + d + k * sps)
            c = np.corrcoef(v, FSW_SYMBOLS)[0, 1]
            if best is None or c > best[0]:
                best = (c, t0 + d)
        starts.append(best[1])
    out = []
    for i, t0 in enumerate(starts):
        period = sps
        if i + 1 < len(starts) and abs((starts[i + 1] - t0) - FRAME_SYMBOLS * sps) < sps:
            period = (starts[i + 1] - t0) / FRAME_SYMBOLS
        v = sign * interp(f, t0 + np.arange(FRAME_SYMBOLS) * period)
        a, b = np.polyfit(FSW_SYMBOLS, v[:10], 1)          # v = a * ideal + b
        out.append((v - b) / a)
    return np.array(out)


def main():
    path, baud = sys.argv[1], float(sys.argv[2])
    r = demod(path, baud)
    fs, iq = read_iq(path)
    fr = frames(discriminator(fs, iq, baud), r['sps'], r['phase'], r['sign'], r['hits'])
    np.save(path + '.frames.npy', fr)
    hits = r['hits']
    print('%s\n  %d symbols/s, %.1f samples a symbol, timing phase %.1f, %s, %d FSW, +3 at %.0f Hz' % (
        path, baud, r['sps'], r['phase'], 'normal' if r['sign'] > 0 else 'inverted', len(hits), r['deviation']))
    if len(hits) > 1:
        gaps, counts = np.unique(np.diff(hits), return_counts=True)
        print('  FSW spacing (symbols): %s' % ', '.join('%d x%d' % gc for gc in zip(gaps, counts)))
        print('  first FSW at symbol %d (%.2f s): %s' % (hits[0], hits[0] / baud,
                                                         ' '.join('%+.1f' % v for v in r['symbols'][hits[0]:hits[0] + 10])))


if __name__ == '__main__':
    main()
