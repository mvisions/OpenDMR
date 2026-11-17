"""What the HR_C7000's physical layer (4800 symbols/s, DMR / P25 levels) makes of an NXDN48 signal (2400 symbols/s):
a capture of tools/debug/p25_phy.py (--dibits: one dibit a byte, in the order on the air) looked at per block,
level histograms, and the NXDN FSW searched for in every second symbol (both phases), then the frames decoded.

  python nxdn/py/chip.py nxdn/data/radio/cap_switch.dibits [--from-block 60]
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frames as F  # noqa: E402
import l2  # noqa: E402

LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}
FSW = np.array([-3, 1, -3, 3, -3, -3, 3, 3, -1, 3], float)
BLOCK = 144  # dibits a 30 ms block


def reference_frames(path):
    out = []
    for line in open(path):
        p = line.split()
        if len(p) >= 3 and p[0] == 'NXDN':
            bits = l2.bits_of(bytes.fromhex(p[2]))
            out.append(np.array(l2.bits_to_symbols(bits), float))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dibits')
    ap.add_argument('--from-block', type=int, default=0)
    ap.add_argument('--to-block', type=int, default=None)
    ap.add_argument('--reference', help="the frames sent (pistar-signal-gen text file), for the error rates")
    a = ap.parse_args()
    d = np.frombuffer(open(a.dibits, 'rb').read(), np.uint8)
    s = np.array([LEVEL[x] for x in d], float)
    nb = len(s) // BLOCK
    print('%d blocks; levels per block (+3 +1 -1 -3), and the share of symbols equal to the one before:' % nb)
    for b in range(0, nb, 8):
        x = s[b * BLOCK:(b + 1) * BLOCK]
        h = [int(np.sum(x == v)) for v in (3, 1, -1, -3)]
        same = np.mean(x[1:] == x[:-1])
        print('  block %3d: %3d %3d %3d %3d   repeats %.2f' % (b, *h, same))
    s = s[a.from_block * BLOCK:(a.to_block * BLOCK if a.to_block else None)]
    best = None
    for phase in (0, 1):
        n = s[phase::2]
        win = np.lib.stride_tricks.sliding_window_view(n, 10)
        sign = np.sign(win) @ np.sign(FSW)          # signs only: 10 = all agree
        hits = np.where(sign >= 9)[0]
        print('phase %d: %d places with >= 9 of 10 FSW signs; spacing %s' % (
            phase, len(hits), np.unique(np.diff(hits), return_counts=True) if len(hits) > 1 else '-'))
        hits = np.array([h for h in hits if (h + 192 in hits) or (h - 192 in hits)])   # a frame apart only
        if best is None or len(hits) > len(best[1]):
            best = (phase, hits, n)
    phase, hits, n = best
    if a.reference:
        # the frame starts: where a whole frame's signs agree best with one of the frames sent, in both phases
        ref = reference_frames(a.reference)
        rows = []
        best_rows = None
        for ph in (0, 1):
            m = s[ph::2]
            if len(m) < 192:
                continue
            win = np.sign(np.lib.stride_tricks.sliding_window_view(m, 192))
            agree = np.max(np.array([win @ np.sign(r) for r in ref]), axis=0) / 192
            kbest = np.argmax(np.array([win @ np.sign(r) for r in ref]), axis=0)
            starts = [i for i in range(len(agree)) if agree[i] > 0.6 and agree[i] == agree[max(0, i - 96):i + 96].max()]
            cand = [(m[i:i + 192], ref[kbest[i]]) for i in starts]
            print('phase %d: %d frames by whole-frame signs (agreement %s)' % (
                ph, len(cand), ', '.join('%.2f' % agree[i] for i in starts[:6])))
            if best_rows is None or len(cand) > len(best_rows):
                best_rows = cand
        rows = best_rows or []
        if rows:
            g = np.concatenate([r[0] for r in rows])
            e = np.concatenate([r[1] for r in rows])
            sign_err = np.mean(np.sign(g) != np.sign(e))
            mag_err = np.mean((np.abs(g) == 3) != (np.abs(e) == 3))
            conf = {(x, y): int(np.sum((e == x) & (g == y))) for x in (3, 1, -1, -3) for y in (3, 1, -1, -3)}
            print('against the frames sent: %d frames, sign errors %.1f %%, magnitude errors %.1f %%' % (
                len(rows), 100 * sign_err, 100 * mag_err))
            print('  sent -> received:  ' + '  '.join('%+d:%s' % (x, ' '.join('%4d' % conf[(x, y)] for y in (3, 1, -1, -3)))
                                                      for x in (3, 1, -1, -3)))
    if len(hits) == 0:
        return
    print('FSW as received (phase %d):' % phase)
    for h in hits[:4]:
        print('   ', n[h:h + 10])
    # the frames: as received (the chip's levels), descrambled and decoded
    fr = np.array([n[h:h + 192] for h in hits if h + 192 <= len(n)])
    out = F.frames(fr, 0)
    for f in out:
        sr, data, ok = l2.sacch(f['payload'][F.LICH:F.LICH + F.SACCH])
        vch = [l2.to_bytes(v).hex() for v in f['vch']]
        print('LICH %s %s %-22s SACCH SR %02X %s  VCH %s' % (format(f['lich'], '07b'), 'ok ' if f['lich_ok'] else 'BAD',
                                                           F.LICH_NAMES.get(f['lich'], '?'), sr,
                                                           'ok ' if ok else 'BAD', ' '.join(vch[:2])))


if __name__ == '__main__':
    main()
