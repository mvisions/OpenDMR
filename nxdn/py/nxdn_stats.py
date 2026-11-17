"""The NXDN receiver's counters (nxdn_radio.c nxdn_radio_stats) read over the cable, a few times.

  python nxdn/py/nxdn_stats.py [--port COM22] [--times 3] [--every 2]
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402

NAMES = ('halves missed_halves frames lich_bad sacch_ok vch facch_ok hunts lost_sync pcm_drops underruns calls '
         'busy_max_us dec_us_max dec_us_sum demod_us_sum feed_writes').split()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--times', type=int, default=3)
    ap.add_argument('--every', type=float, default=2.0)
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    for i in range(a.times):
        v = struct.unpack('<%dI' % len(NAMES), r.mem_read(sym.resolve('nxdn_radio_stats'), 4 * len(NAMES)))
        print(' '.join('%s %d' % kv for kv in zip(NAMES, v)), flush=True)
        if i + 1 < a.times:
            time.sleep(a.every)


if __name__ == '__main__':
    main()
