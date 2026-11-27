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
 * OpenDMR, screen: the dual watch (dual_watch.h). After OpenDM32 user_interface/uiDualWatch.c.
 *
 * Two paths, each any channel or VFO A / B (settings.dual_watch_path: a channel number, -1 VFO A, -2 VFO B; 0 is VFO A
 * for the first path, VFO B for the second), the same one twice allowed (both panels shown, one path watched).
 * Watched in turn, a dwell on
 * each; a carrier (FM) or timeslot sync (DMR) is checked for audio, then it stays on that path while the signal lasts
 * and DW_HANG_MS after it (the answer).
 *
 * The home screen with one more path watched (the user's design, 2026-11-25): one path is the selected one
 * (BIT_DW_TX_1 / _2), and it is the channel or VFO of the home screen under this one. Turned on there, that channel or
 * VFO is the selected path, on top; the other path is the other one of the last time (the same allowed). UP / DOWN
 * select the upper / lower path (the home screen goes to it). Every other key is the home screen's, done on it under
 * this screen (ui_handle_under()): the knob, LEFT / RIGHT, the digits, *, #, SK1 / SK2 with them, the left key (its
 * quick menu, where the dual watch is turned off; held: the main menu), the right key (channel <-> VFO, held: VFO
 * A / B).
 * A scan started there pauses the dual watch (the radio has one receiver): the home screen scans, the dual watch is
 * back when the scan stops (dual_watch_scan_ended(), on the channel it stopped on). The pause is in RAM only: the
 * option stays on, also over a power off during the scan (#198, #204). SK2 + the right key turns it off ("Close" on
 * its soft key while SK2 is held). Off: the home screen is the selected path.
 *
 * The PTT: on the path heard last for DW_FOLLOW_MS after its signal (the answer), else on the selected path.
 */

#include <stdio.h>
#include <string.h>
#include "widgets.h"
#include "draw.h"
#include "fonts.h"
#include "icons.h"
#include "settings.h"
#include "codeplug.h"
#include "codeplug_text.h"
#include "systime.h"
#include "radio.h"
#include "dmr.h"
#include "dmr_ids.h"
#include "last_heard.h"
#include "tones.h"
#include "text.h"
#include "channel_screen.h"
#include "channel_details.h"
#include "vfo_screen.h"
#include "lock_screen.h"
#include "keymap.h"
#include "tx_screen.h"
#include "tx_target.h"
#include "dual_watch.h"

#define BIT_DUAL_WATCH    (1UL << 10) // BIT_DUAL_WATCH (BIT_UNUSED_1)
#define BIT_DW_TX_1       (1UL << 25) // the selected path: the first (neither, older settings: the first too)
#define BIT_DW_TX_2       (1UL << 26) // the second

#define DW_TICK_MS        10
#define DW_DWELL_FM_MS    135   // as the VFO dual watch of OpenGD77
#define DW_DWELL_DMR_MS   150   // the HR_C7000 needs a few timeslots to see a DMR signal
#define DW_SETTLE_MS      30    // after a change of frequency, before looking for a signal
#define DW_CHECK_FM_MS    500   // carrier seen: time for the squelch and the tone to open the audio
#define DW_CHECK_DMR_MS   1500  // sync seen: time for the voice (1 superframe + 1 timeslot, 4 times)
#define DW_HANG_MS        3000  // after the signal, on that path, for the answer
#define DW_FOLLOW_MS      10000 // the transmission follows the path heard during this time after its signal
#define DW_REDRAW_RX_MS   250
#define SQUELCH_MIN          1 // codeplug sql: 0 the band default, 1 .. 21: 0 .. 100 % (as the channel screen)
#define SQUELCH_PERCENT_STEP 5

#define PANEL_TOP    (WIDGET_STATUS_BAR_HEIGHT + 2)
#define PANEL_HEIGHT ((WIDGET_BOTTOM_BAR_TOP - PANEL_TOP) / 2)

typedef enum {
    STATE_WATCHING, // switching between the two paths
    STATE_CHECKING, // something on the path: does it open the audio
    STATE_RECEIVING,
    STATE_HANG // after the signal (or our transmission), staying on the path
} state_t;

