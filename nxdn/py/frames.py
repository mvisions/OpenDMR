"""NXDN frames from the symbols demod.py found (NXDN TS 1-A): after each FSW, 182 scrambled symbols (4.6): LICH 8,
SACCH 30, then 4 VCH of 36 (EHR voice, RDCH/RTCH 4.4.2). The VCH's 72 bits are the AMBE+2 3600/2450 channel frame in
the same bit order as DMR's (the published silence frame B9E8...6B is DMR's too): decoded by our vocoder
(vocoder/py) into a WAV.

  python nxdn/py/frames.py "nxdn/data/iq/NXDN48 IQ.wav"           (after demod.py)
  python nxdn/py/frames.py ... --scrambler N                        a scrambler variant (find the right one)
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'vocoder', 'py'))

PAYLOAD = 182                      # symbols after the FSW: S0 .. S181 of the scrambler (Figure 4.6-2)
LICH, SACCH, VCH = 8, 30, 36
SCRAMBLER_INIT = [0, 1, 1, 1, 0, 0, 1, 0, 0]  # S8 .. S0, Table 4.6-1


def scrambler(variant):
    """182 bits of the X^9 + X^4 + 1 generator from the default value; the variants: where the output and the
    feedback are taken (the figure is a picture, the text does not say)"""
    s = list(SCRAMBLER_INIT)        # s[0] = S8 ... s[8] = S0
    out = []
    for _ in range(PAYLOAD):
        if variant == 0:            # output S0, S0 ^ S4 shifted in at S8
            o = s[8]
            fb = s[8] ^ s[4]
            s = [fb] + s[:8]
        elif variant == 1:          # output S0, S0 ^ S5 in at S8 (taps counted the other way)
            o = s[8]
            fb = s[8] ^ s[3]
            s = [fb] + s[:8]
        elif variant == 2:          # output S8, S8 ^ S4 shifted in at S0
            o = s[0]
            fb = s[0] ^ s[4]
            s = s[1:] + [fb]
        else:                       # output S8, S8 ^ S3 in at S0
            o = s[0]
            fb = s[0] ^ s[5]
            s = s[1:] + [fb]
        out.append(o)
    return np.array(out)


def symbols_to_bits(sym):
    """+3 -> 01, +1 -> 00, -1 -> 10, -3 -> 11 (Table 3.3-1)"""
    bits = []
    for v in sym:
        if v >= 2:
            bits += [0, 1]
        elif v >= 0:
            bits += [0, 0]
        elif v >= -2:
            bits += [1, 0]
        else:
            bits += [1, 1]
    return bits


def lich(sym):
    """8 symbols, one bit each (0: +3 / +1, 1: -1 / -3; Figure 4.5-7): 7 bits and even parity of the 4 MSBs"""
    b = [1 if v < 0 else 0 for v in sym]
    value = 0
    for x in b[:7]:
        value = (value << 1) | x
    ok = (sum(b[:4]) % 2) == b[7]
    return value, ok


def frames(frames_symbols, variant):
    pn = 1 - 2 * scrambler(variant)   # 0 -> +1, 1 -> -1
    out = []
    for h, fsym in enumerate(frames_symbols):
        p = fsym[10:10 + PAYLOAD] * pn
        value, ok = lich(p[:LICH])
        vch = [symbols_to_bits(p[LICH + SACCH + k * VCH:LICH + SACCH + (k + 1) * VCH]) for k in range(4)]
        out.append(dict(at=h, lich=value, lich_ok=ok, vch=vch, payload=p))
    return out


LICH_NAMES = {0b1010110: 'RDCH voice SU->', 0b1010111: 'RDCH voice CR->SU', 0b0110110: 'RTCH voice SU->TR',
              0b0110111: 'RTCH voice TR->SU', 0b1011000: 'RDCH idle SU->', 0b1011001: 'RDCH idle CR->SU',
              0b0111001: 'RTCH idle TR->SU', 0b1010000: 'RDCH 2 FACCH1 SU->', 0b1010001: 'RDCH 2 FACCH1 CR->SU',
              0b1000000: 'RDCH non-superframe 2 FACCH1 SU->', 0b1000001: 'RDCH non-superframe 2 FACCH1 CR->SU',
              0b0100001: 'RTCH non-superframe 2 FACCH1 TR->SU', 0b0110001: 'RTCH 2 FACCH1 TR->SU'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('wav')
    ap.add_argument('--scrambler', type=int, default=0, help='0 - 3: the variants tried while finding the right one (0)')
    a = ap.parse_args()
    frames_symbols = np.load(a.wav + '.frames.npy')

    variants = [a.scrambler] if a.scrambler is not None else range(4)
    scores = []
    for v in variants:
        fr = frames(frames_symbols, v)
        good = sum(1 for f in fr if f['lich_ok'] and f['lich'] in LICH_NAMES)
        scores.append((good, v, fr))
        print('scrambler %d: %d / %d LICHs known and with good parity' % (v, good, len(fr)))
    good, v, fr = max(scores, key=lambda x: x[0])
    counts = {}
    for f in fr:
        k = LICH_NAMES.get(f['lich'], '?%s%s' % (format(f['lich'], '07b'), '' if f['lich_ok'] else ' parity!'))
        counts[k] = counts.get(k, 0) + 1
    print('LICHs with scrambler %d: %s' % (v, ', '.join('%s x%d' % kv for kv in sorted(counts.items(), key=lambda x: -x[1]))))

    # SACCH (every voice frame) and FACCH1 (the halves the LICH's steal flag says)
    import l2
    sacch_ok = 0
    facch_ok = 0
    facch_n = 0
    super_bits = []
    messages = {}
    for f in fr:
        if (f['lich'] >> 5) not in (0b10, 0b01):      # RDCH / RTCH
            continue
        p = f['payload']
        sr, data, ok = l2.sacch(p[LICH:LICH + SACCH])
        f['sacch'] = (sr, data, ok)
        if ok:
            sacch_ok += 1
            structure = sr >> 6
            if structure == 3:                      # 1/4: the head of a superframe
                super_bits = []
            super_bits.append((structure, data))
            if structure == 0 and [x[0] for x in super_bits] == [3, 2, 1, 0]:
                text = l2.message(l2.to_bytes(sum((x[1] for x in super_bits), [])))
                text = 'SACCH RAN %d: %s' % (sr & 0x3F, text)
                messages[text] = messages.get(text, 0) + 1
        steal = (f['lich'] >> 1) & 3
        halves = {3: [], 2: [1], 1: [0], 0: [0, 1]}.get(steal, [])
        for h in halves:
            facch_n += 1
            start = LICH + SACCH + h * 2 * VCH
            data, ok = l2.facch1(p[start:start + 2 * VCH])
            if ok:
                facch_ok += 1
                text = 'FACCH1: ' + l2.message(l2.to_bytes(data))
                messages[text] = messages.get(text, 0) + 1
    print('SACCH: %d / %d CRC good; FACCH1: %d / %d CRC good' % (sacch_ok, sum(1 for f in fr if 'sacch' in f),
                                                                facch_ok, facch_n))
    for text, n in sorted(messages.items(), key=lambda x: -x[1]):
        print('  %s  x%d' % (text, n))

    # the voice: the VCHs of the voice frames (both halves VCH: LICH option 11)
    from ambe_decoder import Decoder, to_pcm16
    from compare import write_wav
    dec = Decoder()
    pcm = []
    errs = []
    kinds = {}
    bits_out = bytearray()
    for f in fr:
        if (f['lich'] & 0b0000110) != 0b0000110 or (f['lich'] >> 3) & 0b11 != 0b10:
            continue                   # not "superframe SACCH, VCH only"
        for b in f['vch']:
            x, kind, _, e = dec.decode_frame72(b)
            pcm.append(to_pcm16(x).astype(float))
            errs.append(e)
            kinds[kind] = kinds.get(kind, 0) + 1
            bits_out += bytes(int(''.join(map(str, b[i:i + 8])), 2) for i in range(0, 72, 8))
    if pcm:
        out = a.wav + '.decoded.wav'
        write_wav(out, np.concatenate(pcm))
        open(a.wav + '.bit', 'wb').write(bits_out)
        e = np.array(errs)
        print('voice: %d AMBE frames (%.1f s), Golay corrections %d (frames with any %d), kinds %s -> %s' % (
            len(errs), len(errs) * 0.02, e.sum(), np.sum(e > 0), kinds, out))
    else:
        print('no voice frames')


if __name__ == '__main__':
    main()
