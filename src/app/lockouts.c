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
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */


/*
 * OpenDMR: what the scans leave out (scan.c).
 *
 * The main menu's "Scan lockouts": all of them, one row each, the kind on the right:
 *   Temp       a channel or VFO frequency locked out with * until power off (nuisance delete)
 *   Saved      a VFO frequency locked out for good (* held, or the quick menu)
 *   Zone skip  a channel with the codeplug's Zone Skip (* held in a zone, the quick menu, the CPS, channel details)
 *   All skip   a channel with All Skip (the all channels zone)
 * The menu key on a row unlocks it (back in the scans), the last row unlocks them all.
 *
 * The quick menu's "Scan lockout": the current channel or VFO frequency only, on (locked out for good) or off.
 */

#include <stdio.h>
#include "codeplug.h"
#include "codeplug_text.h"
#include "list_screen.h"
#include "scan.h"
#include "text.h"
#include "ui.h"
#include "channel_screen.h"
#include "vfo_screen.h"
#include "lockouts.h"

#define FLAG4_ZONE_SKIP 0x20 // channel_details.c
#define FLAG4_ALL_SKIP  0x10
#define FLAG4_SKIPS     (FLAG4_ZONE_SKIP | FLAG4_ALL_SKIP)
#define FLAGGED_MAX     128 // channels with a skip flag listed

/* The current channel or VFO frequency (the quick menu) */

static bool channel_flags(int number, uint8_t *flags)
{
    codeplug_channel_t c;

    if ((number <= 0) || !codeplug_get_channel(number, &c)) {
        return false;
    }
    *flags = c.flag4;
    return true;
}

static void channel_unflag(int number)
{
    codeplug_channel_t c;

    if (codeplug_get_channel(number, &c) && (c.flag4 & FLAG4_SKIPS)) {
        c.flag4 &= (uint8_t)~FLAG4_SKIPS;
        (void)codeplug_write_channel(number, &c);
    }
}

static void temp_remove(scan_skipped_t *skipped, uint32_t value)
{
    for (int i = skipped->count - 1; i >= 0; i--) {
        if (skipped->item[i] == value) {
            scan_skipped_remove(skipped, i);
        }
    }
}

bool lockouts_current_locked(void)
{
    if (vfo_screen_is_home()) {
        uint32_t f = vfo_screen_vfo(vfo_screen_current())->rx_freq;

        return scan_saved_has(f) || scan_skipped_has(&scan_skipped_frequencies, f);
    }

    int number = channel_screen_channel;
    uint8_t flags = 0;

    return (channel_flags(number, &flags) && (flags & FLAG4_SKIPS)) ||
           scan_skipped_has(&scan_skipped_channels, (uint32_t)number);
}

bool lockouts_set_current(bool on)
{
    if (vfo_screen_is_home()) {
        uint32_t f = vfo_screen_vfo(vfo_screen_current())->rx_freq;

        if (on) {
            return scan_saved_add(f);
        }
        temp_remove(&scan_skipped_frequencies, f);
        for (int i = scan_saved_count() - 1; i >= 0; i--) {
            if (scan_saved_frequency(i) == f) {
                scan_saved_remove(i);
            }
        }
        return true;
    }

    int number = channel_screen_channel;

    if (on) {
        return channel_screen_lock_out(number);
    }
    temp_remove(&scan_skipped_channels, (uint32_t)number);
    channel_unflag(number);
    return true;
}

/* The list (the main menu) */

typedef enum { KIND_TEMP_CHANNEL, KIND_TEMP_FREQUENCY, KIND_SAVED, KIND_FLAGGED, KIND_ALL } kind_t;

static uint16_t flagged[FLAGGED_MAX]; // the channel numbers with a skip flag, found when the list opens
static int flagged_count;

static void find_flagged(void)
{
    uint8_t flags;

    flagged_count = 0;
    for (int n = CODEPLUG_CHANNELS_MIN; (n <= CODEPLUG_CHANNELS_MAX) && (flagged_count < FLAGGED_MAX); n++) {
        if (codeplug_channel_in_use(n) && channel_flags(n, &flags) && (flags & FLAG4_SKIPS)) {
            flagged[flagged_count++] = (uint16_t)n;
        }
    }
}

