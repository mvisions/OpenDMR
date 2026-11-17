"""The HR_C7000's FM receive recording (the AF input, 8 kHz, 16 bit) read from the radio while the hotspot sends NXDN48:
firmware nxdn_af_capture() (p25_phy.c) copies the halves of the RX RAM recording into p25_phy_buf; this reads them back,
puts them in order (FM_ADDR_SW log) and writes a wav and the raw samples.

  python nxdn/py/af_capture.py name [--bw 0F] [--work-mode 80] [--halves 27]
  (the radio on a DMR VFO at the hotspot's frequency, eco off; the hotspot already sending)
"""
import argparse
import os
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--bw', default='0F', help='FM_BANDWIDTH meanwhile (normal 5F: bit 6 the band-pass, bit 4 pre-emphasis)')
    ap.add_argument('--work-mode', default='80')
    ap.add_argument('--halves', type=int, default=27)
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    n = r.call(sym.resolve('nxdn_af_capture'), [a.halves, int(a.bw, 16), int(a.work_mode, 16)])
    if n <= 0:
        raise SystemExit('capture: %d' % n)
    raw = b''
    buf = sym.resolve('p25_phy_buf')
    while len(raw) < n * 512:
        raw += r.mem_read(buf + len(raw), min(256, n * 512 - len(raw)))
    log = r.mem_read(sym.resolve('nxdn_af_sw_log'), n)
    r.p.close()
    x = np.frombuffer(raw, '>i2').astype(float)   # big endian (a 1 kHz tone: 80 % pure, little endian 13 %)
    out = os.path.join(ROOT, 'nxdn', 'data', 'radio', a.name)
    np.save(out + '.af.npy', x)
    with wave.open(out + '.af.wav', 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(x.astype('<i2').tobytes())
    print('%d halves (%d samples, %.2f s); FM_ADDR_SW log %s' % (n, len(x), len(x) / 8000, list(log[:12])))
    print('samples: mean %.0f, std %.0f, min %.0f, max %.0f' % (x.mean(), x.std(), x.min(), x.max()))
    # the jumps at the joins of the halves: small if the halves follow each other
    joins = [abs(x[k * 256] - x[k * 256 - 1]) for k in range(1, n)]
    inner = np.abs(np.diff(x)).mean()
    print('mean step inside %.0f, at the joins %.0f' % (inner, np.mean(joins)))


if __name__ == '__main__':
    main()
