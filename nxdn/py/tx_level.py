"""The deviation as the receiver's discriminator sees it: the receiver's recording (nxdn_radio.c nxdn_tap, 2048
samples, 256 ms) frozen and its level measured: the +-3 level from a fit of each FSW found (as nxdn_core.c), and
percentiles of |x|. The same receiver for the hotspot's NXDN48 (the reference: +3 = 1050 Hz) and ours, so the ratio
is the deviation's.

  python nxdn/py/tx_level.py listen [--times 5]            what is on the air now (e.g. the hotspot transmitting)
  python nxdn/py/tx_level.py dev 553 800 1024 ...          our transmitter (COM23) keyed with each nxdn_tx_dev
  python nxdn/py/tx_level.py bias 0x4343 0x2424 ...        ... with RF_MOD_BIAS_CTRL's low half written while keyed
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
import dm32dbg  # noqa: E402
import radio  # noqa: E402

REG = 0x11000114
FSW = np.array([-3, 1, -3, 3, -3, -3, 3, 3, -1, 3], float)
SPS = 8000 / 2400


def grab(port, sym):
    r = dm32dbg.Radio(port)
    r.value_write(sym.resolve('nxdn_tap_source'), 4, 0)
    r.value_write(sym.resolve('nxdn_tap_hold'), 4, 1)
    base = sym.resolve('nxdn_tap')
    raw = b''.join(r.mem_read(base + i, 512) for i in range(0, 4096, 512))
    n = r.value_read(sym.resolve('nxdn_tap_n'), 4)
    r.value_write(sym.resolve('nxdn_tap_hold'), 4, 0)
    r.p.close()
    x = np.frombuffer(raw, '<i2').astype(float)
    k = n % 2048
    return np.r_[x[k:], x[:k]]  # oldest first


def level(x):
    """the +-3 level: the best FSW fits (normalised correlation over 0.9) at 1/3-sample steps, their slope"""
    t = np.arange(len(x))
    fits = []
    i = 0.0
    while i + 10 * SPS + 2 < len(x):
        v = np.interp(i + np.arange(10) * SPS, t, x)
        v = v - v.mean()
        e = np.sqrt((v * v).sum() * (FSW * FSW).sum())
        c = (v * FSW).sum() / e if e > 0 else 0
        if abs(c) > 0.9:
            fits.append((abs(c), abs((v * FSW).sum() / (FSW * FSW).sum()) * 3, c > 0))
        i += 1 / 3
    if not fits:
        return None, None
    fits.sort(reverse=True)
    best = fits[0]
    return best[1], best[2]


def report(name, x):
    x = x - np.median(x)
    lv, pos = level(x)
    p = np.percentile(np.abs(x), [50, 90, 99])
    print('%-14s +3 level %s (%s)  |x| p50 %5.0f p90 %5.0f p99 %5.0f' %
          (name, '%6.0f' % lv if lv else '  none', '' if lv is None else ('normal' if pos else 'inverted'), *p),
          flush=True)


def keyed(a, sym, before, during):
    t = dm32dbg.Radio(a.tx)
    before(t)
    t.p.close()
    k = radio.Radio(a.tx)
    k.ptt(True)
    time.sleep(0.8)
    k.close()
    t = dm32dbg.Radio(a.tx)
    during(t)
    reg = t.value_read(REG, 4)
    t.p.close()
    time.sleep(0.5)
    x = grab(a.rx, sym)
    k = radio.Radio(a.tx)
    k.ptt(False)
    k.close()
    time.sleep(1.5)
    return reg, x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['listen', 'dev', 'bias'])
    ap.add_argument('values', nargs='*')
    ap.add_argument('--tx', default='COM23')
    ap.add_argument('--rx', default='COM22')
    ap.add_argument('--times', type=int, default=3)
    a = ap.parse_args()
    sym = dm32dbg.Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    if a.what == 'listen':
        for i in range(a.times):
            report('on air %d' % i, grab(a.rx, sym))
            time.sleep(0.4)
        return
    for v in a.values:
        if a.what == 'dev':
            reg, x = keyed(a, sym, lambda t: t.value_write(sym.resolve('nxdn_tx_dev'), 4, int(v)), lambda t: None)
        else:
            def during(t):
                r = t.value_read(REG, 4)
                t.value_write(REG, 4, (r & 0xFFFF0000) | int(v, 0))
            reg, x = keyed(a, sym, lambda t: None, during)
        report('%s %s 0x%04X' % (a.what, v, reg & 0xFFFF), x)


if __name__ == '__main__':
    main()
