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

#ifndef DM32_EXTRA_OPTIONS_H
#define DM32_EXTRA_OPTIONS_H

#include <stdbool.h>
#include <stdint.h>

// Options of ours that the OpenGD77 settings have no room for, in a block of our own after them (extra_options.c)
#define EXTRA_OPTION_HIDE_CALLER_PLACE (1UL << 0) // the DMR caller panel without the city and state (qso_panel.c)
// bit 1: the receive log (rx_log.h, a test firmware: 0.4.1-debug): set on radios that ran it, so not reused
#define EXTRA_OPTION_HIDE_RECENT_CALLERS (1UL << 2) // the channel screen's last two callers (off: shown)
#define EXTRA_OPTION_AUTO_TIMEZONE       (1UL << 3)

// APRS "Send via": bits 1..2 of the same block, a 2 bit value (0: AFSK, 1: DMR, 2: both)
#define APRS_VIA_AFSK 0u
#define APRS_VIA_DMR  1u
#define APRS_VIA_BOTH 2u
#define APRS_VIA_MASK (3UL << 1)

// Destination for APRS positions sent over DMR (LRRP to the APRS gateway). Stored in our own flash block, not in
// settings_t, so the OpenGD77 CPS layout stays untouched. 222999 (the Italian gateway) is the default; the APRS
// options menu, the Dg cable command and tools/debug/radio.py change it (BrandMeister's common gateway is 5057).
#define APRS_DMR_GATEWAY_DEFAULT 222999u // 0x036717

void extra_options_load(void); // after flash_init()
bool extra_option(uint32_t bit);
void extra_option_set(uint32_t bit, bool on); // saved at once
uint8_t extra_options_theme(void);          // the theme chosen (display.c); 0xFF: none yet
void extra_options_set_theme(uint8_t theme); // saved at once
uint8_t extra_options_aprs_via(void);                     // APRS_VIA_AFSK / DMR / BOTH
void extra_options_set_aprs_via(uint8_t via);             // saved at once
uint32_t extra_options_aprs_dmr_gateway(void);            // 24 bit DMR ID, default when unset
void extra_options_set_aprs_dmr_gateway(uint32_t id);     // saved at once
void extra_options_keep_block(uint32_t sector_address, uint8_t *sector); // a CPS sector write keeps the block

#endif
