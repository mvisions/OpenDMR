"""NXDN SACCH and FACCH1 (TS 1-A 4.5.2) and the layer 3 messages on them (6.2.3, 6.4).

Coding (encoder side, the decoder runs it backwards):
  data (+ CRC, init all ones) + 4 zero tail bits -> convolutional code K = 5, R = 1/2 (G1 = 1 + D^3 + D^4,
  G2 = 1 + D + D^2 + D^4, read G1, G2 alternately) -> puncturing -> interleave (written in rows, read in columns).
  SACCH:  26 bits (SR 8 + 18) + CRC6  -> 36 -> 72 -> punctured to 60 (G2 of pairs 3 and 6 of each 6 erased),
          5 rows x 12 columns.
  FACCH1: 80 bits + CRC12 -> 96 -> 192 -> punctured to 144 (G2 of pair 1 of each 2 erased), 9 rows x 16 columns.
Decoding: soft Viterbi on the symbols' bits (a punctured bit: no information).
"""

import numpy as np

G1 = 0b10011  # taps on (input, D, D^2, D^3, D^4) as bit 4 .. 0: 1 + D^3 + D^4
G2 = 0b11101  # 1 + D + D^2 + D^4


def parity(x):
    return bin(x).count('1') & 1


def conv_encode(bits):
    s = 0  # the last 4 inputs: bit 3 = D, bit 0 = D^4
    out = []
    for b in bits:
        r = (b << 4) | s
        out += [parity(r & G1), parity(r & G2)]
        s = r >> 1
    return out


def viterbi(soft):
    """soft: pairs of (G1, G2) values in -1 .. +1 (+: bit 0, -: bit 1, 0: unknown) -> the input bits"""
    n = len(soft) // 2
    INF = 1e9
    metric = np.full(16, INF)
    metric[0] = 0.0
    paths = []
    # the expected outputs of every (state, input)
    exp = np.zeros((16, 2, 2))
    nxt = np.zeros((16, 2), int)
    for s in range(16):
        for b in range(2):
            r = (b << 4) | s
            exp[s, b] = [1 - 2 * parity(r & G1), 1 - 2 * parity(r & G2)]
            nxt[s, b] = r >> 1
    for i in range(n):
        y = np.array(soft[2 * i:2 * i + 2])
        new = np.full(16, INF)
        back = np.zeros((16, 2), int)
        for s in range(16):
            if metric[s] >= INF:
                continue
            for b in range(2):
                m = metric[s] - float(np.dot(exp[s, b], y))  # correlation: higher is better
                t = nxt[s, b]
                if m < new[t]:
                    new[t] = m
                    back[t] = (s, b)
        metric = new
        paths.append(back)
    s = 0  # the tail bits bring it back to 0
    out = []
    for back in reversed(paths):
        prev, b = back[s]
        out.append(b)
        s = prev
    return out[::-1]


def crc(bits, width, poly):
    """poly without the top term, e.g. CRC6 x^6 + x^5 + x^2 + x + 1 -> 0b100111; register starts all ones"""
    reg = (1 << width) - 1
    top = 1 << (width - 1)
    for b in bits:
        fb = ((reg & top) != 0) ^ b
        reg = (reg << 1) & ((1 << width) - 1)
        if fb:
            reg ^= poly
    return [(reg >> (width - 1 - i)) & 1 for i in range(width)]


CRC6 = 0b100111            # x^6 + x^5 + x^2 + x + 1
CRC12 = 0b100000001111     # x^12 + x^11 + x^3 + x^2 + x + 1


def deinterleave(values, rows, cols):
    """received in columns of a rows x cols matrix written in rows -> the order written"""
    out = [0.0] * (rows * cols)
    k = 0
    for c in range(cols):
        for r in range(rows):
            out[r * cols + c] = values[k]
            k += 1
    return out


def depuncture(values, keep):
    """keep: the pattern of one period over the encoded bits (1: sent); the erased ones come back as 0"""
    out = []
    it = iter(values)
    while True:
        for k in keep:
            if k:
                try:
                    out.append(next(it))
                except StopIteration:
                    return out
            else:
                out.append(0.0)


SACCH_KEEP = [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0]   # G1, G2 of pairs 1 - 6: G2 of pairs 3 and 6 erased
FACCH1_KEEP = [1, 0, 1, 1]                           # pairs 1 - 2: G2 of pair 1 erased


def soft_bits(symbols):
    """Each symbol -> its two bits as soft values (+: 0, -: 1). Dibit: +3 01, +1 00, -1 10, -3 11: the first bit is
    the sign, the second the magnitude (outer: 1)"""
    out = []
    for v in symbols:
        first = np.clip(v / 2, -1, 1)              # + : 0
        second = np.clip((abs(v) - 2) / 1, -1, 1)  # outer (|v| ~ 3): bit 1 -> negative soft value
        out += [first, -second]
    return out


def decode(symbols, rows, cols, keep, data_bits, crc_width, crc_poly):
    soft = depuncture(deinterleave(soft_bits(symbols), rows, cols), keep)
    bits = viterbi(soft)
    data, check = bits[:data_bits], bits[data_bits:data_bits + crc_width]
    return data, crc(data, crc_width, crc_poly) == check


def sacch(symbols):
    """30 symbols -> (SR 8 bits as int, 18 data bits, CRC ok)"""
    data, ok = decode(symbols, 5, 12, SACCH_KEEP, 26, 6, CRC6)
    sr = int(''.join(map(str, data[:8])), 2)
    return sr, data[8:], ok


