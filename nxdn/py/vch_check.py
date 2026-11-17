"""The voice frames the radio received (nxdn_radio.c nxdn_vch_log, the last 256) against the ones sent (a .bit file:
9 bytes a frame, as make_voice.py took them): each received frame matched to the frame sent nearest in bits, in order
(the sent index found from the first frames, then following on), the bit errors per frame.

  python nxdn/py/vch_check.py vocoder/data/dvsi/r33/clean.bit [--port COM22]
"""
import argparse
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402

LOG = 256


def bits(b):
    return np.unpackbits(np.frombuffer(b, np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sent')
    ap.add_argument('--port', default='COM22')
    a = ap.parse_args()
    d = open(a.sent, 'rb').read()
    sent = np.array([bits(d[i:i + 9]) for i in range(0, len(d) - 8, 9)])
    sent = np.concatenate([sent, np.repeat(sent[-1:], (-len(sent)) % 4, axis=0)]) # make_voice pads to 4
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    n = struct.unpack('<I', r.mem_read(sym.resolve('nxdn_vch_log_n'), 4))[0]
    raw = b''
    base = sym.resolve('nxdn_vch_log')
    while len(raw) < LOG * 9:
        raw += r.mem_read(base + len(raw), min(252, LOG * 9 - len(raw)))
    count = min(n, LOG)
    got = [raw[((n - count + i) % LOG) * 9:((n - count + i) % LOG) * 9 + 9] for i in range(count)]
    errs = []
    idx = None
    for g in got:
        gb = bits(g)
        if idx is None or idx >= len(sent):
            dist = (sent != gb).sum(axis=1)
            idx = int(np.argmin(dist))
        else:
            # following on; a jump (a lost frame, a new pass) if the next one is far off
            near = range(max(0, idx - 2), min(len(sent), idx + 6))
            k = min(near, key=lambda j: (sent[j] != gb).sum())
            if (sent[k] != gb).sum() > 10:
                k = int(np.argmin((sent != gb).sum(axis=1)))
            idx = k
        e = int((sent[idx] != gb).sum())
        errs.append(e)
        idx += 1
    errs = np.array(errs)
    print('%d frames received in all, the last %d: bit errors per frame (of 72): mean %.2f, frames with errors %d, '
          'with > 3 (more than the FEC may fix) %d' % (n, count, errs.mean(), (errs > 0).sum(), (errs > 3).sum()))
    print('errors in order:', ' '.join(str(x) for x in errs))


if __name__ == '__main__':
    main()
