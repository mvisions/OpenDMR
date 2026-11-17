"""Speech for the hotspot to send as NXDN48: WAV / PCM files encoded by our AMBE+2 encoder (vocoder/py hotspot_tx.py's
load_frames: band-passed, levelled), put into a conventional group call (tx.py call(): a first frame with VCALL in
FACCH1, voice frames with VCALL over the SACCH superframe, TX_REL at the end) and written as a pistar-signal-gen frame
file ("NXDN 48 <hex>", one frame a line; the hotspot sends its own preamble).

  python nxdn/py/make_voice.py out.txt speech.wav [more.wav ...] [--src 1234] [--dst 9] [--ran 1] [--gap 0.4]
  python nxdn/py/make_voice.py out.txt --upload        also onto the hotspot (PISTAR_HOST / PISTAR_PASS) as out.txt
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'vocoder', 'py'))
import tx  # noqa: E402

D = {3: 1, 1: 0, -1: 2, -3: 3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('inputs', nargs='*')
    ap.add_argument('--src', type=int, default=1234)
    ap.add_argument('--dst', type=int, default=9)
    ap.add_argument('--ran', type=int, default=1)
    ap.add_argument('--gap', type=float, default=0.4)
    ap.add_argument('--upload', action='store_true')
    a = ap.parse_args()
    if a.inputs:
        from hotspot_tx import load_frames
        voice = load_frames(a.inputs, gap=a.gap)
        syms, n = tx.call(voice, a.src, a.dst, a.ran, 2400)
        syms = [int(s) for s in syms[12:]]          # the preamble: the hotspot sends its own
        assert len(syms) % 192 == 0
        lines = []
        for i in range(0, len(syms), 192):
            v = 0
            for s in syms[i:i + 192]:
                v = (v << 2) | D[s]
            lines.append('NXDN 48 %s\n' % v.to_bytes(48, 'big').hex().upper())
        open(a.out, 'w', newline='\n').write(''.join(lines))
        print('%d AMBE frames, %d NXDN frames (%.1f s) -> %s' % (len(voice), len(lines), len(lines) * 0.08, a.out))
    if a.upload:
        import pi
        name = os.path.basename(a.out)
        c = pi.connect()
        pi.put(c, a.out, '/tmp/' + name)
        print(pi.run(c, "echo %s | sudo -S /usr/local/p25tx/p25tx-ctl upload /tmp/%s %s 2>&1"
                     % (os.environ['PISTAR_PASS'], name, name)).strip())


if __name__ == '__main__':
    main()
