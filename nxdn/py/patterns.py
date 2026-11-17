"""Simple NXDN48 test frames for the hotspot (pistar-signal-gen text format: "NXDN 48 <hex>"): the FSW, then a known
symbol pattern instead of channel data (not scrambled: the hotspot sends the bytes as they are), to see what the
radio's demodulator makes of each level before whole frames.

  python nxdn/py/patterns.py stair  out.txt    +3 x12, +1 x12, -1 x12, -3 x12, ... after the FSW
  python nxdn/py/patterns.py square out.txt    +3 +3 -3 -3 ... (TS 1-A 3.6, the reference deviation: a 600 Hz sine)
  python nxdn/py/patterns.py outer  out.txt    +3 x12, -3 x12, ... (the outer levels only)
"""
import sys

FSW = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3]
DIBIT = {3: 0b01, 1: 0b00, -1: 0b10, -3: 0b11}


def payload(kind):
    if kind == 'stair':
        unit = [3] * 12 + [1] * 12 + [-1] * 12 + [-3] * 12
    elif kind == 'square':
        unit = [3, 3, -3, -3]
    elif kind == 'outer':
        unit = [3] * 12 + [-3] * 12
    else:
        raise SystemExit('stair, square or outer')
    return (unit * 10)[:182]


def frame(symbols):
    bits = 0
    for s in symbols:
        bits = (bits << 2) | DIBIT[s]
    return bits.to_bytes(48, 'big')


def main():
    kind, out = sys.argv[1], sys.argv[2]
    data = frame(FSW + payload(kind))
    with open(out, 'w', newline='\n') as f:
        for _ in range(4):
            f.write('NXDN 48 %s\n' % data.hex().upper())
    print('%s: 4 frames, FSW + %s' % (out, kind))


if __name__ == '__main__':
    main()