def facch1(symbols):
    """72 symbols -> (80 message bits, CRC ok)"""
    return decode(symbols, 9, 16, FACCH1_KEEP, 80, 12, CRC12)


def to_bytes(bits):
    bits = list(bits) + [0] * (-len(bits) % 8)
    return bytes(int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


MESSAGES = {0x3F: 'PROP_FORM', 0x01: 'VCALL', 0x03: 'VCALL_IV', 0x08: 'TX_REL', 0x07: 'TX_REL_EX', 0x10: 'IDLE', 0x09: 'DCALL',
            0x0B: 'DCALL', 0x0F: 'HEAD_DLY', 0x11: 'DISC'}
CALL_TYPES = {0: 'broadcast', 1: 'group', 2: 'unspecified', 4: 'individual', 6: 'interconnect', 7: 'speed dial'}
MODES = {0: '4800 EHR', 2: '9600 EHR', 3: '9600 EFR'}
CIPHERS = {0: 'clear', 1: 'scramble', 2: 'DES', 3: 'AES'}


def message(data):
    """A layer 3 message (bytes) -> text"""
    kind = data[0] & 0x3F
    name = MESSAGES.get(kind, 'type %02X' % kind)
    if kind in (0x01, 0x08) and len(data) >= 8:   # VCALL, TX_REL: the same layout to the IDs
        call_type = data[2] >> 5
        src = (data[3] << 8) | data[4]
        dst = (data[5] << 8) | data[6]
        text = '%s %s %d -> %s%d' % (name, CALL_TYPES.get(call_type, '?%d' % call_type), src,
                                    'TG ' if call_type in (0, 1) else '', dst)
        if kind == 0x01:
            text += ', %s, %s%s' % (MODES.get(data[2] & 7, '?'), CIPHERS[data[7] >> 6],
                                     ' key %d' % (data[7] & 0x3F) if data[7] >> 6 else '')
            if data[1] & 0x80:
                text += ', EMERGENCY'
        return text
    if kind == 0x3F and len(data) >= 2:          # maker-defined (6.4.4.1): the maker number, the text in it
        text = ''.join(chr(c) for c in data[2:] if 0x20 <= c < 0x7F)
        return '%s maker %02X: %s%s' % (name, data[1], data[2:].hex(), ' "%s"' % text if text else '')
    return '%s %s' % (name, data.hex())


# ---- the transmit side ---------------------------------------------------------------------------------------

DIBIT_SYMBOL = {(0, 1): 3, (0, 0): 1, (1, 0): -1, (1, 1): -3}


def bits_to_symbols(bits):
    return [DIBIT_SYMBOL[(bits[i], bits[i + 1])] for i in range(0, len(bits), 2)]


def encode(data, crc_width, crc_poly, keep, rows, cols):
    enc = conv_encode(list(data) + crc(data, crc_width, crc_poly) + [0] * 4)
    pk = keep * (len(enc) // len(keep))
    sent = [b for b, k in zip(enc, pk) if k]
    inter = [0] * len(sent)
    for r in range(rows):
        for c in range(cols):
            inter[c * rows + r] = sent[r * cols + c]
    return bits_to_symbols(inter)


def sacch_encode(sr, data18):
    """SR (8 bits) + 18 bits -> 30 symbols"""
    bits = [(sr >> (7 - i)) & 1 for i in range(8)] + list(data18)
    return encode(bits, 6, CRC6, SACCH_KEEP, 5, 12)


def facch1_encode(message):
    """a message of up to 10 bytes -> 72 symbols"""
    m = bytes(message) + bytes(10 - len(message))
    return encode(bits_of(m), 12, CRC12, FACCH1_KEEP, 9, 16)


def bits_of(data):
    return [(c >> (7 - i)) & 1 for c in data for i in range(8)]


def vcall(src, dst, call_type=1, mode=0, cipher=0, key=0, emergency=False):
    """VCALL (6.4.1.1): 8 bytes"""
    return bytes([0x01, 0x80 if emergency else 0x00, (call_type << 5) | mode, src >> 8, src & 0xFF, dst >> 8,
                  dst & 0xFF, (cipher << 6) | key])


def tx_rel(src, dst, call_type=1):
    """TX_REL (6.4.1.6): the same layout to the IDs"""
    return bytes([0x08, 0x00, call_type << 5, src >> 8, src & 0xFF, dst >> 8, dst & 0xFF])


if __name__ == '__main__':
    # self test: encode, puncture, interleave, back
    import random
    rnd = random.Random(1)
    for name, n, w, poly, rows, cols, keep in (('SACCH', 26, 6, CRC6, 5, 12, SACCH_KEEP),
                                                ('FACCH1', 80, 12, CRC12, 9, 16, FACCH1_KEEP)):
        data = [rnd.randint(0, 1) for _ in range(n)]
        enc = conv_encode(data + crc(data, w, poly) + [0] * 4)
        pk = keep * (len(enc) // len(keep))
        sent = [b for b, k in zip(enc, pk) if k]
        inter = [0] * len(sent)
        for r in range(rows):
            for c in range(cols):
                inter[c * rows + r] = sent[r * cols + c]
        # bits -> symbols (dibits)
        sym = []
        for i in range(0, len(inter), 2):
            sym.append({(0, 1): 3, (0, 0): 1, (1, 0): -1, (1, 1): -3}[(inter[i], inter[i + 1])])
        got, ok = decode(sym, rows, cols, keep, n, w, poly)
        print(name, len(sent), 'bits sent, round trip', 'OK' if (got == data and ok) else 'FAILED')
