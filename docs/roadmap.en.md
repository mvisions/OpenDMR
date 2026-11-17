# Roadmap

OpenDMR is made in spare time. This is what we plan to do, roughly in order, with **no dates**; the order may change.
Suggestions are welcome in the [issues](https://github.com/va3bpf/OpenDMR/issues), and so are pull requests.

中文：[roadmap.md](roadmap.md)

## Next

**APRS**

- Beacons on the APRS configuration's Tx frequency (OpenGD77's "Transmit frequency", "Frec TX" in the CPS), also from
  a DMR channel with an APRS configuration, back to the channel afterwards
  ([#35](https://github.com/va3bpf/OpenDMR/pull/35))
- APRS beacons in the satellite screen: on the satellite's APRS frequency (Doppler corrected) with the satellite's
  path (e.g. `RS0ISS` for the ISS, `DP0SNX` for SONATE-2) ([#55](https://github.com/va3bpf/OpenDMR/issues/55))
- On-air tests: beacons received by an APRS decoder / aprs.fi, the QSY information, satellite digipeating

**Codeplug software (OpenDMR CPS)**

- Edit the APRS configurations (up to 8: path, comment, icon, beacon frequency, QSY ...); today they are written back
  as the radio has them
- Edit DTMF and the other parts that are written back unchanged today

**Manual**

- New screenshots in the new colours

## Later

- Voice prompts
- Writing the calibration (read only today)
- "Safe Pwr-On" and "Sat (Manual / Auto)" taking effect
- Accented letters for the Spanish interface (the fonts are ASCII today)
- On-air tests: the hotspot's CW ID, satellite passes, talkaround, distance sort, the AM / SSB squelch hold

**P25** (see [p25.md](p25.md), section 6)

- No HDU on the first call after power on
- Private calls
- Weak signal sensitivity measured; tests with commercial P25 radios and MMDVM hotspots
- Repeater (duplex) operation

**NXDN** (NXDN48 receive and transmit done, see [nxdn/README.md](../nxdn/README.md), Chinese)

- An NXDN ID to callsign database (callers shown by callsign)
- A better demodulator (about 1.4 % voice frame bit errors over the air: an equaliser)
- Tests with commercial NXDN radios

## Being considered (needs much time and test equipment)

- NXDN96, NXDN trunking and encryption
- P25 encryption (DES / AES), trunking, Phase 2 (TDMA)
