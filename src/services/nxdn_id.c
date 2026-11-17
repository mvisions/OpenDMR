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

/*
 * OpenDMR, service: the radio's NXDN ID (nxdn_id.h), read from the codeplug's custom data each time (the CPS may
 * write it while the radio runs).
 */

#include "codeplug.h"
#include "custom_data.h"
#include "nxdn_id.h"

#define NXDN_ID_DATA_TYPE 0x44540006 // a custom data block of this firmware ("DT", 6)
#define NXDN_ID_VERSION   1

typedef struct {
    uint8_t version;
    uint8_t zero;
    uint8_t id[2]; // little endian
} stored_t;

uint16_t nxdn_id_stored(void)
{
    stored_t s;

    if (!custom_data_read(NXDN_ID_DATA_TYPE, (uint8_t *)&s, sizeof(s)) || (s.version != NXDN_ID_VERSION)) {
        return 0;
    }
    return (uint16_t)(s.id[0] | (s.id[1] << 8));
}

uint16_t nxdn_id_get(void)
{
    uint16_t id = nxdn_id_stored();

    return (id != 0) ? id : (uint16_t)codeplug_get_dmr_id();
}

void nxdn_id_set(uint16_t id)
{
    stored_t s = {.version = NXDN_ID_VERSION, .zero = 0, .id = {(uint8_t)id, (uint8_t)(id >> 8)}};

    (void)custom_data_write(NXDN_ID_DATA_TYPE, (const uint8_t *)&s, sizeof(s));
}
