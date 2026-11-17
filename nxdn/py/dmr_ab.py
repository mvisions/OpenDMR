"""Which difference between DMR and NXDN48 upsets the chip's physical layer after a good 48-bit lock: the symbol rate or
the deviation. The hotspot sends DMR (its native 48-bit syncs, TS1) with
  native     the test file as it is (the baseline: 0 bit errors)
  doubled    every payload symbol of the voice bursts sent twice (2400 symbols/s content, DMR deviation)
  level70    the test file at TX level 70 instead of 128 (about NXDN48's deviation, 1050 / 1944 Hz)
and the radio captures with the DMR syncs (no custom registers); dmr_check.py counts the bit errors against the file.

  python nxdn/py/dmr_ab.py [native doubled level70 ...]
  (PISTAR_HOST / PISTAR_PASS in the environment; COM22 on the DMR VFO RX 439.000 TS1, eco off)
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
import pi  # noqa: E402

SRC = 'E:/exam/pistar-signal-gen/files/1031Hz_test_dmr.txt'


def dibits(b):
    return [(c >> s) & 3 for c in b for s in (6, 4, 2, 0)]


def pack(d):
    return bytes((d[i] << 6) | (d[i + 1] << 4) | (d[i + 2] << 2) | d[i + 3] for i in range(0, len(d), 4))


def doubled(burst):
    """the 54 dibits before and the 54 after the middle 24 (sync / EMB) as 27 symbols each, every one twice"""
    d = dibits(burst)
    a, mid, b = d[:54], d[54:78], d[78:]
    return pack([x for x in a[:27] for _ in (0, 1)] + mid + [x for x in b[:27] for _ in (0, 1)])


def main():
    names = sys.argv[1:] or ['native', 'doubled', 'level70']
    pw = os.environ['PISTAR_PASS']
    c = pi.connect()
    lines = open(SRC).read().splitlines()
    for name in names:
        level = 70 if name == 'level70' else 128
        fname = '1031Hz_test_dmr.txt'
        local_ref = SRC
        if name == 'doubled':
            out = []
            for line in lines:
                p = line.split()
                if len(p) >= 3 and p[0] == 'DMR1':
                    burst = bytes.fromhex(p[2])
                    # voice bursts: the A burst with its sync, B - F with an EMB; data bursts (header / terminator) kept
                    data_sync = (burst[13] & 0x0F, burst[14:19], burst[19] & 0xF0) == (0x0D, bytes.fromhex('FF57D75DF5'), 0xD0)
                    if not data_sync:
                        burst = doubled(burst)
                    out.append('DMR1 33 %s' % burst.hex().upper())
                else:
                    out.append(line)
            local_ref = os.path.join(tempfile.gettempdir(), 'dmr_doubled.txt')
            open(local_ref, 'w', newline='\n').write('\n'.join(out) + '\n')
            pi.put(c, local_ref, '/tmp/dmr_doubled.txt')
            print(pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl upload /tmp/dmr_doubled.txt dmr_doubled.txt 2>&1"
                         % pw).strip())
            fname = 'dmr_doubled.txt'
        env = ('P25TX_ARGS=/usr/local/p25tx/files/%s --rx 434000000 --tx 439000000 --gap 0 --max 3600 --loop --level %d'
               % (fname, level))
        print(name + ': ' + ' '.join(pi.run(c, (
            "echo %s | sudo -S systemctl stop p25tx >/dev/null 2>&1; sleep 2; "
            "echo %s | sudo -S sh -c 'mkdir -p /run/p25tx; echo \"%s\" > /run/p25tx/env' 2>&1; "
            "echo %s | sudo -S systemctl start p25tx 2>&1; sleep 6; systemctl is-active p25tx; cat /run/p25tx/env")
            % (pw, pw, env, pw)).split()))
        time.sleep(1)
        base = os.path.join(ROOT, 'nxdn', 'data', 'radio', 'dmrab_%s' % name)
        cap = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'debug', 'p25_phy.py'), 'capture', '--port',
                              'COM22', '--elf', os.path.join(ROOT, 'src', 'build', 'opendmr.elf'), '--blocks', '80',
                              '--wait', '30', '--out', base + '.bin', '--dibits', base + '.dibits'],
                             capture_output=True, text=True, encoding='utf-8', errors='replace').stdout
        print('  ' + ' | '.join(l.strip() for l in cap.splitlines() if 'RX_TYPE' in l or 'syncs in the joined' in l))
        chk = subprocess.run([sys.executable, os.path.join(HERE, 'dmr_check.py'), base + '.dibits', '--file', local_ref],
                             capture_output=True, text=True).stdout
        print('  ' + '\n  '.join(l for l in chk.splitlines() if 'bursts' in l or 'syncs' in l))
    pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl stop >/dev/null 2>&1" % pw)


if __name__ == '__main__':
    main()
