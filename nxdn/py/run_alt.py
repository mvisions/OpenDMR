"""One run of the P25 / NXDN alternation (pi_switch.py on the hotspot) with a physical layer capture on the radio.

  python nxdn/py/run_alt.py out_name [--port COM22] [--nxdn-file /tmp/x.txt] [--p25 1.0] [--nxdn 2.0]
     (PISTAR_HOST, PISTAR_PASS in the environment; /tmp/pi_switch.py on the hotspot)
"""
import argparse
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
import pi  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--nxdn-file', default=None)
    ap.add_argument('--tx', type=int, default=439000360, help="the hotspot's Tx, Hz (its TXOffset added: 360)")
    ap.add_argument('--p25', type=float, default=1.0)
    ap.add_argument('--nxdn', type=float, default=2.0)
    ap.add_argument('--blocks', type=int, default=160)
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    pi.run(c, "echo %s | sudo -S systemctl stop p25tx mmdvmhost.timer mmdvmhost 2>&1; sleep 1" % pw)
    out = []
    extra = (' --nxdn-file ' + a.nxdn_file) if a.nxdn_file else ''

    def remote():
        _, o, _ = c.exec_command("echo %s | sudo -S python3 /tmp/pi_switch.py --tx %d --p25 %s --nxdn %s "
                                 "--cycles 6%s 2>&1" % (pw, a.tx, a.p25, a.nxdn, extra), timeout=120)
        out.append(o.read().decode())
    t = threading.Thread(target=remote)
    t.start()
    time.sleep(4)
    base = os.path.join(ROOT, 'nxdn', 'data', 'radio', a.name)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'capture', '--port', a.port,
                        '--elf', os.path.join(ROOT, 'src', 'build', 'opendmr.elf'), '--blocks', str(a.blocks), '--p25',
                        '--out', base + '.bin'], capture_output=True, text=True)
    print((r.stdout.splitlines() or [r.stderr[-300:]])[0])
    t.join()
    print(out[0].strip() if out and out[0].strip() else '(no output from the hotspot)')
    pi.run(c, "echo %s | sudo -S systemctl start mmdvmhost.timer mmdvmhost 2>&1" % pw)
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'analyse', base + '.bin',
                    '--dibits', base + '.dibits'], capture_output=True)


if __name__ == '__main__':
    main()
