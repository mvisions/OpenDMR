"""How reliable the FM recording path is: the hotspot sends the NXDN48 1031 Hz test signal, the radio is rebooted (eco
off) before every recording (af_capture.py), each recording demodulated (af_demod.py) and the results summed up.

  python nxdn/py/af_stability.py [--runs 10] [--tau 600] [--no-reboot]
  (PISTAR_HOST / PISTAR_PASS in the environment; COM22 on the DMR VFO RX 439.000)
"""
import argparse
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
import pi  # noqa: E402
from dev_sweep import fresh, Symbols, ELF  # noqa: E402

REF = 'E:/exam/pistar-signal-gen/files/1031Hz_test_nxdn.txt'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=10)
    ap.add_argument('--tau', default='600')
    ap.add_argument('--bw', default='1F')
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--no-reboot', action='store_true')
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    print(' '.join(pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1; sleep 3; "
                             "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl start 1031Hz_test_nxdn.txt 439000000 1 0 3600 2>&1"
                          % (pw, pw)).split()))
    time.sleep(6)
    sym = Symbols(ELF)
    for i in range(a.runs):
        if not a.no_reboot:
            fresh(a.port, sym)
            time.sleep(2)
        name = 'stab_%02d' % i
        cap = subprocess.run([sys.executable, os.path.join(HERE, 'af_capture.py'), name, '--bw', a.bw, '--port', a.port],
                             capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = cap.stdout + cap.stderr
        npy = os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.af.npy')
        if cap.returncode or not os.path.exists(npy):
            print('#%02d capture failed: %s' % (i, out.strip()[-200:]), flush=True)
            continue
        x = np.load(npy)
        std = x.std()
        dem = subprocess.run([sys.executable, os.path.join(HERE, 'af_demod.py'), npy, '--reference', REF, '--tau', a.tau],
                             capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        sign = re.search(r'sign errors ([\d.]+) %, magnitude errors ([\d.]+) %', dem)
        tot = re.search(r'frames (\d+): LICH ok (\d+), SACCH CRC ok (\d+), VCH = 1031 Hz vector (\d+) of (\d+)', dem)
        print('#%02d std %6.0f  %s  %s' % (
            i, std, 'sign %5s %% mag %5s %%' % sign.groups() if sign else 'no symbol comparison',
            'frames %s LICH %s SACCH %s VCH %s/%s' % tot.groups() if tot else 'no frames'), flush=True)
        os.remove(os.path.join(ROOT, 'nxdn', 'data', 'radio', name + '.af.wav'))
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1" % pw)


if __name__ == '__main__':
    main()
