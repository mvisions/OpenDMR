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
 * OpenDMR, service: the display backlight. After OpenDM32 menuSystem.c displayLightTrigger(),
 * applicationMain.c (the light timer, the manual toggle) and display.c displayEnableBacklight().
 *
 * Auto: a key, the knob, a signal heard or a transmission light it, backlight_timeout seconds after dims it.
 * Squelch: the same, the time does not run while a signal is heard. Buttons: only the keys and the knob light it.
 * Manual: SK1 alone toggles it. Dim is display_backlight_percentage_off; a timeout of 0 keeps it lit. Only the input
 * task calls these, but the menu (display_apply_brightness()).
 *
 * Lit, it is the day brightness, or the night one when "Auto night" is on and the auto theme's night period applies.
 */

#include <math.h>
#include "FreeRTOS.h"
#include "task.h"
#include "backlight.h"
#include "settings.h"
#include "radio.h"
#include "display.h"
#include "datetime.h"
#include "extra_options.h"
#include "theme.h"
#include "gps.h"
#include "position.h"

#define DEFAULT_PERCENT 100
#define NIGHT_CHECK_MS  1000 // day or night looked at again while lit

#define AUTO_LIGHT_FROM 7  // local hours without a position
#define AUTO_LIGHT_TO   19
#define DAY_SECONDS     86400U
#define DEG_TO_RAD      0.017453292519943295

static volatile bool lit = true;
static volatile uint32_t light_left_ms; // 0: no timeout running
static uint32_t night_check_ms;

static struct {
    uint32_t minute;
    int32_t latitude;
    int32_t longitude;
    bool night;
} solar_cache;

// NOAA solar position approximation, evaluated at the current UTC minute.
static bool solar_night(uint32_t utc, int32_t latitude, int32_t longitude)
{
    datetime_fields_t date;
    datetime_to_fields(utc, &date);
    uint16_t year = date.year;
    uint32_t jan1 = datetime_from_fields(&(datetime_fields_t){.year = year, .month = 1, .day = 1});
    bool leap = (year % 4 == 0) && ((year % 100 != 0) || (year % 400 == 0));
    double gamma = (360.0 * DEG_TO_RAD / (leap ? 366 : 365)) * ((utc - jan1) / 86400.0 - 0.5);
    double c1 = cos(gamma);
    double s1 = sin(gamma);
    double c2 = cos(2.0 * gamma);
    double s2 = sin(2.0 * gamma);
    double equation = 229.18 * (0.000075 + 0.001868 * c1 - 0.032077 * s1 - 0.014615 * c2 - 0.040849 * s2);
    double declination = 0.006918 - 0.399912 * c1 + 0.070257 * s1 - 0.006758 * c2 + 0.000907 * s2
                       - 0.002697 * cos(3.0 * gamma) + 0.001480 * sin(3.0 * gamma);
    double lat = latitude * 1E-5 * DEG_TO_RAD;
    double solar_minutes = (utc % DAY_SECONDS) / 60.0 + equation + 4.0 * longitude * 1E-5;
    double hour_angle = (solar_minutes / 4.0 - 180.0) * DEG_TO_RAD;
    double cos_zenith = sin(lat) * sin(declination) + cos(lat) * cos(declination) * cos(hour_angle);

    return cos_zenith < -0.014538; // cos(90.833 degrees), the standard sunrise and sunset threshold
}

static bool valid_coordinates(int32_t latitude, int32_t longitude)
{
    return (latitude >= -9000000) && (latitude <= 9000000) &&
           (longitude >= -18000000) && (longitude <= 18000000);
}

static bool is_night(bool no_clock)
{
    uint32_t utc = datetime_now();
    int32_t latitude;
    int32_t longitude;

    if (utc < DATETIME_VALID_MIN) {
        return no_clock;
    }
    if (gps_position(&latitude, &longitude) && valid_coordinates(latitude * 10, longitude * 10)) {
        // Hundredths of a degree suffice for sunrise and sunset and keep GPS jitter out of the cache key.
        latitude = (latitude / 100) * 1000;
        longitude = (longitude / 100) * 1000;
    } else if (!position_own(&latitude, &longitude) || !valid_coordinates(latitude, longitude)) {
        int32_t offset = ((int32_t)(settings.timezone & 0x7F) - 64) * 900;
        int hour = (int)(((utc % DAY_SECONDS + DAY_SECONDS + offset) % DAY_SECONDS) / 3600);

        return (hour < AUTO_LIGHT_FROM) || (hour >= AUTO_LIGHT_TO);
    }

    uint32_t minute = utc / 60;
    taskENTER_CRITICAL();
    bool cached = (solar_cache.minute == minute) && (solar_cache.latitude == latitude) &&
                  (solar_cache.longitude == longitude);
    bool night = solar_cache.night;
    taskEXIT_CRITICAL();
    if (!cached) {
        night = solar_night(minute * 60, latitude, longitude);
        taskENTER_CRITICAL();
        solar_cache.minute = minute;
        solar_cache.latitude = latitude;
        solar_cache.longitude = longitude;
        solar_cache.night = night;
        taskEXIT_CRITICAL();
    }
    return night;
}

