"""MMDVMCal on the Pi-Star hotspot over an interactive ssh shell (it takes single keys): e.g. the DMR simplex 1031 Hz
test pattern (MMDVM_HS key M: CC1, ID 1, TG 9).

  python nxdn/py/pi_cal.py start --freq 439000000 [--keys M T]    MMDVMHost stopped, MMDVMCal started, keys sent
  python nxdn/py/pi_cal.py stop                                   MMDVMCal quit (Q), MMDVMHost started again
  (PISTAR_HOST / PISTAR_PASS in the environment)

The shell stays open while start waits (--seconds); the test runs as long as MMDVMCal runs.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pi  # noqa: E402


def read(ch, wait=0.8):
    time.sleep(wait)
    out = b''
    while ch.recv_ready():
        out += ch.recv(65536)
    return out.decode(errors='replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['start', 'stop'])
    ap.add_argument('--freq', type=int, default=439000000)
    ap.add_argument('--keys', nargs='*', default=['M'])
    ap.add_argument('--seconds', type=float, default=60)
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    if a.action == 'stop':
        print(pi.run(c, "echo %s | sudo -S sh -c 'pkill -INT MMDVMCal; sleep 1; pkill MMDVMCal; "
                        "systemctl start mmdvmhost.timer mmdvmhost' 2>&1; systemctl is-active mmdvmhost" % pw))
        return
    print(pi.run(c, "echo %s | sudo -S systemctl stop p25tx mmdvmhost.timer mmdvmhost 2>&1; sleep 4" % pw))
    ch = c.invoke_shell(width=200)
    read(ch)
    ch.send('sudo /usr/local/bin/MMDVMCal 115200 /dev/ttyAMA0\n')
    out = read(ch, 3.0)          # it talks to the modem first
    if 'password' in out.lower():
        ch.send(pw + '\n')
        out += read(ch, 2.0)
    print(out[-1500:])
    ch.send('E')
    out = read(ch, 0.8)
    ch.send('%d\r' % a.freq)    # the terminal is raw: Enter is a carriage return
    out += read(ch, 1.5)
    ch.send('H')                  # the help shows the frequency now set
    out += read(ch, 1.5)
    print(out[-1600:])
    for k in a.keys:
        ch.send(k)
        print('--- key %s' % k)
        print(read(ch, 1.5)[-800:])
    print('running for %.0f s' % a.seconds, flush=True)
    time.sleep(a.seconds)
    ch.send(' ')                 # transmit off
    read(ch, 0.8)
    ch.send('Q')
    print(read(ch, 1.5)[-500:])
    print(pi.run(c, "echo %s | sudo -S systemctl start mmdvmhost.timer mmdvmhost 2>&1; systemctl is-active mmdvmhost"
                 % pw))


if __name__ == '__main__':
    main()
