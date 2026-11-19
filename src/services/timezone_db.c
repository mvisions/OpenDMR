/* OpenDMR automatic timezone lookup. Database format: timezone-data/README.md. */
#include <stddef.h>
#include <string.h>
#include "timezone_db.h"

#define GRID_SCALE 8
#define ROWS_PER_BLOCK 16
#define GRID_ROWS (180 * GRID_SCALE)
#define GRID_COLS (360 * GRID_SCALE)
#define BLOCK_COUNT (GRID_ROWS / ROWS_PER_BLOCK)
#define MAX_RUNS 69
#define MAX_BITS 12
#define ALPHABET 128
#define STREAM_COUNT 4
#define HEADER_SIZE 28
#define RULE_HEADER_SIZE 18
#define ZONE_MASK 511u

typedef struct {
    uint8_t symbols[ALPHABET];
    uint8_t count[MAX_BITS + 1];
} codebook_t;

typedef struct {
    const codebook_t *book;
    const uint8_t *bits;
    const uint8_t *bits_end;
    const uint8_t *extra;
    const uint8_t *extra_end;
    uint8_t mask;
} stream_t;

typedef struct {
    uint16_t end;
    uint16_t zone;
} span_t;

static codebook_t books[STREAM_COUNT];
static const uint8_t *ranks;
static const uint8_t *block_index;
static const uint8_t *blocks;
static const uint8_t *rules;
static const uint8_t *rules_end;
static uint16_t rank_count;
static volatile uint32_t cached_zone; // (cell + 1) in the upper bits, zone in the lower nine bits

static uint16_t le16(const uint8_t *p)
{
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t le32(const uint8_t *p)
{
    return le16(p) | ((uint32_t)le16(p + 2) << 16);
}

static uint32_t crc32(const uint8_t *data, uint32_t size)
{
    uint32_t crc = UINT32_MAX;

    while (size--) {
        crc ^= *data++;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1u) ? 0xEDB88320u : 0);
        }
    }
    return ~crc;
}

void timezone_db_init(const uint8_t *data, uint32_t size)
{
    rules = NULL;
    cached_zone = 0;
    if ((size < HEADER_SIZE) || (memcmp(data, "TZDB", 4) != 0) || (le16(data + 4) != 1) ||
        (data[6] != GRID_SCALE) || (data[7] != ROWS_PER_BLOCK) ||
        (crc32(data + HEADER_SIZE, size - HEADER_SIZE) != le32(data + 24))) {
        return;
    }

    uint32_t boundary_size = le32(data + 16);
    uint32_t rule_size = le32(data + 20);
    if ((boundary_size > size - HEADER_SIZE) || (rule_size != size - HEADER_SIZE - boundary_size) ||
        (rule_size < RULE_HEADER_SIZE)) {
        return;
    }

    rank_count = le16(data + 14);
    uint32_t index_end = STREAM_COUNT * ALPHABET + 2u * rank_count + 2u * (BLOCK_COUNT + 1u);
    if ((rank_count == 0) || (rank_count > ZONE_MASK) || (index_end > boundary_size)) {
        return;
    }

    const uint8_t *boundary = data + HEADER_SIZE;
    ranks = boundary + STREAM_COUNT * ALPHABET;
    block_index = ranks + 2u * rank_count;
    blocks = boundary + index_end;
    if ((le16(block_index) != 0) || (le16(block_index + 2 * BLOCK_COUNT) != boundary_size - index_end)) {
        return;
    }
    for (int i = 0; i < BLOCK_COUNT; ++i) {
        if (le16(block_index + 2 * i) >= le16(block_index + 2 * (i + 1))) {
            return;
        }
    }

    for (int i = 0; i < STREAM_COUNT; ++i) {
        const uint8_t *lengths = boundary + i * ALPHABET;
        codebook_t *book = &books[i];
        int next = 0;
        memset(book->count, 0, sizeof(book->count));
        for (int bits = 1; bits <= MAX_BITS; ++bits) {
            for (int symbol = 0; symbol < ALPHABET; ++symbol) {
                if (lengths[symbol] == bits) {
                    book->symbols[next++] = (uint8_t)symbol;
                    ++book->count[bits];
                }
            }
        }
    }

    const uint8_t *candidate = boundary + boundary_size;
    if (memcmp(candidate, "TZR2", 4) == 0) {
        rules = candidate;
        rules_end = candidate + rule_size;
    }
}

static int read_varint(const uint8_t **cursor, const uint8_t *end)
{
    unsigned value = 0;
    for (int shift = 0; (shift <= 21) && (*cursor < end); shift += 7) {
        uint8_t byte = *(*cursor)++;
        value |= (unsigned)(byte & 127) << shift;
        if (!(byte & 128)) {
            return (int)value;
        }
    }
    return -1;
}

static int read_symbol(stream_t *stream)
{
    int code = 0;
    int first = 0;
    for (int bits = 1; bits <= MAX_BITS; ++bits) {
        if (stream->bits == stream->bits_end) {
            break;
        }
        code = 2 * code + ((*stream->bits & stream->mask) != 0);
        stream->mask >>= 1;
        if (!stream->mask) {
            stream->mask = 128;
            ++stream->bits;
        }
        int choices = stream->book->count[bits];
        if ((code >= 0) && (code < choices)) {
            int value = stream->book->symbols[first + code];
            if (value == 127) {
                int extra = read_varint(&stream->extra, stream->extra_end);
                return extra < 0 ? -1 : 127 + extra;
            }
            return value;
        }
        first += choices;
        code -= choices;
    }
    return -1;
}

