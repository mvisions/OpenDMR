"""NXDN transmit with two radios: the transmitter keyed over the cable (radio.py, the PTT) for a few seconds, the
receiver's NXDN counters (nxdn_radio_stats) and its call compared before and after; the transmitter's counters
(nxdn_tx_stats: calls, frames, encoder frames, underruns) after.

  python nxdn/py/tx_test.py [--tx COM23] [--rx COM22] [--seconds 3] [--set name=value ...]

--set writes variables of the transmitter first (e.g. nxdn_tx_low_power=1 nxdn_tx_dev=553 nxdn_tx_source=1).
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
import dm32dbg  # noqa: E402
import radio  # noqa: E402

NAMES = ('halves missed_halves frames lich_bad sacch_ok vch facch_ok hunts lost_sync pcm_drops underruns calls '
         'busy_max_us dec_us_max dec_us_sum demod_us_sum feed_writes').split()


def stats(r, sym):
    v = struct.unpack('<%dI' % len(NAMES), r.mem_read(sym.resolve('nxdn_radio_stats'), 4 * len(NAMES)))
    return dict(zip(NAMES, v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tx', default='COM23')
    ap.add_argument('--rx', default='COM22')
    ap.add_argument('--seconds', type=float, default=3.0)
    ap.add_argument('--set', nargs='*', default=[])
    a = ap.parse_args()
    sym = dm32dbg.Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))

    t = dm32dbg.Radio(a.tx)
    for kv in a.set:
        name, value = kv.split('=')
        t.value_write(sym.resolve(name), 4, int(value, 0))
        print('%s = %d' % (name, t.value_read(sym.resolve(name), 4)))
    t.p.close()

    rx = dm32dbg.Radio(a.rx)
    before = stats(rx, sym)
    rx_port = rx
    keys = radio.Radio(a.tx)
    keys.ptt(True)
    t0 = time.time()
    time.sleep(0.5)
    print('tx state while keyed:', {k: v for k, v in keys.state().items() if k in ('transmitting', 'mode', 'tx')})
    time.sleep(max(0.0, a.seconds - (time.time() - t0)))
    keys.ptt(False)
    time.sleep(1.0)
    keys.close()
    after = stats(rx_port, sym)
    d = {k: after[k] - before[k] for k in NAMES if not k.endswith('_max_us') and k != 'dec_us_max'}
    print('receiver:', ' '.join('%s %d' % (k, v) for k, v in d.items() if v))
    t = dm32dbg.Radio(a.tx)
    print('transmitter: calls %d frames %d encoder %d underruns %d' %
          struct.unpack('<4I', t.mem_read(sym.resolve('nxdn_tx_stats'), 16)))


if __name__ == '__main__':
    main()
