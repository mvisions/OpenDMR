/*
 * Copyright (C) 2026 Junqiang Shi, VA3BPF / BG8AM
 *
 * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
 * following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
 *    disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
 *    following disclaimer in the documentation and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
 *    products derived from this software without specific prior written permission.
 *
 * 4. Use of this source code or binary releases for commercial purposes is strictly forbidden without the written
 *    permission of the copyright holder. This includes, without limitation, incorporation in a commercial product or
 *    incorporation into a product or project which allows commercial use.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef NXDN_RADIO_H
#define NXDN_RADIO_H

#include <stdbool.h>
#include <stdint.h>

// The NXDN48 receiver (nxdn/README.md): the HR_C7000's FM recording (its AF input, the FD6818's discriminator with
// the DMR settings) read every 32 ms, demodulated and decoded in software (nxdn_core.c), the voice through our AMBE+2
// vocoder to the prompt path (the baseband stays in FM). Started by radio.c on an NXDN channel, once the RF and the
// modem are set up as for DMR. Transmit: the mic through our AMBE+2 encoder, the symbols through the P25 physical
// layer's transmit (nxdn_radio.c).

typedef struct {
    bool active;   // a call is being received
    uint8_t type;  // VCALL call type: 0 broadcast, 1 group, 4 individual ...
    uint8_t ran;   // the SACCH's RAN
    uint16_t src;  // 0: not known yet
    uint16_t dst;  // the group or the unit called
} nxdn_call_t;

void nxdn_radio_start(void);
void nxdn_radio_stop(void);
bool nxdn_radio_call(nxdn_call_t *out);        // the call now (false: none)
bool nxdn_radio_heard_within(uint32_t ms);     // a frame decoded lately (scan)
uint32_t nxdn_call_tg_or_pc(const nxdn_call_t *c); // as last heard keeps it

// The channel's RAN (0: any received; transmitted as it is), our ID (individual calls to others ignored) and where a
// transmission goes: a group, or a unit (individual) (tx_target.c sets them). The PTT on / off, transmitting until the
// last frame is sent (nxdn_radio_transmitting())
void nxdn_radio_set_target(uint8_t ran, uint16_t src, uint16_t dst, bool individual);
void nxdn_radio_transmit(bool on);
bool nxdn_radio_transmitting(void);

// counters, read over the cable
typedef struct {
    uint32_t halves, missed_halves, frames, lich_bad, sacch_ok, vch, facch_ok, hunts, lost_sync;
    uint32_t pcm_drops, underruns, calls, busy_max_us;
    uint32_t dec_us_max, dec_us_sum, demod_us_sum, feed_writes; // our AMBE decoder; the rest of the halves' work
    uint32_t other_ran;                                         // frames of another RAN than the channel's
} nxdn_radio_stats_t;
extern volatile nxdn_radio_stats_t nxdn_radio_stats;

#endif