static int entries(void)
{
    return scan_skipped_channels.count + scan_skipped_frequencies.count + scan_saved_count() + flagged_count;
}

// What row index is: its kind and its index in that kind's list
static kind_t row(int index, int *at)
{
    if (index >= entries()) {
        return KIND_ALL;
    }
    if (index < scan_skipped_channels.count) {
        *at = index;
        return KIND_TEMP_CHANNEL;
    }
    index -= scan_skipped_channels.count;
    if (index < scan_skipped_frequencies.count) {
        *at = index;
        return KIND_TEMP_FREQUENCY;
    }
    index -= scan_skipped_frequencies.count;
    if (index < scan_saved_count()) {
        *at = index;
        return KIND_SAVED;
    }
    *at = index - scan_saved_count();
    return KIND_FLAGGED;
}

static void frequency_text(uint32_t f, char *buffer, size_t size)
{
    snprintf(buffer, size, "%lu.%05lu", (unsigned long)(f / 100000), (unsigned long)(f % 100000));
}

static void channel_text(int number, char *buffer, size_t size)
{
    codeplug_channel_t c;

    if (codeplug_get_channel(number, &c)) {
        codeplug_text_name(c.name, CODEPLUG_NAME_LENGTH, buffer, size);
    } else {
        snprintf(buffer, size, "%d", number);
    }
}

static int count(void)
{
    int n = entries();

    return n ? (n + 1) : 0; // and "unlock all"; none: the list says it is empty
}

// Where the selection starts: the list is made again when it opens
static int current(void)
{
    find_flagged();
    return 0;
}

static void name(int index, char *buffer, size_t size)
{
    int at = 0;

    switch (row(index, &at)) {
        case KIND_TEMP_CHANNEL:
            channel_text((int)scan_skipped_channels.item[at], buffer, size);
            break;
        case KIND_TEMP_FREQUENCY:
            frequency_text(scan_skipped_frequencies.item[at], buffer, size);
            break;
        case KIND_SAVED:
            frequency_text(scan_saved_frequency(at), buffer, size);
            break;
        case KIND_FLAGGED:
            channel_text(flagged[at], buffer, size);
            break;
        default:
            snprintf(buffer, size, "%s", text(TEXT_UNLOCK_ALL));
            break;
    }
}

static void value(int index, char *buffer, size_t size)
{
    int at = 0;
    uint8_t flags = 0;

    buffer[0] = '\0';
    switch (row(index, &at)) {
        case KIND_TEMP_CHANNEL:
        case KIND_TEMP_FREQUENCY:
            snprintf(buffer, size, "%s", text(TEXT_LOCKOUT_TEMP));
            break;
        case KIND_SAVED:
            snprintf(buffer, size, "%s", text(TEXT_LOCKOUT_SAVED));
            break;
        case KIND_FLAGGED:
            if (channel_flags(flagged[at], &flags)) {
                snprintf(buffer, size, "%s", text((flags & FLAG4_ZONE_SKIP) ? TEXT_ZONE_SKIP : TEXT_ALL_SKIP));
            }
            break;
        default:
            break;
    }
}

static void pick(int index)
{
    int at = 0;

    switch (row(index, &at)) {
        case KIND_TEMP_CHANNEL:
            scan_skipped_remove(&scan_skipped_channels, at);
            break;
        case KIND_TEMP_FREQUENCY:
            scan_skipped_remove(&scan_skipped_frequencies, at);
            break;
        case KIND_SAVED:
            scan_saved_remove(at);
            break;
        case KIND_FLAGGED:
            channel_unflag(flagged[at]);
            break;
        default:
            scan_skipped_channels.count = 0;
            scan_skipped_frequencies.count = 0;
            scan_saved_clear();
            for (int i = 0; i < flagged_count; i++) {
                channel_unflag(flagged[i]);
            }
            break;
    }
    find_flagged();
    if (*ui_state() >= count()) {
        *ui_state() = (count() > 0) ? (count() - 1) : 0;
    }
    ui_redraw(); // the list stays, a row less
}

const ui_pick_list_t lockouts_list = {
    .title = TEXT_SCAN_LOCKOUTS,
    .icon = ICONS_COUNT,
    .count = count,
    .current = current,
    .name = name,
    .value = value,
    .pick = pick,
    .action = TEXT_UNLOCK,
};
