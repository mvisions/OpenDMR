"""NXDN transmit side in software: a conventional (RDCH) group call from AMBE+2 frames, as an IQ recording that
demod.py / frames.py (or another receiver) decode.

  python nxdn/py/tx.py voice.bit out.wav [--src 1234] [--dst 9] [--ran 1] [--baud 2400] [--snr 20] [--offset 300]

Frames (TS 1-A 4.4.2.2, LICH Table 5.2-2, SU -> CR/SU):
  preamble (24 bits) only before the first frame,
  1 frame   non-superframe SACCH, two FACCH1 (LICH 1000000): VCALL in both FACCH1
  n frames  superframe SACCH, VCH only (LICH 1010110): 4 VCH each, VCALL over 4 SACCHs (SR 1/4 .. 4/4)
  1 frame   non-superframe SACCH, two FACCH1 (LICH 1000000): TX_REL in both (MMDVMHost ends a call on that only)
Modulation: impulses at the symbol levels -> root raised cosine (alpha 0.2) and a one-symbol hold (P(f), sinc) ->
FM (+3 = 1050 Hz at 2400 symbols/s, 2400 Hz at 4800) -> 48 kHz I/Q.
"""
import argparse
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import l2  # noqa: E402
from frames import scrambler  # noqa: E402

FS = 48000
FSW = [-3, 1, -3, 3, -3, -3, 3, 3, -1, 3]
PREAMBLE = 0x5775FD          # Table 4.4-1: 24 bits
LICH_FIRST = 0b1000000       # non-superframe SACCH, two FACCH1, SU
LICH_VOICE = 0b1010110       # superframe SACCH, VCH only, SU
LICH_LAST = 0b1000000        # as the first: non-superframe SACCH, two FACCH1, SU


def lich_symbols(value):
    bits = [(value >> (6 - i)) & 1 for i in range(7)]
    bits.append(sum(bits[:4]) % 2)          # even parity of the 4 MSBs
    return [-3 if b else 3 for b in bits]   # 1 -> 11 (-3), 0 -> 01 (+3)


def frame(lich, sacch, middle):
    """FSW + scrambled (LICH 8, SACCH 30, 144 symbols of VCH / FACCH1)"""
    body = np.array(lich_symbols(lich) + list(sacch) + list(middle), float)
    assert len(body) == 182
    pn = 1 - 2 * scrambler(0)
    return list(FSW) + list(body * pn)


def vch_symbols(frame9):
    return l2.bits_to_symbols(l2.bits_of(frame9))


def call(voice, src, dst, ran, baud):
    mode = 0 if baud == 2400 else 2
    vc = l2.vcall(src, dst, mode=mode)
    vc72 = l2.bits_of(vc + bytes(1))        # SACCH superframe: 72 bits
    rel = l2.tx_rel(src, dst)
    syms = []
    syms += [{0b01: 3, 0b00: 1, 0b10: -1, 0b11: -3}[(PREAMBLE >> (22 - 2 * i)) & 3] for i in range(12)]
    # first: the single SACCH carries the first 18 bits of the VCALL (structure 00: single)
    syms += frame(LICH_FIRST, l2.sacch_encode(ran & 0x3F, vc72[:18]),
                  l2.facch1_encode(vc) + l2.facch1_encode(vc))
    voice = list(voice)
    voice += [voice[-1]] * (-len(voice) % 4)
    n = 0
    for k in range(0, len(voice), 4):
        part = n % 4                        # 0: 1/4 (structure 11) .. 3: 4/4 (00)
        sr = ((3 - part) << 6) | (ran & 0x3F)
        mid = []
        for f in voice[k:k + 4]:
            mid += vch_symbols(f)
        syms += frame(LICH_VOICE, l2.sacch_encode(sr, vc72[18 * part:18 * part + 18]), mid)
        n += 1
    syms += frame(LICH_LAST, l2.sacch_encode(ran & 0x3F, l2.bits_of(rel)[:18]),
                  l2.facch1_encode(rel) + l2.facch1_encode(rel))
    return np.array(syms, float), n


