"""The frequency response of the FM receive recording (af_capture.py): the other radio sends FM tones
(radio_tx_signal + radio_transmit_plain, on its VFO, both radios on the same UHF frequency), this radio records them
under each FM_BANDWIDTH; the tone's level (its FFT bin) per frequency.

  python nxdn/py/fm_response.py [--tones 100 200 ...] [--bws 0F 1F 4F 5F]
"""
import argparse
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402


def level(x, f0):
    x = x - x.mean()
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / 8000)
    m = (f > f0 - 15) & (f < f0 + 15)
    return 10 * np.log10(X[m].sum() + 1), 100 * X[m].sum() / X.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tones', nargs='+', type=int, default=[100, 200, 300, 500, 800, 1200, 1800, 2400])
    ap.add_argument('--bws', nargs='+', default=['0F', '1F', '4F', '5F'])
    ap.add_argument('--rx', default='COM22')
    ap.add_argument('--tx', default='COM23')
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    table = {}
    for t in a.tones:
        tx = Radio(a.tx)
        tx.call(sym.resolve('radio_tx_signal'), [t, 0])
        tx.call(sym.resolve('radio_transmit_plain'), [])
        tx.p.close()
        time.sleep(1.2)
        try:
            for bw in a.bws:
                name = 'resp_%d_%s' % (t, bw)
                subprocess.run([sys.executable, os.path.join(HERE, 'af_capture.py'), name, '--bw', bw, '--port', a.rx,
                                '--halves', '12'], capture_output=True)
                table[(t, bw)] = level(np.load(os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.af.npy')), t)
        finally:
            tx = Radio(a.tx)
            tx.call(sym.resolve('radio_transmit'), [0])
            tx.call(sym.resolve('radio_tx_signal'), [0, 0])
            tx.p.close()
        time.sleep(0.5)
    print('tone Hz  ' + '  '.join('%-16s' % ('FM_BW ' + bw) for bw in a.bws))
    for t in a.tones:
        print('%6d   ' % t + '  '.join('%5.1f dB (%3.0f %%)  ' % table[(t, bw)] for bw in a.bws))


if __name__ == '__main__':
    main()
