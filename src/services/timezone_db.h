#ifndef DM32_TIMEZONE_DB_H
#define DM32_TIMEZONE_DB_H

#include <stdbool.h>
#include <stdint.h>

void timezone_db_init(const uint8_t *data, uint32_t size);
bool timezone_db_offset(uint32_t utc, int32_t latitude_e5, int32_t longitude_e5, int32_t *seconds);

#endif
