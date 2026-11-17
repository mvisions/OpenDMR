"""Sweep the HR_C7000's receive gain (RF_MODE[23:16], af_recv_ctrl: x / 16) and the hotspot's Tx offset for NXDN48:
one P25 / NXDN alternation (run_alt.py) and a capture each, the symbol error rates against the frames sent.

  python nxdn/py/sweep.py --gains 32 36 3A --offsets 0 -200
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio  # noqa: E402

RF_MODE = 0x11000104
REF = 'E:/exam/pistar-signal-gen/files/1031Hz_test_nxdn.txt'


def set_gain(port, g):
    r = Radio(port)
    v = r.value_read(RF_MODE, 4)
    r.value_write(RF_MODE, 4, (v & ~0xFF0000) | (g << 16))
    r.p.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gains', nargs='+', default=['36'])
    ap.add_argument('--offsets', nargs='+', type=int, default=[0])
    ap.add_argument('--port', default='COM22')
    a = ap.parse_args()
    rows = []
    for g in a.gains:
        for off in a.offsets:
            name = 'sw_g%s_o%d' % (g, off)
            set_gain(a.port, int(g, 16))
            subprocess.run([sys.executable, os.path.join(HERE, 'run_alt.py'), name, '--tx', str(439000000 + off),
                            '--p25', '1.5', '--nxdn', '2.0', '--port', a.port], capture_output=True)
            out = subprocess.run([sys.executable, os.path.join(HERE, 'chip.py'),
                                  os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.dibits'), '--from-block', '58',
                                  '--to-block', '126', '--reference', REF], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace').stdout
            m = re.search(r'against the frames sent: (\d+) frames, sign errors ([\d.]+) %, magnitude errors ([\d.]+) %',
                          out)
            lich = len(re.findall(r'LICH \d+ ok ', out))
            sacch = len(re.findall(r'SACCH SR \w\w ok', out))
            vch = out.count('cea8fe83acc458200a')
            line = 'gain 0x%s offset %+4d Hz: %s  LICH ok %d, SACCH ok %d, VCH exact %d' % (
                g, off, ('%s frames, sign %s %%, magnitude %s %%' % m.groups()) if m else 'no frames', lich, sacch, vch)
            print(line, flush=True)
            rows.append(line)
    set_gain(a.port, 0x26)
    print('gain back to 0x26')


if __name__ == '__main__':
    main()
