"""Radio to radio over the air, the cables quiet while the transmitter is on (its RF upsets the other radio's cable):
the receiver's physical layer capture armed first, then the transmitter's test (P25, or the NXDN loop of
radio_tx.py), then wait until it is over, then read the capture back.

  python nxdn/py/radio_pair.py out_name --p25                        P25 test call, P25 sync
  python nxdn/py/radio_pair.py out_name --frames f.txt --sync HEX    the frames in a loop, that sync
         [--rx COM22] [--tx COM23] [--seconds 4] [--blocks 160] [--gain 26] [--threshold 0978786F]
"""
import argparse
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402

ELF = os.path.join(ROOT, 'src', 'build', 'opendmr.elf')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('name')
    ap.add_argument('--rx', default='COM22')
    ap.add_argument('--tx', default='COM23')
    ap.add_argument('--p25', action='store_true')
    ap.add_argument('--frames')
    ap.add_argument('--sync')
    ap.add_argument('--dibits', help='raw dibits (0 - 3, one a byte) to loop instead of --frames')
    ap.add_argument('--seconds', type=float, default=4)
    ap.add_argument('--blocks', type=int, default=160)
    ap.add_argument('--gain', default=None)
    ap.add_argument('--threshold', default=None)
    ap.add_argument('--rfmode', default=None, help='RF_MODE for the capture, hex (DM-32: 03269860)')
    a = ap.parse_args()
    sym = Symbols(ELF)

    rx = Radio(a.rx)
    if a.gain:
        g = rx.value_read(0x11000104, 4)
        rx.value_write(0x11000104, 4, (g & ~0xFF0000) | (int(a.gain, 16) << 16))
    if a.threshold:
        rx.value_write(0x11000120, 4, int(a.threshold, 16))
    rf_saved = rx.value_read(0x11000104, 4)
    if a.rfmode:
        rx.value_write(0x11000104, 4, int(a.rfmode, 16))
    saved = [rx.value_read(x, 4) for x in (0x1100013C, 0x11000140, 0x11000144, 0x11000148)]
    if a.sync:
        v = int(a.sync, 16)
        for h, l in ((0x1100013C, 0x11000140), (0x11000144, 0x11000148)):
            rx.value_write(h, 4, 0x80000000 | (v >> 24))
            rx.value_write(l, 4, v & 0xFFFFFF)
    r = rx.call(sym.resolve('p25_phy_capture'), [1 if a.p25 else 0, a.blocks])
    if r != 0:
        raise SystemExit('capture: %d' % r)
    rx.p.close()

    # the transmitter's VFO frequency typed in again first: the physical layer test transmissions leave it worse each
    # time (after a few, nothing the receiver can lock on); a retune puts it right (2026-11-17; radio_set_channel()
    # over the cable with the same channel does not)
    from radio import Radio as UI
    ui = UI(a.tx)
    ui.home()
    ui.key('up', mod='sk2', settle=0.2)
    ui.keys(*ui.state()['rx'].rjust(8, '0'), settle=0.12)
    time.sleep(0.4)
    ui.close()
    tx = Radio(a.tx)
    if a.p25:
        res = tx.call(sym.resolve('p25_phy_tx_test'), [1000, int(a.seconds * 1000), 0])
    else:
        frames = []
        for line in (open(a.frames) if a.frames else []):
            p = line.split()
            if len(p) >= 3 and p[0] == 'NXDN':
                frames.append(bytes((c >> (6 - 2 * i)) & 3 for c in bytes.fromhex(p[2]) for i in range(4)))
        data = open(a.dibits, 'rb').read() if a.dibits else b''.join(frames)
        buf = sym.resolve('p25_phy_tx_loop')
        for i in range(0, len(data), 128):
            tx.mem_write_bytes(buf + i, data[i:i + 128])
        tx.value_write(sym.resolve('p25_phy_tx_loop_len'), 4, len(data))
        res = tx.call(sym.resolve('p25_phy_tx_test'), [1000, int(a.seconds * 1000), 1])
    tx.p.close()
    if res != 0:
        raise SystemExit('tx test: %d' % res)
    time.sleep(1 + a.seconds + 1.5)                 # quiet cables while it sends

    tx = Radio(a.tx)
    state = struct.unpack('<I', tx.mem_read(sym.resolve('p25_phy_tx_state'), 4))[0]
    blocks_sent = struct.unpack('<I', tx.mem_read(sym.resolve('p25_phy_tx_blocks'), 4))[0]
    tx.p.close()
    rx = Radio(a.rx)
    n = struct.unpack('<I', rx.mem_read(sym.resolve('p25_phy_count'), 4))[0]
    rx.call(sym.resolve('p25_phy_stop'), [])
    raw = b''
    buf = sym.resolve('p25_phy_buf')
    while len(raw) < n * 88:
        raw += rx.mem_read(buf + len(raw), min(256, n * 88 - len(raw)))
    for x, v in zip((0x1100013C, 0x11000140, 0x11000144, 0x11000148), saved):
        rx.value_write(x, 4, v)                     # the DMR syncs back
    if a.gain:
        g = rx.value_read(0x11000104, 4)
        rx.value_write(0x11000104, 4, (g & ~0xFF0000) | (0x26 << 16))
    if a.threshold:
        rx.value_write(0x11000120, 4, 0x0978786F)
    if a.rfmode:
        rx.value_write(0x11000104, 4, rf_saved)
    rx.p.close()
    out = os.path.join(ROOT, 'nxdn', 'data', 'radio', a.name)
    open(out + '.bin', 'wb').write(raw)
    print('tx state %d, %d blocks sent; rx %d blocks -> %s.bin' % (state, blocks_sent, n, out))
    if n:
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'analyse', out + '.bin',
                        '--dibits', out + '.dibits'])


if __name__ == '__main__':
    main()