static uint16_t boundary_zone(int row, int col)
{
    int block = row / ROWS_PER_BLOCK;
    const uint8_t *cursor = blocks + le16(block_index + 2 * block);
    const uint8_t *end = blocks + le16(block_index + 2 * (block + 1));
    stream_t streams[STREAM_COUNT];
    span_t spans[2][MAX_RUNS];
    span_t *previous = spans[0];
    span_t *current = spans[1];
    int previous_count = 0;

    for (int i = 0; i < STREAM_COUNT; ++i) {
        if (end - cursor < 4) {
            return 0;
        }
        uint16_t bit_size = le16(cursor);
        uint16_t extra_size = le16(cursor + 2);
        cursor += 4;
        if (end - cursor < (int)bit_size + extra_size) {
            return 0;
        }
        streams[i] = (stream_t){
            .book = &books[i], .bits = cursor, .bits_end = cursor + bit_size,
            .extra = cursor + bit_size, .extra_end = cursor + bit_size + extra_size, .mask = 128,
        };
        cursor += bit_size + extra_size;
    }

    for (int i = 0; i <= row % ROWS_PER_BLOCK; ++i) {
        int op = read_symbol(&streams[0]);
        if (!op && previous_count) {
            continue;
        }
        int stop = 0;
        int count = 0;
        while (stop < GRID_COLS) {
            int runs = op >> 1;
            bool copy = (op & 1) != 0;
            int origin = copy ? read_symbol(&streams[1]) : 0;
            if ((runs <= 0) || (runs > MAX_RUNS - count) ||
                (copy && ((origin < 0) || (origin > previous_count - runs)))) {
                return 0;
            }
            for (int j = 0; j < runs; ++j) {
                int delta = read_symbol(&streams[2]);
                if (delta < 0) {
                    return 0;
                }
                int next;
                uint16_t zone;
                if (copy) {
                    span_t span = previous[origin + j];
                    next = span.end + ((delta & 1) ? -(delta / 2) - 1 : delta / 2);
                    zone = span.zone;
                } else {
                    int rank = read_symbol(&streams[3]);
                    if ((rank < 0) || (rank >= rank_count)) {
                        return 0;
                    }
                    next = stop + delta;
                    zone = le16(ranks + 2 * rank);
                }
                if ((next <= stop) || (next > GRID_COLS)) {
                    return 0;
                }
                stop = next;
                current[count++] = (span_t){(uint16_t)stop, zone};
            }
            if (stop < GRID_COLS) {
                op = read_symbol(&streams[0]);
            }
        }
        span_t *swap = previous;
        previous = current;
        current = swap;
        previous_count = count;
    }
    for (int i = 0; i < previous_count; ++i) {
        if (col < previous[i].end) {
            return previous[i].zone;
        }
    }
    return 0;
}

static bool rule_offset(uint16_t zone, uint32_t utc, int32_t *seconds)
{
    uint16_t zones = le16(rules + 12);
    uint16_t count = le16(rules + 14);
    uint16_t pool_size = le16(rules + 16);
    if ((zone == 0) || (zone > zones) ||
        (rules_end - rules <= RULE_HEADER_SIZE + zones + 2 * count + pool_size)) {
        return false;
    }
    const uint8_t *index = rules + RULE_HEADER_SIZE + zones;
    const uint8_t *pool = index + 2 * count;
    const uint8_t *schedules = pool + pool_size;
    uint8_t rule_id = rules[RULE_HEADER_SIZE + zone - 1];
    if (rule_id >= count) {
        return false;
    }
    uint16_t at = le16(index + 2 * rule_id);
    if (at + 3 > pool_size) {
        return false;
    }
    const uint8_t *rule = pool + at;
    uint16_t schedule_at = le16(rule);
    if (schedule_at >= rules_end - schedules) {
        return false;
    }
    const uint8_t *schedule = schedules + schedule_at;
    uint8_t steps = *schedule++;
    if ((int)steps > pool_size - at - 3) {
        return false;
    }
    uint32_t minute = (utc - le32(rules + 4)) / 60;
    uint32_t transition = 0;
    unsigned step = 0;
    for (; step < steps; ++step) {
        int delta = read_varint(&schedule, rules_end);
        if (delta <= 0) {
            return false;
        }
        transition += (uint32_t)delta;
        if (transition > minute) {
            break;
        }
    }
    *seconds = (int32_t)(int8_t)rule[2 + step] * 900;
    return true;
}

bool timezone_db_offset(uint32_t utc, int32_t latitude_e5, int32_t longitude_e5, int32_t *seconds)
{
    if (!rules || (utc < le32(rules + 4)) || (utc >= le32(rules + 8)) ||
        (latitude_e5 < -9000000) || (latitude_e5 > 9000000) ||
        (longitude_e5 < -18000000) || (longitude_e5 > 18000000)) {
        return false;
    }
    int row = (latitude_e5 + 9000000) / 12500;
    int col = (longitude_e5 + 18000000) / 12500;
    row = (row == GRID_ROWS) ? GRID_ROWS - 1 : row;
    col = (col == GRID_COLS) ? 0 : col;
    uint32_t key = (uint32_t)(row * GRID_COLS + col + 1) << 9;
    uint32_t cached = cached_zone;
    uint16_t zone;
    if ((cached & ~ZONE_MASK) == key) {
        zone = cached & ZONE_MASK;
    } else {
        zone = boundary_zone(row, col);
        cached_zone = key | zone;
    }
    return rule_offset(zone, utc, seconds);
}
