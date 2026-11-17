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
 * OpenDMR, service: the NXDN48 receiver (nxdn_radio.h, nxdn/README.md).
 *
 * The modem records its AF input (the FD6818's discriminator, the DMR settings kept) in two halves of 256 samples;
 * the task reads each half as the modem finishes it (every 32 ms) into nxdn_core.c, which finds the frames and decodes
 * them. Voice frames (VCH, AMBE+2 in DMR's bit order) go through our vocoder into a queue of 20 ms frames; a second,
 * small task feeds them into the prompt FIFO (8 kHz, the path the beeps take), which plays while the modem stays in FM.
 * The caller and the group come from the SACCH superframe (VCALL) or a FACCH1; a TX_REL or no voice for CALL_TIMEOUT
 * ends the call. The demodulator's state and the voice queue live in the vocoder's overlay RAM after its own.
 */

#include <string.h>

#include "FreeRTOS.h"
#include "task.h"
#include "hw.h"
#include "leds.h"
#include "modem.h"
#include "systime.h"
#include "vocoder.h"
#include "radio.h"
#include "p25_phy.h"
#include "nxdn_core.h"
#include "nxdn_radio.h"
#include "ui.h"
#include "last_heard.h"
#include "dmr_ids.h"
#include "flash.h"

#define PCM_FRAMES     16   // 320 ms of decoded voice
#define PLAY_START     6    // frames queued before the playback starts: they come 4 at a time every 80 ms, a frame
                            // decoded once its last half (32 ms) is read
#define CALL_TIMEOUT   320  // ms without a voice frame: the call ended (a frame is 80 ms)
#define AMP_START_MS   75   // the amplifier on before the voice (sound.c)
#define POLL_MS        4    // the recording looked at this often (a half is 32 ms)
#define TAP_SAMPLES    2048 // the last samples as recorded, for tools over the cable (256 ms)
#define VCH_LOG        256  // the last voice frames received, for tools over the cable (5 s)

#define OVERLAY_BSS __attribute__((section(".vocoder_bss"))) // zeroed by the vocoder's load, ours after its own

volatile nxdn_radio_stats_t nxdn_radio_stats;

static nxdn_rx rx OVERLAY_BSS;
static nxdn_sacch_super super OVERLAY_BSS;
static int16_t pcm[PCM_FRAMES][160] OVERLAY_BSS;
static volatile uint32_t pcm_in, pcm_out;  // frames put in / taken out (the feeder's)
static uint32_t pcm_pos;                    // samples of pcm[pcm_out] already in the FIFO (the feeder's)
int16_t nxdn_tap[TAP_SAMPLES] OVERLAY_BSS; // the recording, nxdn_tap_n samples in so far (ring)
volatile uint32_t nxdn_tap_n;
volatile uint32_t nxdn_tap_hold; // not 0 (over the cable): the tap kept as it is, to be read out whole
// what the tap keeps (over the cable): 0 the recording, 1 the vocoder's output, 2 the samples into the FIFO
volatile uint32_t nxdn_tap_source;

static void tap_put(const int16_t *x, int n)
{
    if (nxdn_tap_hold) {
        return;
    }
    for (int i = 0; i < n; i++) {
        nxdn_tap[(nxdn_tap_n + (uint32_t)i) % TAP_SAMPLES] = x[i];
    }
    nxdn_tap_n += (uint32_t)n;
}
// A test of the vocoder and the playback without the air (over the cable, nxdn/py/flash_play.py): AMBE frames (9
// bytes each) in the flash window from nxdn_play_address, nxdn_play_frames of them played 4 every 80 ms as a call
// would bring them, around and around until nxdn_play_frames is 0 again; the received voice ignored meanwhile
volatile uint32_t nxdn_play_address, nxdn_play_frames;
static uint32_t play_index;
static TickType_t play_next;
uint8_t nxdn_vch_log[VCH_LOG][9] OVERLAY_BSS; // the voice frames as received (ring, nxdn_vch_log_n so far), for
volatile uint32_t nxdn_vch_log_n;              // nxdn/py/vch_check.py against the frames sent

static StaticTask_t task_tcb, feed_tcb;
static StackType_t task_stack[1280]; // 5 KB: the frame decoding and our AMBE decoder
static StackType_t feed_stack[192];
static TaskHandle_t task, feeder;
static volatile bool running;
static volatile bool busy; // the task is using the overlay

static nxdn_call_t call;
static TickType_t last_voice;
static volatile TickType_t heard_at;
static volatile bool heard;

/* the playback, the feeder's: 0 off, 1 the amplifier starting, 2 playing */
static volatile int play_state;
volatile uint32_t nxdn_feed_blocks = 1; // blocks into the FIFO a tick at most (16 samples: 2 x real time); over the cable
static TickType_t play_since;
static volatile bool play_wanted;

/* ---- the call ---- */

static struct {
    bool active;
    uint16_t src;
    uint32_t tg_or_pc;
} published;

uint32_t nxdn_call_tg_or_pc(const nxdn_call_t *c)
{
    return (c->type == 4) ? (((uint32_t)LAST_HEARD_PC_FLAG << 24) | c->dst) : c->dst;
}

static void call_publish(void)
{
    uint32_t tg_or_pc = nxdn_call_tg_or_pc(&call);
    char text[LAST_HEARD_TEXT_SIZE];

    if ((call.active == published.active) && (call.src == published.src) && (tg_or_pc == published.tg_or_pc)) {
        return;
    }
    if (call.active && (call.src != 0) && ((call.src != published.src) || (tg_or_pc != published.tg_or_pc))) {
        dmr_ids_caller_text(call.src, text, sizeof(text));
        last_heard_add(call.src, tg_or_pc, LAST_HEARD_TS_UNKNOWN, text[0] ? text : NULL);
    }
    published.active = call.active;
    published.src = call.src;
    published.tg_or_pc = tg_or_pc;

    ui_event_t ev = {.type = UI_EVENT_DATA, .what = UI_DATA_SIGNAL};

    ui_post(&ev);
}

static void call_begin(void)
{
    if (!call.active) {
        memset(&call, 0, sizeof(call));
        call.active = true;
        vocoderReset();
        nxdn_radio_stats.calls++;
    }
}

static void call_end(void)
{
    call.active = false;
    play_wanted = false; // the feeder plays out what is queued, then stops
    memset(&super, 0, sizeof(super));
    call_publish();
}

// a VCALL or TX_REL (SACCH superframe or FACCH1): who and to whom
static void message(const uint8_t *msg, int len, uint8_t ran)
{
    uint8_t type;
    uint16_t src, dst;

    if (!nxdn_msg_call(msg, len, &type, &src, &dst)) {
        return;
    }
    if ((msg[0] & 0x3F) == NXDN_MSG_TX_REL) {
        if (call.active) {
            call_end();
        }
        return;
    }
    call_begin();
    call.type = type;
    call.src = src;
    call.dst = dst;
    call.ran = ran;
}

/* ---- the voice ---- */

static void voice(const uint8_t ambe[9])
{
    if ((pcm_in - pcm_out) >= PCM_FRAMES) { // the feeder fell behind: the newest frame dropped
        nxdn_radio_stats.pcm_drops++;
        return;
    }
    memcpy(nxdn_vch_log[nxdn_vch_log_n % VCH_LOG], ambe, 9);
    nxdn_vch_log_n++;
    uint32_t t0 = systime_get_us();
    vocoderDecodeFrame(ambe, pcm[pcm_in % PCM_FRAMES]);
    uint32_t took = systime_get_us() - t0;
    if (nxdn_tap_source == 1) {
        tap_put(pcm[pcm_in % PCM_FRAMES], 160);
    }
    nxdn_radio_stats.dec_us_sum += took;
    if (took > nxdn_radio_stats.dec_us_max) {
        nxdn_radio_stats.dec_us_max = took;
    }
    pcm_in++;
    nxdn_radio_stats.vch++;
    if ((pcm_in - pcm_out) >= PLAY_START) {
        play_wanted = true;
    }
}

static void on_frame(void *ctx, const nxdn_frame_t *f)
{
    (void)ctx;
    nxdn_radio_stats.frames++;
    if (!f->lich_ok) {
        nxdn_radio_stats.lich_bad++;
        return;
    }
    heard = true;
    heard_at = xTaskGetTickCount();
    if (f->sacch_ok) {
        nxdn_radio_stats.sacch_ok++;
    }
    uint8_t msg[9];
    if (nxdn_sacch_add(&super, f, msg)) {
        message(msg, 9, (uint8_t)(f->sacch_sr & 0x3F));
    }
    for (int h = 0; h < 2; h++) {
        if (f->facch_ok & (1u << h)) {
            nxdn_radio_stats.facch_ok++;
            message(f->facch[h], 10, (uint8_t)(f->sacch_sr & 0x3F));
        }
    }
    // a call begins with a frame whose SACCH or FACCH1 CRC holds (LICH parity alone: 1 in 2 by chance), noise
    // decoded as voice otherwise
    if (f->halves && (call.active || f->sacch_ok || f->facch_ok) && !nxdn_play_frames) {
        call_begin();
        last_voice = xTaskGetTickCount();
        for (int k = 0; k < 4; k++) {
            if (f->halves & (1u << (k / 2))) {
                voice(f->vch[k]);
            }
        }
    }
    call_publish();
}

/* ---- the playback: the prompt FIFO (8 kHz, 16 bits little endian, MODEM_BEEP_BLOCK bytes a write) ---- */

static void play_on(bool on)
{
    if (on) {
        radio_beep_path(true);
        modem_beep(true);
        radio_dmr_audio(true);
        leds_green(true);
    } else {
        radio_dmr_audio(false);
        modem_beep(false);
        radio_beep_path(false);
        leds_green(false);
    }
}

static void feed_task(void *arg)
{
    uint8_t block[MODEM_BEEP_BLOCK];

    (void)arg;
    for (;;) {
        vTaskDelay(1);
        int state = play_state;
        if (state == 0) {
            if (running && play_wanted) {
                play_on(true);
                play_since = xTaskGetTickCount();
                play_state = 1;
            }
            continue;
        }
        if (state == 1) { // the amplifier starting: silence meanwhile, the voice kept queued
            if (!modem_beep_fifo_full()) {
                memset(block, 0, sizeof(block));
                modem_beep_write(block);
            }
            if ((xTaskGetTickCount() - play_since) >= pdMS_TO_TICKS(AMP_START_MS)) {
                play_state = 2;
            }
            continue;
        }
        // playing: a block a tick while the FIFO has room (as sound.c: several at once overran it, its full flag
        // comes late, and samples were lost: the voice shook); out of voice: silence while the call goes on, else the end
        for (int blocks = 0; running && (blocks < (int)nxdn_feed_blocks) && !modem_beep_fifo_full(); blocks++) {
            if (pcm_in == pcm_out) {
                if (!play_wanted) {
                    break;
                }
                nxdn_radio_stats.underruns++;
                memset(block, 0, sizeof(block));
                modem_beep_write(block);
                continue;
            }
            const int16_t *frame = pcm[pcm_out % PCM_FRAMES];
            for (int i = 0; i < (MODEM_BEEP_BLOCK / 2); i++) {
                int16_t s = frame[pcm_pos + (uint32_t)i];
                block[2 * i] = (uint8_t)s;
                block[2 * i + 1] = (uint8_t)((uint16_t)s >> 8);
            }
            modem_beep_write(block);
            if (nxdn_tap_source == 2) {
                tap_put(&frame[pcm_pos], MODEM_BEEP_BLOCK / 2);
            }
            nxdn_radio_stats.feed_writes++;
            pcm_pos += MODEM_BEEP_BLOCK / 2;
            if (pcm_pos >= 160) {
                pcm_pos = 0;
                pcm_out++;
            }
        }
        if (!running || (!play_wanted && (pcm_in == pcm_out))) {
            play_on(false);
            pcm_pos = 0;
            if (!running) {
                pcm_out = pcm_in;
            }
            play_state = 0;
        }
    }
}

/* ---- the receive task ---- */

static void task_main(void *arg)
{
    int16_t half[256];
    TickType_t last_half = 0;

    (void)arg;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(POLL_MS));
        busy = true;
        if (!running) {
            last_half = 0;
            busy = false;
            continue;
        }
        while (running && nxdn_fm_read(half)) {
            uint32_t t0 = systime_get_us();
            TickType_t now = xTaskGetTickCount();
            if (last_half && ((now - last_half) > pdMS_TO_TICKS(48))) { // a half or more went by unread
                nxdn_radio_stats.missed_halves += (now - last_half) / pdMS_TO_TICKS(32) - 1;
            }
            last_half = now;
            nxdn_radio_stats.halves++;
            if (nxdn_tap_source == 0) {
                tap_put(half, 256);
            }
            nxdn_rx_samples(&rx, half, 256);
            nxdn_radio_stats.hunts = rx.hunts;
            nxdn_radio_stats.lost_sync = rx.lost_sync;
            uint32_t took = systime_get_us() - t0;
            nxdn_radio_stats.demod_us_sum += took;
            if (took > nxdn_radio_stats.busy_max_us) {
                nxdn_radio_stats.busy_max_us = took;
            }
        }
        if (nxdn_play_frames && ((int32_t)(xTaskGetTickCount() - play_next) >= 0)) { // the flash test
            if (!call.active) {
                call_begin();
                play_next = xTaskGetTickCount();
            }
            for (int k = 0; k < 4; k++) {
                uint8_t ambe[9];
                if (play_index >= nxdn_play_frames) {
                    play_index = 0;
                }
                flash_read(nxdn_play_address + (9 * play_index++), ambe, 9);
                voice(ambe);
            }
            last_voice = xTaskGetTickCount();
            play_next += pdMS_TO_TICKS(80);
        }
        if (call.active && ((xTaskGetTickCount() - last_voice) >= pdMS_TO_TICKS(CALL_TIMEOUT))) {
            call_end();
        }
        busy = false;
    }
}

