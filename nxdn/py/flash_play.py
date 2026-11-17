"""AMBE frames from a .bit file (9 bytes a frame) into the radio's flash, then played by the NXDN receiver's vocoder and
playback as if received (nxdn_radio.c nxdn_play_*): the vocoder and the speaker path without the air. The radio on an
NXDN channel (the receiver running: its tap buffer carries the data on the way).

  python nxdn/py/flash_play.py write vocoder/data/dvsi/r33/clean.bit     into the flash (window 0x410000, checked empty)
  python nxdn/py/flash_play.py play [--frames N]                        play them around and around
  python nxdn/py/flash_play.py stop
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'debug'))
from dm32dbg import Radio, Symbols  # noqa: E402

AREA = 0x410000   # in the flash window: the receive log's area (0x400000 - 0x4FF000), below the DMR IDs (0x5AF000 on)
SIZE = 0x40000    # 256 KB at most
CHUNK = 4096
COUNT_FILE = os.path.join(ROOT, 'nxdn', 'data', 'flash_play_frames.txt')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['write', 'play', 'stop'])
    ap.add_argument('bits', nargs='?')
    ap.add_argument('--frames', type=int)
    ap.add_argument('--port', default='COM22')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    sym = Symbols(os.path.join(ROOT, 'src', 'build', 'opendmr.elf'))
    r = Radio(a.port)
    if a.action == 'stop':
        r.value_write(sym.resolve('nxdn_play_frames'), 4, 0)
        return
    if a.action == 'play':
        n = a.frames or int(open(COUNT_FILE).read())
        r.value_write(sym.resolve('nxdn_play_address'), 4, AREA)
        r.value_write(sym.resolve('nxdn_play_frames'), 4, n)
        print('playing %d frames (%.1f s) around and around' % (n, n * 0.02))
        return
    data = open(a.bits, 'rb').read()
    data = data[:len(data) // 9 * 9]
    if len(data) > SIZE:
        raise SystemExit('too long')
    tap = sym.resolve('nxdn_tap')
    hold = sym.resolve('nxdn_tap_hold')
    fread, fwrite = sym.resolve('flash_read'), sym.resolve('flash_write')
    r.value_write(hold, 4, 1) # the tap is the buffer on the way
    try:
        for off in range(0, len(data), CHUNK):
            part = data[off:off + CHUNK]
            # empty (or ours already) before writing: nothing else lives there
            if r.call(fread, [AREA + off, tap, len(part)]) == 0:
                raise SystemExit('flash_read failed')
            old = b''
            while len(old) < len(part):
                old += r.mem_read(tap + len(old), min(252, len(part) - len(old)))
            if off == 0 and any(b != 0xFF for b in old) and old[:9] != part[:9] and not a.force:
                raise SystemExit('the area is not empty (first bytes %s): --force to write over it' % old[:16].hex())
            for i in range(0, len(part), 240):
                r.mem_write_bytes(tap + i, part[i:i + 240])
            if r.call(fwrite, [AREA + off, tap, len(part)]) == 0:
                raise SystemExit('flash_write failed at %x' % off)
            print('%d / %d bytes' % (off + len(part), len(data)), flush=True)
        # read back
        for off in range(0, len(data), CHUNK):
            part = data[off:off + CHUNK]
            r.call(fread, [AREA + off, tap, len(part)])
            back = b''
            while len(back) < len(part):
                back += r.mem_read(tap + len(back), min(252, len(part) - len(back)))
            if back != part:
                raise SystemExit('read back differs at %x' % off)
    finally:
        r.value_write(hold, 4, 0)
    open(COUNT_FILE, 'w').write(str(len(data) // 9))
    print('%d frames written and read back' % (len(data) // 9))


if __name__ == '__main__':
    main()
