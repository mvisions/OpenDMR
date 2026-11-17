"""Snapshots of the NXDN receiver's recording (nxdn_radio.c nxdn_tap: the last 2048 samples, 256 ms, as the modem
gave them) while the radio receives on an NXDN channel: the tap held, read out, let go; again after a pause. Saved as
one .npy per snapshot (int16 samples) for the PC (af_eq.py, nxdn/c).

  python nxdn/py/tap_grab.py name [--count 30] [--pause 0.5] [--port COM22]
"""
import argparse
import os
import struct
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402

TAP = 2048


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--count', type=int, default=30)
    ap.add_argument('--pause', type=float, default=0.5)
    ap.add_argument('--port', default='COM22')
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    hold, tap, n_addr = sym.resolve('nxdn_tap_hold'), sym.resolve('nxdn_tap'), sym.resolve('nxdn_tap_n')
    out = os.path.join(ROOT, 'nxdn', 'data', 'radio', 'tap')
    os.makedirs(out, exist_ok=True)
    for k in range(a.count):
        r.value_write(hold, 4, 1)
        time.sleep(0.05) # a half being written meanwhile is finished
        n = struct.unpack('<I', r.mem_read(n_addr, 4))[0]
        raw = b''
        while len(raw) < TAP * 2:
            raw += r.mem_read(tap + len(raw), min(252, TAP * 2 - len(raw)))
        r.value_write(hold, 4, 0)
        x = np.frombuffer(raw, '<i2')
        start = n % TAP # the oldest sample
        x = np.concatenate([x[start:], x[:start]])
        np.save(os.path.join(out, '%s_%02d.npy' % (a.name, k)), x)
        print('%d: %d samples, rms %.0f' % (k, len(x), x.std()), flush=True)
        time.sleep(a.pause)


if __name__ == '__main__':
    main()
