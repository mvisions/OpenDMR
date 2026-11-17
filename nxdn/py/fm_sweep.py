"""The FM receive recording (af_capture.py) under FM_BANDWIDTH / fm_dev_coef_r settings, the radio in FM with the
FD6818 flat (0x2B 0x0700) and unmuted: the signal band (100 - 1200 Hz) against the noise band (2 - 4 kHz), the
distinct sample values, and what af_demod.py finds.

  python nxdn/py/fm_sweep.py --bws 5F 4F 1F 0F --coefs 0A 20 40
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bws', nargs='+', default=['5F'])
    ap.add_argument('--coefs', nargs='+', default=['0A'])
    ap.add_argument('--port', default='COM22')
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    r.call(sym.resolve('fd6818_write'), [0x2B, 0x0700])
    r.call(sym.resolve('fd6818_write'), [0x47, 0x6142])
    saved = r.value_read(0x11000504, 4)
    r.p.close()
    for c in a.coefs:
        for bw in a.bws:
            r = Radio(a.port)
            r.value_write(0x11000504, 4, (saved & ~0xFF00) | (int(c, 16) << 8))
            r.p.close()
            name = 'fs_%s_%s' % (bw, c)
            subprocess.run([sys.executable, os.path.join(HERE, 'af_capture.py'), name, '--bw', bw, '--port', a.port],
                           capture_output=True)
            x = np.load(os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.af.npy'))
            X = np.abs(np.fft.rfft((x - x.mean()) * np.hanning(len(x)))) ** 2
            f = np.fft.rfftfreq(len(x), 1 / 8000)
            sig = X[(f >= 100) & (f < 1200)].mean()
            noise = X[(f >= 2000) & (f < 4000)].mean()
            d = subprocess.run([sys.executable, os.path.join(HERE, 'af_demod.py'),
                                os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.af.npy')],
                               capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
            m = re.search(r'(\d+) FSWs, (\d+) a frame apart', d)
            fr = re.search(r'frames (\d+): LICH ok (\d+), SACCH CRC ok (\d+), VCH = 1031 Hz vector (\d+) of (\d+)', d)
            print('FM_BANDWIDTH %s coef %s: std %5.0f, %3d values, signal/noise band %5.1f dB;  FSW %s;  %s' % (
                bw, c, x.std(), len(np.unique(x)), 10 * np.log10(sig / (noise + 1e-9)),
                '%s (%s a frame apart)' % m.groups() if m else '-',
                'LICH %s SACCH %s VCH %s/%s' % fr.groups()[1:] if fr else ''), flush=True)
    r = Radio(a.port)
    r.value_write(0x11000504, 4, saved)
    r.p.close()


if __name__ == '__main__':
    main()
