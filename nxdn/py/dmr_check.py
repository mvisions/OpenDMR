"""The radio's physical layer capture of the hotspot's DMR test signal (pistar-signal-gen 1031Hz_test_dmr.txt) against
the bursts sent: every BS voice sync in the captured stream (tools/debug/p25_phy.py analyse --dibits, the order on
the air), the 264-bit burst around it compared with the voice bursts of the file (A - F differ in their EMB), bit by
bit.

  python nxdn/py/dmr_check.py capture.dibits [--file E:/exam/pistar-signal-gen/files/1031Hz_test_dmr.txt]
"""
import argparse

import numpy as np

BS_VOICE = 0x755FD7DF75F7


def bits_of(data):
    return np.array([(c >> (7 - i)) & 1 for c in data for i in range(8)], np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dibits')
    ap.add_argument('--file', default='E:/exam/pistar-signal-gen/files/1031Hz_test_dmr.txt')
    a = ap.parse_args()
    bursts = []
    for line in open(a.file):
        p = line.split()
        if len(p) >= 3 and p[0].startswith('DMR'):
            bursts.append(bits_of(bytes.fromhex(p[2])))
    d = np.frombuffer(open(a.dibits, 'rb').read(), np.uint8)
    stream = np.empty(2 * len(d), np.uint8)
    stream[0::2] = d >> 1
    stream[1::2] = d & 1
    sync = np.array([(BS_VOICE >> (47 - i)) & 1 for i in range(48)], np.uint8)
    w = np.lib.stride_tricks.sliding_window_view(stream, 48)
    errs = (w != sync).sum(axis=1)
    found = np.where(errs <= 4)[0]
    print('%d bits; BS voice syncs (<= 4 bit errors): %d, spacing (bits) %s' % (
        len(stream), len(found), np.unique(np.diff(found), return_counts=True) if len(found) > 1 else '-'))
    total = wrong = 0
    for pos in found:
        start = pos - 108
        if start < 0 or start + 264 > len(stream):
            continue
        got = stream[start:start + 264]
        best = min(bursts, key=lambda b: int((b != got).sum()))
        e = int((best != got).sum())
        total += 264
        wrong += e
        print('  burst at bit %6d: %3d of 264 bits wrong' % (start, e))
    if total:
        print('bit error rate over %d voice bursts with sync: %.2f %%' % (total // 264, 100 * wrong / total))


if __name__ == '__main__':
    main()