void nxdn_radio_start(void)
{
    if (running) {
        return;
    }
    if (!task) {
        task = xTaskCreateStatic(task_main, "nxdn", sizeof(task_stack) / sizeof(task_stack[0]), NULL,
                                 tskIDLE_PRIORITY + 3, task_stack, &task_tcb);
        feeder = xTaskCreateStatic(feed_task, "nxdna", sizeof(feed_stack) / sizeof(feed_stack[0]), NULL,
                                   tskIDLE_PRIORITY + 4, feed_stack, &feed_tcb);
    }
    // the modem to FM recording first: the DMR engine stands aside from then on, then our state into the overlay
    if (!nxdn_fm_start()) {
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(5));
    overlay_use(OVERLAY_AMBE);
    nxdn_rx_init(&rx, on_frame, NULL);
    memset(&super, 0, sizeof(super));
    memset(&call, 0, sizeof(call));
    memset(&published, 0, sizeof(published));
    pcm_in = pcm_out = 0;
    pcm_pos = 0;
    play_wanted = false;
    heard = false;
    running = true;
}

void nxdn_radio_stop(void)
{
    if (!running) {
        return;
    }
    running = false;
    while (busy || (play_state != 0)) { // the tasks done with the overlay and the prompt path
        vTaskDelay(1);
    }
    nxdn_fm_stop();
    call.active = false;
    call_publish();
}

bool nxdn_radio_call(nxdn_call_t *out)
{
    *out = call;
    return call.active;
}

bool nxdn_radio_heard_within(uint32_t ms)
{
    return heard && ((xTaskGetTickCount() - heard_at) < pdMS_TO_TICKS(ms));
}