typedef struct {
    codeplug_channel_t channel;
    uint32_t talk_group; // DMR: the contact of the channel, or the first of its RX group; the selected: its target
    char name[20];
    bool vfo;
} path_t;

static path_t paths[2];
static int current = 0;
static state_t state = STATE_WATCHING;
static uint32_t state_ms;  // when the path was tuned, or the state started
static uint32_t signal_ms; // the last time the signal was there
static int heard = -1;     // the path heard last
static uint32_t heard_ms;
static uint32_t redraw_ms;
static bool opening = false;     // turned on: the home screen's channel or VFO becomes the selected path, on top
static bool transmitted = false; // the transmit screen was pushed: back from it, stay on that path
static bool sk2_held = false;    // the right soft key says "Close" (SK2 + the right key turns the dual watch off)
static bool scan_paused = false; // a scan started on the home screen: off until it stops, the option kept on
// The squelch of each channel path as it was on the home screen (changed with the keys there), kept while the dual
// watch is on (#175): the home screen forgets its changes when it goes to the other path. A VFO keeps its own
static struct {
    int16_t ref; // the channel; 0: none
    uint8_t sql;
} kept[2];

bool dual_watch_is_on(void)
{
    return ((settings.bitfield_options & BIT_DUAL_WATCH) != 0) && !scan_paused;
}

void dual_watch_set(bool on)
{
    scan_paused = false; // turned on or off (the quick menu) during a scan: as asked
    opening = on && !dual_watch_is_on();
    if (on != dual_watch_is_on()) {
        memset(kept, 0, sizeof(kept)); // on or off: the channels' squelch as they have it
    }
    settings_set_option(BIT_DUAL_WATCH, on);
    settings_changed(); // kept over power off (#176)
    settings_save_if_changed();
}

void dual_watch_scan_ended(void)
{
    ui_event_t ev = {.type = UI_EVENT_DATA, .what = UI_DATA_DUAL_WATCH};

    if (!scan_paused) {
        return;
    }
    scan_paused = false;
    // shown by the home screen when on top, after this event (scan_stop() may run in its leave(), during a push);
    // another screen on top (a menu): the home screen's enter shows it when that one is gone
    (void)ui_post(&ev);
}

bool dual_watch_show(void)
{
    if (!dual_watch_is_on()) {
        return false;
    }
    ui_push(&dual_watch_screen, NULL);
    return true;
}

static int16_t path_ref(int i)
{
    int16_t ref = settings.dual_watch_path[i];

    return (ref == 0) ? (int16_t)(-1 - i) : ref;
}

static bool paths_same(void)
{
    return path_ref(0) == path_ref(1);
}

static int selected(void)
{
    return (settings.bitfield_options & BIT_DW_TX_2) ? 1 : 0;
}

static void set_selected(int i)
{
    settings_set_option(BIT_DW_TX_1, i == 0);
    settings_set_option(BIT_DW_TX_2, i == 1);
}

// The home screen's channel or VFO: the selected path (turned on: on top, the other one of the last time below)
static void paths_from_home(void)
{
    int16_t home = (int16_t)channel_details_current_ref();
    int sel = selected();

    if (home == 0) {
        return; // no channel shown
    }
    if (opening) {
        int16_t other;

        opening = false;
        if ((settings.dual_watch_path[0] == 0) && (settings.dual_watch_path[1] == 0)) {
            other = (home == -1) ? -2 : -1; // the first time: a VFO
        } else {
            other = (path_ref(1 - sel) != home) ? path_ref(1 - sel) : path_ref(sel);
        }
        settings.dual_watch_path[0] = home;
        settings.dual_watch_path[1] = other;
        set_selected(0);
        settings_changed();
    } else if (path_ref(sel) != home) {
        settings.dual_watch_path[sel] = home; // changed there (another channel, the VFO, ...)
        settings_changed();
    }
}

// The home screen's channel for the radio (its changes made with the keys, the TG picked), NULL: none
static const codeplug_channel_t *home_channel(void)
{
    const ui_screen_t *home = vfo_screen_is_home() ? &vfo_screen : &channel_screen;

    return home->channel ? home->channel() : NULL;
}