def rrc(alpha, sps, span=8):
    t = (np.arange(-span * sps, span * sps + 1)) / sps
    h = np.zeros_like(t)
    for i, x in enumerate(t):
        if abs(x) < 1e-9:
            h[i] = 1 - alpha + 4 * alpha / np.pi
        elif abs(abs(x) - 1 / (4 * alpha)) < 1e-9:
            h[i] = alpha / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * alpha)) +
                                         (1 - 2 / np.pi) * np.cos(np.pi / (4 * alpha)))
        else:
            h[i] = (np.sin(np.pi * x * (1 - alpha)) + 4 * alpha * x * np.cos(np.pi * x * (1 + alpha))) / \
                   (np.pi * x * (1 - (4 * alpha * x) ** 2))
    return h


def modulate(symbols, baud, snr=None, offset=0.0, lead=0.3):
    sps = FS / baud
    if abs(sps - round(sps)) > 1e-9:
        raise SystemExit('48000 / baud must be whole')
    sps = int(round(sps))
    x = np.zeros(len(symbols) * sps)
    x[::sps] = symbols
    shaped = np.convolve(x, rrc(0.2, sps), 'same')
    shaped = np.convolve(shaped, np.ones(sps), 'same')            # P(f): a one-symbol hold
    held = np.zeros(80 * sps)
    held[40 * sps::sps] = 1.0                                     # +1 symbols from the middle on
    steady = np.convolve(np.convolve(held, rrc(0.2, sps), 'same'), np.ones(sps), 'same')[60 * sps]
    dev = 1050.0 if baud == 2400 else 2400.0
    freq = shaped / steady * dev / 3 + offset
    pad = int(lead * FS)
    freq = np.r_[np.full(pad, offset), freq, np.full(pad, offset)]
    phase = 2 * np.pi * np.cumsum(freq) / FS
    iq = np.exp(1j * phase)
    if snr is not None:                                           # in the channel (+-6.25 / 12.5 kHz) bandwidth
        bw = 6250 if baud == 2400 else 12500
        noise_power = 10 ** (-snr / 10) * FS / bw
        iq = iq + np.sqrt(noise_power / 2) * (np.random.default_rng(1).standard_normal(len(iq)) +
                                              1j * np.random.default_rng(2).standard_normal(len(iq)))
    else:
        iq = iq + 0
    return iq


def write_iq(path, iq):
    a = np.clip(np.round(np.c_[iq.real, iq.imag] * 12000), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(a.tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bits', help='AMBE+2 frames, 9 bytes each (e.g. <wav>.bit from frames.py)')
    ap.add_argument('out')
    ap.add_argument('--src', type=int, default=1234)
    ap.add_argument('--dst', type=int, default=9)
    ap.add_argument('--ran', type=int, default=1)
    ap.add_argument('--baud', type=int, default=2400, choices=[2400, 4800])
    ap.add_argument('--snr', type=float, default=None, help='dB in the channel bandwidth (default: no noise)')
    ap.add_argument('--offset', type=float, default=0.0, help='carrier offset, Hz')
    a = ap.parse_args()
    d = open(a.bits, 'rb').read()
    voice = [d[i:i + 9] for i in range(0, len(d) - 8, 9)]
    syms, n = call(voice, a.src, a.dst, a.ran, a.baud)
    write_iq(a.out, modulate(syms, a.baud, a.snr, a.offset))
    print('%s: %d voice frames in %d frames (+ first and last), %d symbols, %.1f s; %d -> TG %d, RAN %d, %d symbols/s%s'
          % (a.out, len(voice), n, len(syms), len(syms) / a.baud, a.src, a.dst, a.ran, a.baud,
             '' if a.snr is None else ', SNR %.0f dB' % a.snr))


if __name__ == '__main__':
    main()
