#!/usr/bin/env python3
"""The screens of the CPS's theme preview (opendmr-cps js/ui/screens.js): the firmware's frame buffer (4 bit palette
indexes, 2 pixels a byte: fshot.py) read over the cable on a few screens, under a dark and a light theme. The CPS
colours the indexes with a theme's 16 colours: the screens as the radio draws them. A theme picks the indexes of its
anti-aliased text edges when it draws them (theme.h: the nearest colours): each screen is drawn again under
each, and the CPS takes the capture of a theme as dark as the one shown.

The radio on the VFO screen, its theme set back at the end. It transmits for a second (the transmit screen) only with
--tx.

  py tools/debug/fscreens.py --port COM22 --out screens.json [--elf src/build/opendmr.elf] [--tx] [--png dir]
"""
import argparse
import base64
import json
import os
import struct
import subprocess
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dm32dbg  # noqa: E402
from radio import Radio  # noqa: E402

WIDTH, HEIGHT = 240, 320
HERE = os.path.dirname(os.path.abspath(__file__))
THEME_ID_AUTO = 0xFE
DARK, LIGHT = 0, 1  # Deep sea, Sunlight (themes.c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM6')
    ap.add_argument('--elf', default=os.path.join(HERE, '..', '..', 'src', 'build', 'opendmr.elf'))
    ap.add_argument('--out', required=True)
    ap.add_argument('--tx', action='store_true')
    ap.add_argument('--png')
    args = ap.parse_args()

    sym = {}
    for line in subprocess.run([dm32dbg.NM, args.elf], capture_output=True, text=True).stdout.splitlines():
        p = line.split()
        if len(p) == 3:
            sym[p[2]] = int(p[0], 16)
    d = dm32dbg.Radio(args.port)
    r = Radio.__new__(Radio)
    r.port = d.p

    def call(name, *a):
        return d.call(sym[name], list(a))

    def frame():
        data = b''
        for a in range(0, WIDTH * HEIGHT // 2, 512):
            data += d.mem_read(sym['frame_buffer_data'] + a, 512)
        return data

    def png(name, data):
        if not args.png:
            return
        from PIL import Image
        palette = struct.unpack('<16H', d.mem_read(sym['palette'], 32))
        rgb = []
        for c in palette:
            c = ((c & 0xFF) << 8) | (c >> 8)
            rgb.append(((c & 0x1F) * 255 // 31, ((c >> 5) & 0x3F) * 255 // 63, ((c >> 11) & 0x1F) * 255 // 31))
        img = Image.new('RGB', (WIDTH, HEIGHT))
        px = img.load()
        for i, b in enumerate(data):
            px[(i * 2) % WIDTH, (i * 2) // WIDTH] = rgb[b >> 4]
            px[(i * 2) % WIDTH + 1, (i * 2) // WIDTH] = rgb[b & 0x0F]
        os.makedirs(args.png, exist_ok=True)
        img.save(os.path.join(args.png, name + '.png'))

    # each screen: how to get there from the VFO screen, and back
    def vfo():
        r.home()

    def channel():
        r.home()
        r.key('red')
        time.sleep(0.8)

    def channel_back():
        r.key('red')
        time.sleep(0.8)

    def menu():
        r.main_menu()

    def options():
        r.main_menu('Options', 'Display options')

    def quick():
        r.quick_menu()

    def fm():
        r.main_menu('FM radio')
        time.sleep(2.5)

    def tx():
        r.home()
        r.ptt(True)
        time.sleep(1.2)

    def tx_back():
        r.ptt(False)
        time.sleep(1.0)

    screens = [('vfo', vfo, None), ('channel', channel, channel_back), ('menu', menu, None),
               ('options', options, None), ('quick', quick, None), ('fm', fm, None)]
    if args.tx:
        screens.append(('tx', tx, tx_back))

    def choose(theme):  # chosen (saved): the minute's auto theme keeps it
        call('extra_options_set_theme', theme)
        call('display_theme_apply')

    choice = call('extra_options_theme')
    out = {'width': WIDTH, 'height': HEIGHT, 'format': '4 bit palette indexes, 2 pixels a byte, raw deflate, base64',
           'screens': {}}
    try:
        for kind, theme in (('dark', DARK), ('light', LIGHT)):
            choose(theme)
            for name, go, back in screens:
                r.main_menu()  # each screen drawn again under this theme (the text edges take its colours)
                r.home()
                go()
                time.sleep(0.6)
                data = frame()
                png('%s_%s' % (name, kind), data)
                c = zlib.compressobj(9, zlib.DEFLATED, -15)
                out['screens'].setdefault(name, {})[kind] = base64.b64encode(c.compress(data) + c.flush()).decode()
                print(kind, name, len(out['screens'][name][kind]))
                if back:
                    back()
                r.home()
    finally:
        choose(choice)
        r.home()
    with open(args.out, 'w') as f:
        json.dump(out, f)
    print(args.out)


if __name__ == '__main__':
    main()
