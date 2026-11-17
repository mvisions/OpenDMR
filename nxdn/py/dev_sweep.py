"""From DMR towards NXDN48 one variable at a time: the hotspot sends the DMR test signal at TX levels (deviation), the
radio (fresh after a reboot, eco off) is first checked in plain DMR (screenshot: the caller's ID shown or not), then its
physical layer captured with the DMR syncs and the voice bursts compared (dmr_check.py); a reboot after every capture
(the capture leaves the receiver in a state where plain DMR no longer decodes).

  python nxdn/py/dev_sweep.py 128 110 95 80 70 [--file 1031Hz_test_dmr.txt] [--gain 26]
  (PISTAR_HOST / PISTAR_PASS in the environment; COM22 on the DMR VFO RX 439.000 TS1)
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
import pi  # noqa: E402
from dm32dbg import Radio, Symbols  # noqa: E402

ELF = os.path.join(ROOT, 'src', 'build', 'opendmr.elf')
SHOTS = os.environ.get('SHOTS', os.path.join(ROOT, 'nxdn', 'data', 'radio'))


def fresh(port, sym):
    r = Radio(port)
    r.reboot()
    r.p.close()
    time.sleep(12)
    r = Radio(port)
    r.mem_write_bytes(sym.resolve('settings') + 0x65, b'\x00')   # eco off
    r.p.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('levels', nargs='+', type=int)
    ap.add_argument('--file', default='1031Hz_test_dmr.txt')
    ap.add_argument('--ref', default='E:/exam/pistar-signal-gen/files/1031Hz_test_dmr.txt')
    ap.add_argument('--gain', default=None)
    ap.add_argument('--port', default='COM22')
    a = ap.parse_args()
    pw = os.environ['PISTAR_PASS']
    sym = Symbols(ELF)
    c = pi.connect()
    for lv in a.levels:
        env = ('P25TX_ARGS=/usr/local/p25tx/files/%s --rx 434000000 --tx 439000000 --gap 0 --max 3600 --loop --level %d'
               % (a.file, lv))
        pi.run(c, "echo %s | sudo -S systemctl stop p25tx >/dev/null 2>&1; sleep 2; "
                  "echo %s | sudo -S sh -c 'echo \"%s\" > /run/p25tx/env' 2>&1; "
                  "echo %s | sudo -S systemctl start p25tx 2>&1" % (pw, pw, env, pw))
        fresh(a.port, sym)
        time.sleep(4)
        shot = os.path.join(SHOTS, 'dev_%d.png' % lv)
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'fshot.py'), shot, '--port', a.port],
                       capture_output=True)
        base = os.path.join(ROOT, 'nxdn', 'data', 'radio', 'dev_%d' % lv)
        for ext in ('.bin', '.dibits'):
            if os.path.exists(base + ext):
                os.remove(base + ext)
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'capture', '--port', a.port, '--elf',
               ELF, '--blocks', '80', '--wait', '15', '--out', base + '.bin', '--dibits', base + '.dibits']
        if a.gain:
            cmd += ['--gain', a.gain]
        cap = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        kinds = [l.split('(')[0].strip() for l in cap.splitlines() if 'RX_TYPE' in l]
        res = '-'
        if os.path.exists(base + '.dibits') and os.path.getsize(base + '.dibits'):
            chk = subprocess.run([sys.executable, os.path.join(HERE, 'dmr_check.py'), base + '.dibits', '--file', a.ref],
                                 capture_output=True, text=True).stdout
            n = [l for l in chk.splitlines() if 'syncs' in l]
            r = [l for l in chk.splitlines() if 'rate' in l]
            res = (n[0].split(':')[1].split(',')[0].strip() + ' voice syncs; ' if n else '') + (
                r[0].split(':')[1].strip() + ' bit errors' if r else 'no bursts')
        print('level %3d: screen %s | %s | %s' % (lv, shot, kinds[0] if kinds else 'no sync', res), flush=True)
    fresh(a.port, sym)
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1" % pw)


if __name__ == '__main__':
    main()