static int lit_percent(void)
{
    bool night = ((settings.bitfield_options & SETTINGS_BIT_AUTO_NIGHT) != 0) && is_night(false);
    int percent = settings.display_backlight_percentage[night ? 1 : 0];

    if (!settings_valid() || (percent < 1) || (percent > 100)) {
        percent = DEFAULT_PERCENT;
    }
    return percent;
}

static void light(bool on)
{
    lit = on;
    backlight_set_percent(on ? lit_percent() : settings.display_backlight_percentage_off);
}

// displayLightTrigger(): lit, the timeout from now
static void trigger(bool from_key)
{
    uint8_t mode = settings.backlight_mode;

    if ((mode == SETTINGS_BACKLIGHT_AUTO) || (mode == SETTINGS_BACKLIGHT_SQUELCH) ||
        ((mode == SETTINGS_BACKLIGHT_BUTTONS) && from_key)) {
        light_left_ms = settings.backlight_timeout * 1000UL;
        light(true);
    }
}

void display_apply_brightness(void)
{
    if (!settings_valid() || (settings.backlight_mode == SETTINGS_BACKLIGHT_MANUAL)) {
        light(true);
        return;
    }
    trigger(true);
}

void display_light_start(void)
{
    if (settings_valid() && (settings.backlight_mode != SETTINGS_BACKLIGHT_AUTO) &&
        (settings.display_backlight_percentage_off > 0)) {
        light(false);
    } else {
        display_apply_brightness();
    }
}

void display_light_key(bool sk1_alone)
{
    if (!settings_valid()) {
        return;
    }
    if (settings.backlight_mode == SETTINGS_BACKLIGHT_MANUAL) {
        if (sk1_alone) {
            light(!lit);
        }
        return;
    }
    trigger(true);
}

void display_light_tick(uint32_t elapsed_ms)
{
    uint8_t mode = settings.backlight_mode;
    bool heard;

    if (!settings_valid()) {
        return;
    }
    night_check_ms += elapsed_ms;
    if (lit && (night_check_ms >= NIGHT_CHECK_MS)) { // day to night or back while lit
        night_check_ms = 0;
        backlight_set_percent(lit_percent());
    }
    if (mode == SETTINGS_BACKLIGHT_MANUAL) {
        return;
    }
    heard = radio_audio_heard(); // FM or DMR audio
    if (((mode == SETTINGS_BACKLIGHT_AUTO) && heard) || radio_is_transmitting()) {
        trigger(true); // lit while it lasts, the timeout runs after
        return;
    }
    if ((mode == SETTINGS_BACKLIGHT_SQUELCH) && heard) {
        if (!lit) {
            trigger(false);
        }
        return; // the time stands still while heard
    }
    if (light_left_ms == 0) {
        return;
    }
    light_left_ms = (light_left_ms > elapsed_ms) ? (light_left_ms - elapsed_ms) : 0;
    if (light_left_ms == 0) {
        light(false);
    }
}

// The choice is kept as a theme id (theme.h) or THEME_ID_AUTO. None yet (0xFF), a theme no longer in the menu (hidden
// or deleted by the CPS) and 6 (auto before the user's themes, then the place after the 6 built-in ones): auto
uint8_t display_theme_choice(void)
{
    uint8_t choice = extra_options_theme();

    return ((choice == THEME_ID_AUTO) || (theme_index(choice) < 0)) ? THEME_ID_AUTO : choice;
}

void display_theme_choose(uint8_t choice)
{
    extra_options_set_theme(choice);
    display_theme_apply();
}

void display_theme_step(int direction)
{
    uint8_t count = theme_count();
    uint8_t choice = display_theme_choice();
    int at = (choice == THEME_ID_AUTO) ? count : theme_index(choice); // auto after the themes

    at = (at + count + 1 + ((direction > 0) ? 1 : -1)) % (count + 1);
    display_theme_choose((at == count) ? THEME_ID_AUTO : theme_id((uint8_t)at));
}

void display_theme_apply(void)
{
    uint8_t choice = display_theme_choice();
    uint8_t wanted = choice;

    if (choice == THEME_ID_AUTO) {
        wanted = theme_first(is_night(true));
    }
    if (wanted != theme_current()) {
        theme_set(wanted);
    }
}
