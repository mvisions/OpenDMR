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

#include <stdio.h>
#include "util.h"
#include "widgets.h"
#include "draw.h"
#include "fonts.h"

// S meter of docs/manual (all the time in receive, squelch open or not): the reading, then 13 segments, S1 - S9
// and +10 - +40 dB. Full (channel screen): reading above the segments, scale below. Compact (VFO screen, dual watch):
// reading and segments on one line. The area is cleared when not active (transmitting).
#define SEGMENTS        13
#define GAP             3
#define COMPACT_READING 70 // width of the reading in the compact form

// The usual scale: S1 at -121 dBm, 6 dB a unit, S9 at -73 dBm. With no antenna the receiver reads -140 dBm (VHF) and
// -135 dBm (UHF), and a quiet channel outdoors shows S0; indoors, electronics' noise can light S1 (-116 dBm on VHF
// away from a computer). The main firmware's S1 (the raw reading 81: -96 dBm VHF, -86 dBm UHF) left fair signals at
// S0 (issue #42)
#define DBM_S1      (-121)
#define DB_PER_UNIT 6
#define DBM_S9      (DBM_S1 + (8 * DB_PER_UNIT))
#define OVER_S9_MAX 60

void s_meter_set_signal(s_meter_data_t *data, int dbm)
{
    data->s_units = 0;
    data->over_s9 = 0;
    if (dbm >= DBM_S1) {
        data->s_units = (int8_t)MIN(9, 1 + ((dbm - DBM_S1) / DB_PER_UNIT));
        data->over_s9 = (int8_t)CLAMP(dbm - DBM_S9, 0, OVER_S9_MAX);
    }
}

int8_t s_meter_bars(const s_meter_data_t *data)
{
    return (int8_t)(((data->s_units * ICONS_SIGNAL_BARS) + 8) / 9);
}

void s_meter_draw(int32_t y, const s_meter_data_t *data)
{
    static const char *const scale[SEGMENTS] = {"1",  NULL, "3",  NULL,  "5",  NULL, "7",
                                                NULL, "9",  NULL, "+20", NULL, "+40"};
    const int32_t bar_x = WIDGET_MARGIN + (data->compact ? COMPACT_READING : 0);
    const int32_t width = FB_WIDTH - WIDGET_MARGIN - bar_x;
    const int32_t segment = (width - ((SEGMENTS - 1) * GAP)) / SEGMENTS;
    // compact: as high as the reading's capitals and digits beside it (roboto20: 14 rows from 5 below the top)
    const int32_t bar_height = (data->compact ? 14 : 12);
    const int32_t bar_y = (data->compact ? (y + 5) : (y + 30));
    char reading[12];

    draw_fill_rect(0, y, FB_WIDTH, (data->compact ? S_METER_COMPACT_HEIGHT : S_METER_HEIGHT), THEME_COLOUR_BACKGROUND);

    if (!data->active) {
        return;
    }

    const font_t *font = (data->compact ? &font_roboto20 : &font_roboto22);
    const font_t *small = (data->compact ? &font_roboto14 : &font_roboto17);

    snprintf(reading, sizeof(reading), "S%d", ((data->over_s9 > 0) ? 9 : data->s_units));
    draw_text(WIDGET_MARGIN, y, reading, font, FONT_ALIGN_LEFT, (data->open ? THEME_COLOUR_RX : THEME_COLOUR_TEXT));
    if (data->over_s9 > 0) {
        // over S9: "+20dB" smaller and red, on the same baseline
        snprintf(reading, sizeof(reading), "+%ddB", data->over_s9);
        draw_text(WIDGET_MARGIN + font_text_width(font, "S9") + 2, y + font->ascent - small->ascent, reading, small,
                  FONT_ALIGN_LEFT, THEME_COLOUR_TX);
    }

    for (int32_t i = 0; i < SEGMENTS; i++) {
        int32_t x = bar_x + (i * (segment + GAP));
        bool lit = ((i < 9) ? (i < data->s_units) : (((i - 9) * 10) < data->over_s9));

        draw_fill_rect(x, bar_y, segment, bar_height,
                       (lit ? ((i < 9) ? THEME_COLOUR_RX : THEME_COLOUR_TX) : THEME_COLOUR_OFF));

        if (!data->compact && scale[i]) {
            draw_text(x + (segment / 2), bar_y + bar_height + 4, scale[i], &font_roboto12, FONT_ALIGN_CENTER,
                      THEME_COLOUR_TEXT_DIM);
        }
    }
}
