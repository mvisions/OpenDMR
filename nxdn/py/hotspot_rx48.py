"""NXDN48 from the Pi-Star hotspot into the radio's physical layer, locked on the preamble: the capture armed first
(gain RF_MODE[23:16], sync pattern, threshold), then the hotspot starts transmitting (pistar-signal-gen p25tx-ctl), so
the preamble at the start of its transmission is there to lock on; then the capture is read and analysed (chip.py).

  python nxdn/py/hotspot_rx48.py name [--sync HEX] [--gain 36] [--tx 439000360] [--file 1031Hz_test_nxdn.txt]
  (PISTAR_HOST / PISTAR_PASS in the environment; the radio on 439.000 MHz, a DMR VFO)
"""
import argparse
import os
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
import pi  # noqa: E402
from dm32dbg import Radio, Symbols  # noqa: E402

PREAMBLE = [3, 3, 3, -3, 3, -3, 3, 3, -3, -3, -3, 3]   # 0x5775FD, TS 1-A Table 4.4-1
D = {3: 1, 1: 0, -1: 2, -3: 3}


def doubled(symbols):
    v = 0
    for s in symbols:
        for _ in range(2):
            v = (v << 2) | D[s]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--sync', default='%012X' % doubled(PREAMBLE))
    ap.add_argument('--gain', default='36')
    ap.add_argument('--threshold', default=None)
    ap.add_argument('--tx', type=int, default=439000360)
    ap.add_argument('--file', default='1031Hz_test_nxdn.txt')
    ap.add_argument('--blocks', type=int, default=160)
    ap.add_argument('--gap', type=int, default=1, help='seconds off air between plays: each play starts with a preamble')
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop 2>&1" % pw)
    time.sleep(2)

    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    g = r.value_read(0x11000104, 4)
    r.value_write(0x11000104, 4, (g & ~0xFF0000) | (int(a.gain, 16) << 16))
    if a.threshold:
        r.value_write(0x11000120, 4, int(a.threshold, 16))
    saved = [r.value_read(x, 4) for x in (0x1100013C, 0x11000140, 0x11000144, 0x11000148)]
    v = int(a.sync, 16)
    for h, l in ((0x1100013C, 0x11000140), (0x11000144, 0x11000148)):
        r.value_write(h, 4, 0x80000000 | (v >> 24))
        r.value_write(l, 4, v & 0xFFFFFF)
    if r.call(sym.resolve('p25_phy_capture'), [0, a.blocks]) != 0:
        raise SystemExit('capture busy')
    print('armed: sync %s, gain 0x%s; the hotspot starts on %.6f MHz' % (a.sync, a.gain, a.tx / 1e6), flush=True)
    print(pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl start %s %d 1 %d 60 2>&1" % (pw, a.file, a.tx, a.gap)).strip())
    n = 0
    end = time.time() + 25
    while time.time() < end:
        time.sleep(1)
        n = struct.unpack('<I', r.mem_read(sym.resolve('p25_phy_count'), 4))[0]
        if n >= a.blocks:
            break
    r.call(sym.resolve('p25_phy_stop'), [])
    raw = b''
    buf = sym.resolve('p25_phy_buf')
    while len(raw) < n * 88:
        raw += r.mem_read(buf + len(raw), min(256, n * 88 - len(raw)))
    for x, val in zip((0x1100013C, 0x11000140, 0x11000144, 0x11000148), saved):
        r.value_write(x, 4, val)
    g = r.value_read(0x11000104, 4)
    r.value_write(0x11000104, 4, (g & ~0xFF0000) | (0x26 << 16))
    r.value_write(0x11000120, 4, 0x0978786F)
    r.p.close()
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop 2>&1" % pw)
    out = os.path.join(ROOT, 'nxdn', 'data', 'radio', a.name)
    open(out + '.bin', 'wb').write(raw)
    print('%d blocks -> %s.bin' % (n, out))
    if n:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'analyse', out + '.bin',
                        '--dibits', out + '.dibits'], capture_output=True)


if __name__ == '__main__':
    main()