static void load_path(int i)
{
    int16_t ref = path_ref(i);
    path_t *p = &paths[i];
    // the selected path, or the same channel or VFO on the other: the home screen's, so both follow what is changed
    const codeplug_channel_t *home = ((i == selected()) || (ref == path_ref(selected()))) ? home_channel() : NULL;
    codeplug_contact_t contact;
    codeplug_rx_group_t group;

    if ((ref > 0) && codeplug_channel_in_use(ref) && (home || codeplug_get_channel(ref, &p->channel))) {
        p->vfo = false;
        if (home) {
            memcpy(&p->channel, home, sizeof(p->channel));
        } else if (kept[i].ref == ref) {
            p->channel.sql = kept[i].sql;
        }
        codeplug_text_name(p->channel.name, CODEPLUG_NAME_LENGTH, p->name, sizeof(p->name));
    } else {
        int n = (ref == -2) ? 1 : 0;

        memcpy(&p->channel, home ? home : vfo_screen_vfo(n), sizeof(p->channel));
        // the VFO's own power (0: the radio's), as the VFO screen
        p->vfo = true;
        snprintf(p->name, sizeof(p->name), "VFO %c", (n == 1) ? 'B' : 'A');
    }
    p->talk_group = 9; // as the VFO screen when nothing is set
    if (p->channel.mode != CODEPLUG_MODE_DMR) {
        return;
    }
    if (home) {
        tx_target_t target;

        tx_target_get(&p->channel, &target);
        if (target.id != 0) {
            p->talk_group = target.id;
        }
        return;
    }
    if ((p->channel.rx_group_list != 0) && codeplug_get_rx_group(p->channel.rx_group_list, &group) &&
        (group.contact_count > 0) && codeplug_get_contact(group.contacts[0], &contact)) {
        p->talk_group = contact.id;
    }
    if ((p->channel.contact != 0) && codeplug_get_contact(p->channel.contact, &contact)) {
        p->talk_group = contact.id |
                        ((contact.call_type == CODEPLUG_CALL_PRIVATE) ? ((uint32_t)TX_TARGET_PC_FLAG << 24) : 0);
    }
}

// The paths again; the selected one's squelch kept when it is a channel (load_path())
static void load_paths(void)
{
    int sel = selected();

    load_path(0);
    load_path(1);
    if (!paths[sel].vfo) {
        kept[sel].ref = path_ref(sel);
        kept[sel].sql = paths[sel].channel.sql;
    }
}

// The path the radio is on (radio_channel(), after the event), and its TX ID (the selected one: the home screen's
// target, set when its channel is asked)
static void tune_path(int i, uint32_t now)
{
    current = i;
    state_ms = now;
    if ((i == selected()) && home_channel()) {
        return; // asking the home screen for its channel gave the radio its target
    }
    if (paths[i].channel.mode == CODEPLUG_MODE_DMR) {
        dmr_set_tx_id(paths[i].talk_group);
    }
}

static int tx_path(uint32_t now)
{
    if (paths_same()) {
        return selected(); // one path watched: shown twice, the PTT tag on the selected panel
    }
    if ((state == STATE_RECEIVING) || (state == STATE_HANG)) {
        return current;
    }
    if ((heard >= 0) && ((now - heard_ms) < DW_FOLLOW_MS)) {
        return heard; // the answer
    }
    return selected();
}

static bool dmr(void)
{
    return paths[current].channel.mode == CODEPLUG_MODE_DMR;
}

