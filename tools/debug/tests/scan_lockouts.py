"""Two radios, the scan lockouts (docs/manual: scan): one transmits FM on 144.100 (keep it at low power), the other
scans its VFO A (FM, the whole band, from 144.000). Each step checked with the state of the test interface
(tools/debug/radio.py), no screenshots. Both radios' VFO A: FM, the transmitter's 144.100 simplex.

    py tools/debug/tests/scan_lockouts.py SCANNER_PORT TRANSMITTER_PORT
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from radio import Radio  # noqa: E402

F = '14410000'  # 144.100 MHz in the state's 10 Hz units
rx, tx = Radio(sys.argv[1]), Radio(sys.argv[2])
results = []


def check(name, ok, detail=''):
    results.append((name, ok))
    print('%-58s %s %s' % (name, 'OK  ' if ok else 'FAIL', detail))


def stopped_on_signal(timeout=60):
    """The scan standing on 144.100 (paused on its signal)"""
    return rx.wait(lambda s: s['rx'] == F and s['scan'] == 'paused', timeout, every=0.03)


def stays_off(seconds=20):
    """Off 144.100 within a second, and not standing on it again for that long (it may hold on noise elsewhere)"""
    rx.wait(lambda s: s['rx'] != F, 1.0, every=0.02)
    end = time.time() + seconds
    paused, where = 0, set()
    while time.time() < end:
        s = rx.state()
        where.add(s['rx'])
        if s['rx'] == F and s['scan'] == 'paused':
            paused += 1
        time.sleep(0.03)
    print('    (%d frequencies seen in %d s, stood on 144.100 %d times)' % (len(where), seconds, paused))
    return paused == 0


def stop_scan():
    rx.key('down')  # any other key stops it
    rx.wait(lambda s: s['scan'] == 'off')


try:
    rx.home()
    tx.home()
    check('setup: COM23 FM 144.100 simplex', tx.state()['rx'] == F and tx.state()['tx'] == F and tx.state()['mode'] == 'FM')
    check('setup: COM22 VFO A FM', rx.state()['mode'] == 'FM' and rx.state().get('vfo') == 'A')
    check('setup: no lockouts', rx.state()['lockouts'] == '0,0,0', rx.state()['lockouts'])

    tx.ptt(True)
    tx.wait(lambda s: s['transmitting'] == '1')

    # 1. short * : until power off
    rx.tune(144.0)
    rx.key('up', mod='sk1')
    rx.wait(lambda s: s['scan'] != 'off')
    t = time.time()
    stopped_on_signal()
    check('1. the scan stops on COM23', True, '%.1f s' % (time.time() - t))
    rx.key('star', settle=0.3)
    s = rx.state()
    check('1. short * : a temp lockout, the scan on', s['lockouts'] == '0,1,0' and s['scan'] != 'off', s['lockouts'])
    check('1. the scan no longer stops on 144.100', stays_off())
    stop_scan()
    s = rx.main_menu('Scan lockouts')
    check('1. the list: 144.10000 Temp', s.get('row') == '144.10000' and s.get('value') == 'Temp', '%s / %s' % (s.get('row'), s.get('value')))
    rx.row('Unlock all')
    rx.key('green', settle=0.3)
    check('1. Unlock all: empty', rx.state()['lockouts'] == '0,0,0', rx.state()['lockouts'])

    # 2. long * : for good
    rx.tune(144.0)
    rx.key('up', mod='sk1')
    rx.wait(lambda s: s['scan'] != 'off')
    stopped_on_signal()
    rx.key('star', long=True, settle=0.4)
    s = rx.state()
    check('2. long * : saved, the scan on', s['lockouts'] == '0,0,1' and s['scan'] != 'off', s['lockouts'])
    check('2. the scan no longer stops on 144.100', stays_off())
    stop_scan()

    # 3. the quick menu: off / temp / permanent on the current frequency
    rx.tune(144.1)
    s = rx.quick_menu('Scan lockout')
    check('3. quick menu on 144.100: Permanent', s['value'] == 'Permanent', s['value'])
    rx.key('left')
    s = rx.state()
    check('3. left: Temp', s['value'] == 'Temp' and s['lockouts'] == '0,1,0', '%s %s' % (s['value'], s['lockouts']))
    rx.key('left')
    s = rx.state()
    check('3. left: Off, nothing locked out', s['value'] == 'Off' and s['lockouts'] == '0,0,0', '%s %s' % (s['value'], s['lockouts']))
    rx.key('right')
    rx.key('right')
    s = rx.state()
    check('3. right, right: Permanent', s['value'] == 'Permanent' and s['lockouts'] == '0,0,1', '%s %s' % (s['value'], s['lockouts']))
    rx.key('left')
    rx.key('left')
    check('3. back to Off', rx.state()['lockouts'] == '0,0,0', rx.state()['lockouts'])
    rx.home()

    # 4. the scan stops on it again once unlocked
    rx.tune(144.0)
    rx.key('up', mod='sk1')
    rx.wait(lambda s: s['scan'] != 'off')
    stopped_on_signal()
    check('4. unlocked: the scan stops on 144.100 again', True)
    stop_scan()
finally:
    tx.ptt(False)
    rx.home()
    tx.home()
    print('\n%d of %d passed' % (sum(1 for _, ok in results if ok), len(results)))
    print('COM22:', rx.state())
    print('COM23:', tx.state())
