"""Radio to radio NXDN96 (radio_pair.py), each receiver setting a few times: how often it locks and the symbol error
rate after the lock (chip96.py against the frames sent).

  python nxdn/py/pair_sweep.py --rfmodes 03269860 01269860 --sync CDF59D5D7CFA [--threshold 0150502F] [--trials 3]
  (eco off on both radios first: settings.eco_level, see README)
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
REF = 'E:/exam/pistar-signal-gen/files/1031Hz_test_nxdn.txt'


def one(name, sync, rfmode, threshold, gain, frames, dibits):
    cmd = [sys.executable, os.path.join(HERE, 'radio_pair.py'), name, '--sync', sync, '--seconds', '3',
           '--blocks', '80']
    cmd += ['--dibits', dibits] if dibits else ['--frames', frames]
    for opt, v in (('--rfmode', rfmode), ('--threshold', threshold), ('--gain', gain)):
        if v:
            cmd += [opt, v]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    m = re.search(r'rx (\d+) blocks', out)
    blocks = int(m.group(1)) if m else -1
    if blocks <= 0:
        return blocks, None, None
    a = subprocess.run([sys.executable, os.path.join(HERE, 'chip96.py'),
                        os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.dibits'), '--reference', REF],
                       capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
    e = re.search(r'symbol errors ([\d.]+) %', a)
    d = re.search(r'LICH ok (\d+), SACCH CRC ok (\d+), VCH = the 1031 Hz vector (\d+) of (\d+)', a)
    return blocks, float(e.group(1)) if e else None, d.groups() if d else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rfmodes', nargs='+', default=[None])
    ap.add_argument('--sync', default='CDF59D5D7CFA')
    ap.add_argument('--threshold', default=None)
    ap.add_argument('--gain', default=None)
    ap.add_argument('--trials', type=int, default=3)
    ap.add_argument('--frames', default=REF)
    ap.add_argument('--dibits', default=None)
    a = ap.parse_args()
    for rf in a.rfmodes:
        res = [one('ps_%s_%d' % (rf, t), a.sync, rf, a.threshold, a.gain, a.frames, a.dibits)
               for t in range(a.trials)]
        print('RF_MODE %s: %s' % (rf, '  |  '.join(
            ('no lock' if b <= 0 else '%d blocks, %s %% symbol errors%s' % (
                b, '-' if e is None else '%.1f' % e,
                '' if d is None else ', LICH %s SACCH %s VCH %s/%s' % d)) for b, e, d in res)), flush=True)


if __name__ == '__main__':
    main()