// Every DW_TICK_MS (uiDualWatch.c watch()); true: redraw
static bool watch(uint32_t now)
{
    uint32_t elapsed = now - state_ms;
    state_t was = state;

    switch (state) {
        case STATE_WATCHING:
            if (elapsed < DW_SETTLE_MS) {
                break;
            }
            if (radio_audio_heard()) {
                state = STATE_RECEIVING;
                signal_ms = now;
            } else if (dmr() ? dmr_has_sync() : radio_has_carrier()) {
                state = STATE_CHECKING;
                state_ms = now;
            } else if ((elapsed >= (dmr() ? DW_DWELL_DMR_MS : DW_DWELL_FM_MS)) && !paths_same()) {
                tune_path(1 - current, now);
            }
            break;
        case STATE_CHECKING:
            if (radio_audio_heard()) {
                state = STATE_RECEIVING;
                signal_ms = now;
            } else if (elapsed >= (dmr() ? DW_CHECK_DMR_MS : DW_CHECK_FM_MS)) {
                state = STATE_WATCHING; // nothing for us (another tone, another colour code): go on
                if (!paths_same()) {
                    tune_path(1 - current, now);
                }
            }
            break;
        case STATE_RECEIVING:
        case STATE_HANG:
            if (radio_audio_heard()) {
                state = STATE_RECEIVING;
                signal_ms = now;
                heard = current;
                heard_ms = now;
            } else {
                if (state == STATE_RECEIVING) {
                    state = STATE_HANG;
                }
                if ((now - signal_ms) >= DW_HANG_MS) {
                    state = STATE_WATCHING;
                    state_ms = now;
                }
            }
            break;
    }
    if ((state != was) || ((state == STATE_RECEIVING) && ((now - redraw_ms) >= DW_REDRAW_RX_MS))) {
        redraw_ms = now;
        return true;
    }
    return false;
}

// The channel of the screen (ui_screen_t.channel): the path watched
static const codeplug_channel_t *radio_channel(void)
{
    return &paths[current].channel;
}

static void enter(void *arg)
{
    uint32_t now = systime_get_ms();
    bool from_tx = transmitted; // back from the transmission (uiDualWatchPrepareTx())

    (void)arg;
    transmitted = false;
    sk2_held = false;
    paths_from_home();
    load_paths();
    if (from_tx) {
        tune_path(current, now);
        signal_ms = now;
    } else {
        tune_path(selected(), now);
        state = STATE_WATCHING;
    }
    radio_set_scanning(true); // no receive beeps at each path
    ui_timer_start(DW_TICK_MS);
}

static void leave(void)
{
    radio_set_scanning(false);
}

// Back on top after the home screen took a key: the selected path as it is there now; changed (another channel, a
// frequency, ...): listened to at once
static void resume(void)
{
    codeplug_channel_t before;
    int sel = selected();
    int16_t ref = path_ref(sel);

    memcpy(&before, &paths[sel].channel, sizeof(before));
    paths_from_home();
    load_paths();
    if ((path_ref(sel) != ref) || (memcmp(&before, &paths[sel].channel, sizeof(before)) != 0)) {
        tune_path(sel, systime_get_ms());
        state = STATE_WATCHING;
    } else if (current == sel) {
        (void)home_channel(); // its target again
    }
    radio_set_scanning(true);
    ui_timer_start(DW_TICK_MS);
}

// Kept on top after the home screen took a key: not when it started a scan (paused until it stops: the scan is theirs)
static bool keep(void)
{
    if ((channel_screen_scanning() || vfo_screen_scanning()) && dual_watch_is_on()) {
        scan_paused = true;
    }
    return dual_watch_is_on();
}

// The home screen on the selected path (done under this screen)
static bool go_to_selected(void *arg)
{
    int16_t ref = path_ref(selected());

    (void)arg;
    if (ref < 0) {
        int n = -1 - ref;

        if (vfo_screen_current() != n) {
            settings.current_vfo_number = (uint8_t)n;
            settings_changed();
        }
        if (!vfo_screen_is_home()) {
            vfo_screen_show();
        }
    } else if (channel_screen_select(ref) && vfo_screen_is_home()) {
        vfo_screen_leave();
    }
    return true;
}

static void select_path(int i)
{
    if (i == selected()) {
        return;
    }
    set_selected(i);
    settings_changed();
    if (ui_under(go_to_selected, NULL, keep)) {
        if ((path_ref(i) > 0) && (kept[i].ref == path_ref(i)) && !vfo_screen_is_home()) {
            channel_screen_set_squelch(kept[i].sql); // the home screen on that channel again, with its squelch
        }
        resume();
    }
}

