#!/usr/bin/env python3
"""Runs on the Pi-Star hotspot (MMDVM_HS, the serial protocol of pistar-signal-gen's p25tx.py): P25 and NXDN in turn
on one frequency, for the radio's physical layer capture: it locks on the P25 sync, and what follows shows what the
HR_C7000 makes of NXDN (nxdn/py/chip.py). MMDVMHost must be stopped first (it owns the serial port).

  sudo systemctl stop mmdvmhost.timer mmdvmhost
  sudo python3 pi_switch.py --tx 439000000 [--p25 1.0] [--nxdn 2.0] [--cycles 10] [--nxdn-file F]
  sudo systemctl start mmdvmhost.timer mmdvmhost

Frame files: pistar-signal-gen's normalised text ("<type> <length> <hex>").
"""
import argparse
import os
import select
import termios
import time

FRAME_START, GET_VERSION, GET_STATUS, SET_CONFIG, SET_MODE, SET_FREQ = 0xE0, 0x00, 0x01, 0x02, 0x03, 0x04
P25_HDR, P25_LDU, NXDN_DATA, ACK, NAK = 0x30, 0x31, 0x40, 0x70, 0x7F
STATE_IDLE, STATE_P25, STATE_NXDN = 0, 4, 5

ap = argparse.ArgumentParser()
ap.add_argument('--port', default='/dev/ttyAMA0')
ap.add_argument('--tx', type=int, required=True)
ap.add_argument('--p25', type=float, default=1.0, help='seconds of P25 a cycle')
ap.add_argument('--nxdn', type=float, default=2.0, help='seconds of NXDN a cycle')
ap.add_argument('--cycles', type=int, default=10)
ap.add_argument('--p25-file', default='/usr/local/p25tx/files/1011Hz_test.txt')
ap.add_argument('--nxdn-file', default='/usr/local/p25tx/files/1031Hz_test_nxdn.txt')
args = ap.parse_args()


def load(path):
    out = []
    for line in open(path):
        p = line.split()
        if len(p) < 3 or p[0].startswith('#'):
            continue
        data = bytes.fromhex(p[2])
        cmd = NXDN_DATA if p[0] == 'NXDN' else (P25_HDR if p[0] == 'HDU' else P25_LDU)
        out.append((cmd, b'\x00' + data, p[0]))
    return out


P25 = load(args.p25_file)
NXDN = load(args.nxdn_file)

fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
a = termios.tcgetattr(fd)
a[0] = a[1] = a[3] = 0
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[4] = a[5] = termios.B115200
a[6][termios.VMIN] = 0
a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
termios.tcflush(fd, termios.TCIOFLUSH)
rxbuf = bytearray()
t0 = time.time()
tx = False


def log(m):
    print('%7.3f %s %s' % (time.time() - t0, time.strftime('%H:%M:%S'), m), flush=True)


def send(cmd, payload=b''):
    os.write(fd, bytes([FRAME_START, len(payload) + 3, cmd]) + payload)


def frames(timeout):
    end = time.time() + timeout
    while True:
        r, _, _ = select.select([fd], [], [], max(0, end - time.time()))
        if r:
            try:
                rxbuf.extend(os.read(fd, 512))
            except BlockingIOError:
                pass
        while len(rxbuf) >= 3:
            if rxbuf[0] != FRAME_START:
                del rxbuf[0]
                continue
            n = rxbuf[1]
            if len(rxbuf) < n:
                break
            f = bytes(rxbuf[:n])
            del rxbuf[:n]
            yield f
        if time.time() >= end:
            return


def command(cmd, payload, name):
    send(cmd, payload)
    for f in frames(2.0):
        if f[2] == ACK and f[3] == cmd:
            return
        if f[2] == NAK and f[3] == cmd:
            raise SystemExit('%s: NAK %d' % (name, f[4]))
    raise SystemExit(name + ': no reply')


send(GET_VERSION)
list(frames(0.5))
config = bytes([0x00, 0x08 | 0x10, 10, STATE_IDLE, 128, 128, 1, 0, 128, 128, 128, 128, 128, 128, 128, 128, 4, 128])
command(SET_CONFIG, config, 'config')
command(SET_FREQ, bytes([0x00]) + args.tx.to_bytes(4, 'little') + args.tx.to_bytes(4, 'little') + bytes([255]) +
        args.tx.to_bytes(4, 'little'), 'frequency')


def play(queue, state, seconds, space_byte, slot_kinds):
    global tx
    command(SET_MODE, bytes([state]), 'mode')
    log('%s for %.1f s' % ('P25' if state == STATE_P25 else 'NXDN', seconds))
    end = time.time() + seconds
    sent = 0
    space = 0
    last = 0
    while time.time() < end:
        if time.time() - last > 0.05:
            send(GET_STATUS)
            last = time.time()
        for f in frames(0.02):
            if f[2] == GET_STATUS and len(f) > space_byte:
                space = f[space_byte]
                if bool(f[5] & 0x01) != tx:
                    tx = not tx
                    log('TX ' + ('ON' if tx else 'OFF'))
        while space > 0:
            cmd, payload, kind = queue[sent % len(queue)]
            send(cmd, payload)
            sent += 1
            if kind in slot_kinds:
                space -= 1
    # idle until the transmitter is off: the next mode starts a new transmission (the board sets its modulator up
    # for the mode only when a transmission starts)
    command(SET_MODE, bytes([STATE_IDLE]), 'idle')
    end = time.time() + 2
    while tx and time.time() < end:
        send(GET_STATUS)
        for f in frames(0.05):
            if f[2] == GET_STATUS and len(f) > space_byte and not (f[5] & 0x01):
                tx = False
                log('TX OFF')


try:
    for c in range(args.cycles):
        play(P25, STATE_P25, args.p25, 10, ('LDU1', 'LDU2'))
        play(NXDN, STATE_NXDN, args.nxdn, 11, ('NXDN',))
finally:
    send(SET_MODE, bytes([STATE_IDLE]))
    list(frames(0.5))
    os.close(fd)
    log('idle')
