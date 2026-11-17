"""Transmitter settings swept against the hotspot's NXDN receive (MMDVMHost with [Modem] Trace=1, FileLevel=1): for
each value a call from the transmitter (tx_test.py's keying), then the hotspot log since its start: frames the modem
gave (with its sync flag), lost, and the calls MMDVMHost took (its "NXDN, received RF" lines and the end with BER).

  python nxdn/py/hs_sweep.py nxdn_tx_dev 553 700 850 [--fixed p25_phy_tx_xor=2 ...] [--seconds 4] [--tx COM23]
"""
import argparse
import datetime
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
import dm32dbg  # noqa: E402
import pi  # noqa: E402
import radio  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('values', nargs='+')
    ap.add_argument('--fixed', nargs='*', default=[])
    ap.add_argument('--seconds', type=float, default=4.0)
    ap.add_argument('--tx', default='COM23')
    a = ap.parse_args()
    sym = dm32dbg.Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    c = pi.connect()
    log = '/var/log/pi-star/MMDVM-%s.log' % datetime.date.today().isoformat()
    for v in a.values:
        t = dm32dbg.Radio(a.tx)
        for kv in a.fixed + ['%s=%s' % (a.name, v)]:
            n, x = kv.split('=')
            t.value_write(sym.resolve(n), 4, int(x, 0))
        t.p.close()
        since = pi.run(c, 'date -u +%H:%M:%S').strip()
        k = radio.Radio(a.tx)
        k.ptt(True)
        time.sleep(a.seconds)
        k.ptt(False)
        time.sleep(1.5)
        k.close()
        text = pi.run(c, "awk '$3 >= \"%s\"' %s | grep -E 'NXDN' | grep -v RSSI" % (since, log))
        data = sync = lost = 0
        calls = []
        for line in text.splitlines():
            if 'RX NXDN Data' in line:
                data += 1
            elif 'RX NXDN Lost' in line:
                lost += 1
            elif line.startswith('M:'):
                calls.append(line.split(' ', 3)[3])
        print('%s=%s: modem frames %d, lost %d; %s' % (a.name, v, data, lost, ' | '.join(calls) or 'no call'),
              flush=True)


if __name__ == '__main__':
    main()
