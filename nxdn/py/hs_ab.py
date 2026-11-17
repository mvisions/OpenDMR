"""A/B on the hotspot (stable transmitter): NXDN48 frames made of FSW + a 12-symbol window W + a level staircase, sent by
pistar-signal-gen (uploaded as a frame file); the radio's physical layer locks on W with every symbol doubled (NXDN48
at the chip's 4800 symbols/s); the staircase as received tells the level mapping after the lock.

  python nxdn/py/hs_ab.py [names ...] [--freq 439000000] [--gain 36] [--threshold 0140402F]
  (PISTAR_HOST / PISTAR_PASS in the environment; COM22 on a DMR VFO at the frequency, eco off)
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
import pi  # noqa: E402
from dev_sweep import fresh, Symbols, ELF  # noqa: E402

FSW = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3]
STAIR = ([3] * 6 + [1] * 6 + [-1] * 6 + [-3] * 6) * 8
D = {3: 1, 1: 0, -1: 2, -3: 3}
LEVEL = {1: 3, 0: 1, 2: -1, 3: -3}

WINDOWS = {
    'outer': [3, 3, -3, 3, -3, -3, 3, -3, 3, -3, -3, 3],     # only +-3, balanced
    'inner': [3, 1, -3, 3, -1, -3, 3, -1, 1, -3, -3, 3],     # with +-1, balanced
    'fswlich': [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3, -3, 3],  # what the real frames give (FSW + 2 LICH symbols)
}


def build(name):
    """(the frame's 192 symbols, the window, the symbol positions of FSW and windows); a name ending in 3 has the
    window three times a frame (every 64 symbols, 26.7 ms: re-syncs about as often as DMR's)"""
    w = WINDOWS[name.rstrip('3P')]
    if name.endswith('P'):
        # every 72 symbols (144 at the chip's rate: one 30 ms block), three frames a cycle (576 symbols)
        sym = []
        for f in range(3):
            sym += FSW + STAIR[:182]
        skip = set()
        for f in range(3):
            skip |= set(range(192 * f, 192 * f + 10))
        for k in range(8):
            p = 10 + 72 * k
            sym[p:p + 12] = w
            skip |= set(range(p, p + 12))
        return sym, w, sorted(skip)
    if name.endswith('3'):
        seg = STAIR[:42]
        sym = FSW + w + seg + w + seg + w + seg
        sym = (sym + STAIR)[:192]
        skip = list(range(22)) + list(range(64, 76)) + list(range(118, 130))
    else:
        sym = (FSW + w + STAIR)[:192]
        skip = list(range(22))
    return sym, w, skip


def pack(sym):
    v = 0
    for s in sym:
        v = (v << 2) | D[s]
    return v


def report(s, sym, skip=range(24)):
    """at the chip's rate, block by block (the capture's blocks do not follow each other evenly): the frame sent
    with every symbol doubled, repeated, and each block aligned where most levels agree; the window and FSW left out"""
    sent = np.array([v for v in sym for _ in (0, 1)], float)
    ref = np.concatenate([sent, sent])
    period = len(sent)
    keep = np.ones(period, bool)
    for i in skip:
        keep[2 * i:2 * i + 2] = False
    idx = {3: 0, 1: 1, -1: 2, -3: 3}
    conf = np.zeros((4, 4), int)
    good = 0
    for b in range(len(s) // 144):
        blk = s[b * 144:(b + 1) * 144]
        sc = [(ref[o:o + 144] == blk).sum() for o in range(period)]
        o = int(np.argmax(sc))
        if sc[o] < 60:
            continue
        good += 1
        for j in range(144):
            k = (o + j) % period
            if keep[k] and k % 2:
                conf[idx[int(sent[k])], idx[int(blk[j])]] += 1
    n = conf.sum()
    sign_err = conf[0:2, 2:4].sum() + conf[2:4, 0:2].sum()
    report.last = 100 * (n - np.trace(conf)) / max(n, 1)
    print('  %d blocks aligned: symbol errors %.1f %%, sign errors %.1f %%' % (
        good, 100 * (n - np.trace(conf)) / max(n, 1), 100 * sign_err / max(n, 1)))
    for lv in (3, 1, -1, -3):
        r = conf[idx[lv]]
        print('    sent %+d -> +3 %3d%%  +1 %3d%%  -1 %3d%%  -3 %3d%%' % ((lv,) + tuple(
            round(100 * v / max(r.sum(), 1)) for v in r)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*', default=list(WINDOWS))
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--freq', type=int, default=439000000)
    ap.add_argument('--gain', default='36')
    ap.add_argument('--threshold', default='0140402F')
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--level', type=int, default=128, help='the hotspot TX level (deviation), 128 normal')
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    for name in [n for n in a.names for _ in range(a.repeat)]:
        sym, w, skip = build(name)
        frames = ['NXDN 48 %s\n' % pack(sym[i:i + 192]).to_bytes(48, 'big').hex().upper()
                  for i in range(0, len(sym), 192)]
        local = os.path.join(tempfile.gettempdir(), 'ab_%s.txt' % name)
        open(local, 'w', newline='\n').write(''.join(frames) * (24 // len(frames)))
        pi.put(c, local, '/tmp/ab_%s.txt' % name)
        out = pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1; sleep 3; "
                        "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl upload /tmp/ab_%s.txt ab_%s.txt 2>&1; "
                        "echo %s | sudo -S sh -c 'echo \"P25TX_ARGS=/usr/local/p25tx/files/ab_%s.txt --rx 434000000 "
                        "--tx %d --gap 0 --max 3600 --loop --level %d\" > /run/p25tx/env'; "
                        "echo %s | sudo -S systemctl start p25tx 2>&1"
                     % (pw, pw, name, name, pw, name, a.freq, a.level, pw))
        print('%s: hotspot %s' % (name, ' '.join(out.split())))
        fresh(a.port, Symbols(ELF))   # a capture leaves the receiver changed: every one from a fresh start
        time.sleep(3)
        sync = pack([s for s in w for _ in (0, 1)])
        base = os.path.join(ROOT, 'nxdn', 'data', 'radio', 'hsab_%s' % name)
        cap = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'capture', '--port',
                              a.port, '--elf', os.path.join(ROOT, 'src', 'build', 'opendmr.elf'), '--blocks', '80',
                              '--sync', '%012X' % sync, '--gain', a.gain, '--threshold', a.threshold, '--wait', '30',
                              '--out', base + '.bin', '--dibits', base + '.dibits'],
                             capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        kinds = [l for l in cap.splitlines() if 'RX_TYPE' in l]
        print('  sync %012X; %s' % (sync, kinds[0].split('(')[0].strip() if kinds else cap[-300:]))
        if not os.path.exists(base + '.dibits'):
            continue
        d = np.frombuffer(open(base + '.dibits', 'rb').read(), np.uint8)
        s = np.array([LEVEL[x] for x in d], float)
        report(s, sym, skip)
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1" % pw)


if __name__ == '__main__':
    main()
