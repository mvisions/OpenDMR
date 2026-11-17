"""The hotspot's NXDN frames from MMDVMHost's modem trace ([Modem] Trace=1, [Log] FileLevel=1): each 'RX NXDN Data'
(48 bytes, 192 symbols) after a time, joined, and the FSW (0xCDF59, 20 bits) searched at every bit: where each one
is against the 384-bit frame grid shows whether the frames come every 192 symbols.

  python nxdn/py/hs_trace.py HH:MM:SS [--log /var/log/pi-star/MMDVM-YYYY-MM-DD.log]
"""
import argparse
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pi  # noqa: E402

FSW = 0xCDF59


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('since')
    ap.add_argument('--log', default='/var/log/pi-star/MMDVM-%s.log' % datetime.date.today().isoformat())
    ap.add_argument('--until', default='99:99:99')
    a = ap.parse_args()
    c = pi.connect()
    text = pi.run(c, 'cat %s' % a.log)
    frames, cur, hdr = [], None, None
    for line in text.splitlines():
        m = re.match(r'D: \S+ (\d\d:\d\d:\d\d)\.\d+ (.*)', line)
        if not m or m.group(1) < a.since or m.group(1) > a.until:
            continue
        body = m.group(2)
        if body.startswith('RX NXDN'):
            if cur:
                frames.append((hdr, bytes(cur)))
            cur, hdr = [], (m.group(1), body)
            continue
        d = re.match(r'([0-9A-F]{4}):  ((?:[0-9A-F]{2} )+)', body)
        if d and cur is not None:
            cur += [int(x, 16) for x in d.group(2).split()]
    if cur:
        frames.append((hdr, bytes(cur)))
    bits = []
    for (t, what), raw in frames:
        if 'Data' not in what or len(raw) < 52:
            print(t, what)
            continue
        data = raw[4:52]
        print(t, 'flag %02X' % raw[3], data[:6].hex())
        bits += [(b >> (7 - i)) & 1 for b in data for i in range(8)]
    for inv, name in ((0, 'FSW'), (0xFFFFF, 'inverted')):
        hits = []
        for i in range(len(bits) - 20):
            v = 0
            for b in bits[i:i + 20]:
                v = (v << 1) | b
            err = bin(v ^ FSW ^ inv).count('1')
            if err <= 2:
                hits.append((i, err))
        print(name, ' '.join('%d(frame %d +%d, %d err)' % (i, i // 384, i % 384, e) for i, e in hits))


if __name__ == '__main__':
    main()