// The PTT: on the transmit path, then stay on it for the answer
static void transmit(void)
{
    uint32_t now = systime_get_ms();
    int p = tx_path(now);

    if (p != current) {
        tune_path(p, now);
    }
    state = STATE_HANG;
    signal_ms = now;
    heard = p;
    heard_ms = now;
    transmitted = true;
    tx_screen_open(text(TEXT_DUAL_WATCH), paths[p].name, &paths[p].channel);
}

static bool handle(const ui_event_t *ev)
{
    switch (ev->type) {
        case UI_EVENT_TIMER: {
            bool redraw = watch(systime_get_ms());

            ui_timer_start(DW_TICK_MS);
            return redraw;
        }
        case UI_EVENT_DATA:
            load_paths();
            return true;
        case UI_EVENT_ROTARY:
        case UI_EVENT_KEY_PRESS:
        case UI_EVENT_KEY_LONG:
        case UI_EVENT_KEY_REPEAT:
        case UI_EVENT_KEY_RELEASE:
            break;
        default:
            return false;
    }

    if ((ev->type != UI_EVENT_ROTARY) && (ev->key == UI_KEY_PTT)) {
        if ((ev->type == UI_EVENT_KEY_PRESS) && !lock_screen_filter(ev)) {
            transmit();
        }
        return false;
    }
    // SK2 + the right key: the dual watch off, back to the home screen on the selected path. The keymap sees the key
    // (SK2 then was combined: not its own action on release); the rest of the key goes to the home screen, which
    // takes no release without its press
    if ((ev->type != UI_EVENT_ROTARY) && (ev->key == UI_KEY_RED) && (ev->modifiers & UI_MODIFIER_SK2)) {
        (void)keymap_action(ev, vfo_screen_is_home() ? KEYMAP_SCREEN_VFO : KEYMAP_SCREEN_CHANNEL);
        if ((ev->type == UI_EVENT_KEY_PRESS) && !lock_screen_filter(ev)) {
            dual_watch_set(false);
            ui_pop();
        }
        return false;
    }
    if ((ev->type != UI_EVENT_ROTARY) && (ev->key == UI_KEY_SK2) &&
        ((ev->type == UI_EVENT_KEY_PRESS) || (ev->type == UI_EVENT_KEY_RELEASE))) {
        sk2_held = (ev->type == UI_EVENT_KEY_PRESS); // and the key goes on to the home screen
    }
    // UP / DOWN alone: the upper / lower path selected (its press; the rest of the key is ours too)
    if ((ev->type != UI_EVENT_ROTARY) && ((ev->key == UI_KEY_UP) || (ev->key == UI_KEY_DOWN)) &&
        !(ev->modifiers & (UI_MODIFIER_SK1 | UI_MODIFIER_SK2)) && (channel_screen_typed() == 0)) {
        if ((ev->type == UI_EVENT_KEY_PRESS) && !lock_screen_filter(ev)) {
            select_path((ev->key == UI_KEY_UP) ? 0 : 1);
            return true;
        }
        return false;
    }
    // Any other key: the home screen's, on the selected path
    if (ui_handle_under(ev, keep)) {
        resume();
        return true;
    }
    return false;
}

