"""NXDN96 as the HR_C7000's physical layer gives it (4800 symbols/s, one sample a symbol): a p25_phy.py capture
(--dibits), the FSWs, every frame against the frames sent (--reference, pistar-signal-gen text), and the frames
decoded (LICH, SACCH, VCH).

  python nxdn/py/chip96.py nxdn/data/radio/n96_2.dibits --reference frames.txt
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import frames as F  # noqa: E402
import l2  # noqa: E402
from chip import reference_frames, LEVEL  # noqa: E402

FSW = np.array([-3, 1, -3, 3, -3, -3, 3, 3, -1, 3], float)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dibits')
    ap.add_argument('--reference')
    a = ap.parse_args()
    d = np.frombuffer(open(a.dibits, 'rb').read(), np.uint8)
    s = np.array([LEVEL[x] for x in d], float)
    print('%d symbols; levels +3 +1 -1 -3: %s' % (len(s), [int(np.sum(s == v)) for v in (3, 1, -1, -3)]))
    w = np.lib.stride_tricks.sliding_window_view(s, 10)
    exact = np.where(np.all(w == FSW, axis=1))[0]
    print('exact FSWs: %d, spacing %s' % (len(exact), np.unique(np.diff(exact), return_counts=True)
                                          if len(exact) > 1 else '-'))
    # frame starts: 8 of the FSW's 10 symbols right and another such place a frame away (the levels may be off)
    near = set(np.where(np.sum(w == FSW, axis=1) >= 8)[0])
    starts = sorted(h for h in near if ((h + 192) in near or (h - 192) in near) and h + 192 <= len(s))
    print('frame starts (8 of 10 FSW symbols, a frame apart): %d' % len(starts))
    if a.reference and starts:
        ref = reference_frames(a.reference)
        g, e = [], []
        for h in starts:
            got = s[h:h + 192]
            k = int(np.argmax([np.sum(got == r) for r in ref]))
            g.append(got)
            e.append(ref[k])
        g = np.concatenate(g)
        e = np.concatenate(e)
        conf = {(x, y): int(np.sum((e == x) & (g == y))) for x in (3, 1, -1, -3) for y in (3, 1, -1, -3)}
        print('against the frames sent: %d frames, symbol errors %.2f %%' % (len(starts), 100 * np.mean(g != e)))
        print('  sent -> received:  ' + '  '.join('%+d:%s' % (x, ' '.join('%4d' % conf[(x, y)] for y in (3, 1, -1, -3)))
                                                  for x in (3, 1, -1, -3)))
    out = F.frames(np.array([s[h:h + 192] for h in starts]), 0) if starts else []
    good = {'lich': 0, 'sacch': 0, 'vch': 0}
    for f in out:
        sr, data, ok = l2.sacch(f['payload'][F.LICH:F.LICH + F.SACCH])
        good['lich'] += f['lich_ok']
        good['sacch'] += ok
        vch = [l2.to_bytes(v).hex() for v in f['vch']]
        good['vch'] += sum(1 for v in vch if v == 'cea8fe83acc458200a')
    if out:
        print('decoded: %d frames, LICH ok %d, SACCH CRC ok %d, VCH = the 1031 Hz vector %d of %d' % (
            len(out), good['lich'], good['sacch'], good['vch'], 4 * len(out)))
        f = out[0]
        print('first frame: LICH %s (%s)' % (format(f['lich'], '07b'), F.LICH_NAMES.get(f['lich'], '?')))


if __name__ == '__main__':
    main()
