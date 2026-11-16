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
 * OpenDMR, screen: what the scans leave out (scan.c), from the quick menu: the channels or VFO frequencies locked out
 * with * until power off (nuisance delete), and the VFO frequencies locked out for good (* held). A row each, the
 * left key unlocks it (back in the scans); the last row unlocks them all. Empty: the list closes.
 */

#include <stdio.h>
#include "codeplug.h"
#include "codeplug_text.h"
#include "list_screen.h"
#include "scan.h"
#include "text.h"
#include "ui.h"
#include "lockouts.h"

static void frequency_name(uint32_t f, char *buffer, size_t size)
{
    snprintf(buffer, size, "%lu.%05lu MHz", (unsigned long)(f / 100000), (unsigned long)(f % 100000));
}

static void after_unlock(int left)
{
    if (left == 0) {
        ui_pop();
        return;
    }
    if (*ui_state() >= left + 1) {
        *ui_state() = left; // the "unlock all" row
    }
    ui_redraw(); // the list stays: one row less
}

/* Locked out until power off: the channels */

static int channels_count(void)
{
    return scan_skipped_channels.count + 1;
}

static void channels_name(int index, char *buffer, size_t size)
{
    codeplug_channel_t c;

    if (index >= scan_skipped_channels.count) {
        snprintf(buffer, size, "%s", text(TEXT_UNLOCK_ALL));
    } else if (codeplug_get_channel((int)scan_skipped_channels.item[index], &c)) {
        codeplug_text_name(c.name, CODEPLUG_NAME_LENGTH, buffer, size);
    } else {
        snprintf(buffer, size, "%lu", (unsigned long)scan_skipped_channels.item[index]);
    }
}

static void channels_pick(int index)
{
    if (index >= scan_skipped_channels.count) {
        scan_skipped_channels.count = 0;
    } else {
        scan_skipped_remove(&scan_skipped_channels, index);
    }
    after_unlock(scan_skipped_channels.count);
}

/* Locked out until power off: VFO frequencies */

static int frequencies_count(void)
{
    return scan_skipped_frequencies.count + 1;
}

static void frequencies_name(int index, char *buffer, size_t size)
{
    if (index >= scan_skipped_frequencies.count) {
        snprintf(buffer, size, "%s", text(TEXT_UNLOCK_ALL));
    } else {
        frequency_name(scan_skipped_frequencies.item[index], buffer, size);
    }
}

static void frequencies_pick(int index)
{
    if (index >= scan_skipped_frequencies.count) {
        scan_skipped_frequencies.count = 0;
    } else {
        scan_skipped_remove(&scan_skipped_frequencies, index);
    }
    after_unlock(scan_skipped_frequencies.count);
}

/* Locked out for good: VFO frequencies */

static int saved_count(void)
{
    return scan_saved_count() + 1;
}

static void saved_name(int index, char *buffer, size_t size)
{
    if (index >= scan_saved_count()) {
        snprintf(buffer, size, "%s", text(TEXT_UNLOCK_ALL));
    } else {
        frequency_name(scan_saved_frequency(index), buffer, size);
    }
}

static void saved_pick(int index)
{
    if (index >= scan_saved_count()) {
        scan_saved_clear();
    } else {
        scan_saved_remove(index);
    }
    after_unlock(scan_saved_count());
}

static const ui_pick_list_t channel_list = {
    .title = TEXT_SCAN_SKIPPED_MENU,
    .icon = ICONS_COUNT,
    .count = channels_count,
    .name = channels_name,
    .pick = channels_pick,
    .action = TEXT_UNLOCK,
};

static const ui_pick_list_t frequency_list = {
    .title = TEXT_SCAN_SKIPPED_MENU,
    .icon = ICONS_COUNT,
    .count = frequencies_count,
    .name = frequencies_name,
    .pick = frequencies_pick,
    .action = TEXT_UNLOCK,
};

static const ui_pick_list_t saved_list = {
    .title = TEXT_SCAN_SAVED_MENU,
    .icon = ICONS_COUNT,
    .count = saved_count,
    .name = saved_name,
    .pick = saved_pick,
    .action = TEXT_UNLOCK,
};

void lockouts_open(lockouts_t which)
{
    const ui_pick_list_t *list = ((which == LOCKOUTS_CHANNELS) ? &channel_list
                                  : (which == LOCKOUTS_FREQUENCIES) ? &frequency_list
                                                                    : &saved_list);

    ui_replace(&pick_list_screen, (void *)list);
}