static void draw_panel(int i, int tx)
{
    const path_t *p = &paths[i];
    const codeplug_channel_t *ch = &p->channel;
    int32_t top = PANEL_TOP + (i * PANEL_HEIGHT);
    int32_t x = WIDGET_MARGIN + 4;
    int32_t lx = x;
    bool receiving = ((i == current) || paths_same()) && ((state == STATE_RECEIVING) || (state == STATE_HANG));
    bool ptt = (i == tx);
    bool typing = (i == selected()) && !vfo_screen_is_home() && (channel_screen_typed() > 0);
    int32_t right = FB_WIDTH - WIDGET_MARGIN;
    int power = (ch->libre_dmr_power != 0) ? (ch->libre_dmr_power - 1) : settings.tx_power_level;
    char buffer[48];
    char detail[24];
    dmr_call_t call;

    // The path with a signal: a green bar on the left
    if (i == 1) { // between the two paths, to be seen
        draw_fill_rect(WIDGET_MARGIN, top - 2, FB_WIDTH - (2 * WIDGET_MARGIN), 2, THEME_COLOUR_OFF);
    }
    if (receiving) {
        draw_fill_rect(0, top + 4, 5, PANEL_HEIGHT - 8, THEME_COLOUR_RX);
    }

    // A DMR call heard on this path: who is talking takes the large line, the path's name goes to the header
    bool caller = receiving && (ch->mode == CODEPLUG_MODE_DMR) && dmr_call(&call);
    bool known = false; // its callsign: the large line, the ID top right; else the ID large
    char who[LAST_HEARD_TEXT_SIZE];

    if (caller) {
        dmr_ids_caller_text(call.source, who, sizeof(who)); // "callsign name": the callsign only
        who[strcspn(who, " ")] = '\0';
        known = (who[0] != '\0');
        if (!known) {
            snprintf(who, sizeof(who), "%lu", (unsigned long)call.source);
        }
    }

    // CH n or VFO (a call: the path's name); on the right "PTT" (the transmit path), the mode and the power
    if (caller) {
        snprintf(buffer, sizeof(buffer), "%s", p->name);
    } else if (p->vfo) {
        snprintf(buffer, sizeof(buffer), "VFO");
    } else {
        snprintf(buffer, sizeof(buffer), "CH %d", path_ref(i));
    }
    draw_text(lx, top + 8, buffer, &font_roboto17, FONT_ALIGN_LEFT, THEME_COLOUR_TEXT_LABEL);
    // The transmit path: the transmit icon, white on the transmit colour (as the TX labels), in a place of its own kept
    // free on the other path too: the mode and the power stay where they are
    int32_t ptt_w = 22;

    if (ptt) {
        draw_fill_rect(right - ptt_w, top + 8, ptt_w, 20, THEME_COLOUR_TX);
        icons_draw(right - ptt_w + 2, top + 9, ICONS_TX, THEME_COLOUR_WHITE); // its art: 16 px of 20 from the left
    }
    right -= ptt_w + 6;
    if (known) {
        snprintf(buffer, sizeof(buffer), "ID %lu", (unsigned long)call.source);
    } else {
        snprintf(buffer, sizeof(buffer), "%s  %s", codeplug_mode_name(ch->mode),
                 bottom_bar_power_label((power < 10) ? power : 9));
    }
    draw_text(right, top + 8, buffer, &font_roboto17, FONT_ALIGN_RIGHT, THEME_COLOUR_TEXT_LABEL);

    // The squelch of the analog modes (#175) on the name's line, right: its icon and the value, at the name's baseline
    int32_t name_w = (FB_WIDTH - WIDGET_MARGIN) - x;

    if (codeplug_mode_is_analog(ch->mode)) {
        int sql = (ch->sql != 0) ? ch->sql : settings.squelch_defaults[radio_band_of(ch->rx_freq)];
        int32_t baseline = top + 32 + font_roboto32_bold.ascent;
        int32_t sq_x;

        snprintf(buffer, sizeof(buffer), "%d%%", (sql - SQUELCH_MIN) * SQUELCH_PERCENT_STEP);
        sq_x = FB_WIDTH - WIDGET_MARGIN - font_text_width(&font_roboto17, buffer);
        draw_text(FB_WIDTH - WIDGET_MARGIN, baseline - font_roboto17.ascent, buffer, &font_roboto17, FONT_ALIGN_RIGHT,
                  THEME_COLOUR_TEXT_LABEL);
        sq_x -= 4 + ICONS_SQUELCH_WIDTH;
        icons_draw(sq_x, baseline - 15, ICONS_SQUELCH, THEME_COLOUR_TEXT_LABEL); // its bars end on row 14
        name_w = sq_x - 8 - x;
    }

    // The name, large; a call: the caller's callsign (its ID when not known); typed on the selected path: the channel
    // number or the frequency
    if ((i == selected()) && vfo_screen_is_home() && vfo_screen_draw_entry(x, top + 32, &font_roboto32_bold)) {
        // the frequency being typed
    } else if (typing) {
        snprintf(buffer, sizeof(buffer), "-> %d", channel_screen_typed());
        draw_text(x, top + 32, buffer, &font_roboto32_bold, FONT_ALIGN_LEFT, THEME_COLOUR_TEXT);
    } else {
        draw_text_fitted(x, top + 32, (caller ? who : p->name), &font_roboto32_bold, name_w, THEME_COLOUR_TEXT);
    }

    // "RX" and "TX" small, each before its frequency; the selected VFO: in the one the knob and the digits change, the
    // digits its step changes marked (^), green (RX) or red (TX) (SK2 + UP / DOWN choose it)
    bool edited_vfo = (i == selected()) && p->vfo && vfo_screen_is_home();

    lx = x;
    for (int f = 0; f < 2; f++) {
        uint32_t frequency = f ? ch->tx_freq : ch->rx_freq;
        int32_t start;

        lx = font_draw_text(lx, top + 70 + (font_roboto20.ascent - font_roboto14.ascent), text(f ? TEXT_UI_TX : TEXT_UI_RX),
                            &font_roboto14, FONT_ALIGN_LEFT, theme_colour(THEME_COLOUR_TEXT_LABEL)) +
             2;
        snprintf(buffer, sizeof(buffer), "%lu.%05lu", (unsigned long)(frequency / 100000),
                 (unsigned long)(frequency % 100000));
        start = lx;
        lx = font_draw_text(lx, top + 70, buffer, &font_roboto20, FONT_ALIGN_LEFT,
                            theme_colour(THEME_COLOUR_TEXT_SECOND));
        if (edited_vfo && ((f == 1) == vfo_screen_editing_tx())) {
            // one pixel lower than the frequency line's room: clear of its digits
            vfo_screen_draw_step_marks(start, top + 71, buffer, &font_roboto20, vfo_screen_step(), f == 1, 5);
        }
        lx += 6; // both within the margin: xxx.xxxxx twice
    }

    // Receiving: the S meter; else the timeslot and TG, or the tone
    if (receiving) {
        s_meter_data_t meter = {.compact = true, .active = true, .open = radio_is_receiving()};

        s_meter_set_signal(&meter, radio_signal_dbm());
        s_meter_draw(top + 96, &meter);
        return;
    }
    detail[0] = '\0';
    if (ch->mode == CODEPLUG_MODE_DMR) {
        snprintf(detail, sizeof(detail), "TS%d  TG %lu", ((ch->flag2 & 0x40) ? 2 : 1),
                 (unsigned long)(p->talk_group & CODEPLUG_CONTACT_ID_MAX));
    } else {
        uint16_t tone = (ch->rx_tone != CODEPLUG_CSS_NONE) ? ch->rx_tone : ch->tx_tone;

        if (tone != CODEPLUG_CSS_NONE) {
            tones_format(tone, detail, sizeof(detail));
        }
    }
    if (detail[0] != '\0') {
        draw_text(x, top + 96, detail, &font_roboto17, FONT_ALIGN_LEFT,
                  THEME_COLOUR_TEXT_LABEL);
    }
}

