"""NXDN96 from a radio: frames (pistar-signal-gen text "NXDN 48 <hex>", 192 symbols each) into the firmware's
p25_phy_tx_loop over the cable, then the physical layer transmit test in loop mode (src/services/p25_phy.h): the
radio sends them again and again at 4800 symbols/s (the modem's own rate; its deviation, +3 = 1944 Hz, not NXDN96's
2400 Hz) at 50 mW on its channel's Tx frequency.

  python nxdn/py/radio_tx.py frames.txt --port COM23 [--seconds 20] [--delay 1]
  python nxdn/py/radio_tx.py frames.txt --sync      the 48-bit sync of the first frame (FSW, LICH, 6 SACCH symbols)
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))

DIBIT = {3: 0b01, 1: 0b00, -1: 0b10, -3: 0b11}


def load(path):
    out = []
    for line in open(path):
        p = line.split()
        if len(p) >= 3 and p[0] == 'NXDN':
            b = bytes.fromhex(p[2])
            out.append([(c >> (6 - 2 * i)) & 3 for c in b for i in range(4)])   # dibits, first first
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('frames')
    ap.add_argument('--port', default='COM23')
    ap.add_argument('--seconds', type=float, default=20)
    ap.add_argument('--delay', type=float, default=1)
    ap.add_argument('--sync', action='store_true', help='print the sync pattern only')
    ap.add_argument('--elf', default=os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    a = ap.parse_args()
    frames = load(a.frames)
    if a.sync:
        v = 0
        for d in frames[0][:24]:
            v = (v << 2) | d
        print('%012X' % v)
        return
    from dm32dbg import Radio, Symbols
    sym = Symbols(a.elf)
    r = Radio(a.port)
    data = bytes(d for f in frames for d in f)
    if len(data) > 768:
        raise SystemExit('at most 4 frames')
    buf = sym.resolve('p25_phy_tx_loop')
    for i in range(0, len(data), 128):
        r.mem_write_bytes(buf + i, data[i:i + 128])
    if r.mem_read(buf, len(data)) != data:
        raise SystemExit('the loop buffer did not take')
    r.value_write(sym.resolve('p25_phy_tx_loop_len'), 4, len(data))
    res = r.call(sym.resolve('p25_phy_tx_test'), [int(a.delay * 1000), int(a.seconds * 1000), 1])
    if res != 0:
        raise SystemExit('p25_phy_tx_test: %d (busy?)' % res)
    print('%s: %d frames (%d dibits) again and again from %.1f s for %.0f s' % (a.port, len(frames), len(data),
                                                                             a.delay, a.seconds))


if __name__ == '__main__':
    main()