static void draw(void)
{
    status_bar_data_t status = {0};
    s_meter_data_t meter = {.active = true, .open = radio_is_receiving()};
    bool typing = vfo_screen_is_home() ? vfo_screen_typing() : (channel_screen_typed() > 0);

    // the signal bars as the home screens: from the S meter's reading (#175)
    s_meter_set_signal(&meter, radio_signal_dbm());
    status.state = meter.open ? STATUS_BAR_RECEIVING : STATUS_BAR_IDLE;
    status.signal_bars = s_meter_bars(&meter);
    status_bar_draw(&status);
    draw_panel(0, tx_path(systime_get_ms()));
    draw_panel(1, tx_path(systime_get_ms()));
    if (typing) {
        bottom_bar_draw_soft_keys(text(TEXT_UI_OK), text(TEXT_UI_DELETE)); // as on the home screens
    } else {
        // The right key: where it goes (the selected path to the VFO or back to its channel); SK2 held: Close
        const char *right = sk2_held ? text(TEXT_UI_CLOSE) : (vfo_screen_is_home() ? text(TEXT_APRS_CHANNEL) : "VFO");

        bottom_bar_draw_soft_keys(text(TEXT_MENU), right);
    }
}

const ui_screen_t dual_watch_screen = {
    .enter = enter,
    .leave = leave,
    .handle = handle,
    .draw = draw,
    .channel = radio_channel,
};
