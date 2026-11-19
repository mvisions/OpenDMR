# Automatic timezone database

[tzdb.bin](tzdb.bin) is the machine-readable database embedded in OpenDMR.
The boundary portion derives from [Timezone Boundary Builder 2026f, same since
1970](https://github.com/evansiroky/timezone-boundary-builder/releases/tag/2026f),
which uses data from [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
The boundary data and its derivatives are available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The separately encoded UTC offset rules come from
[IANA tzdb 2026f](https://www.iana.org/time-zones) and are
[public-domain data](https://data.iana.org/time-zones/tzdb/LICENSE).
Firmware releases that embed this database should include this notice and offer
the database as a separate machine-readable download under these data terms.

The grid samples polygon membership at each 0.125-degree cell center.
Asia/Urumqi uses Asia/Shanghai to represent the official UTC+8 in mainland
China. Cells outside the sampled polygons have no zone. Coordinates near
borders and coasts may resolve to a neighboring cell's zone.

## Binary format

Multibyte integers use little endian. The 28-byte header has the magic TZDB,
a u16 format version, u8 cells per degree and rows per block, a six-byte
NUL-terminated tzdb version, a u16 rank count, u32 boundary and rule lengths,
and a u32 CRC32 over both concatenated payloads.

The boundary payload starts with four 128-byte canonical Huffman code-length
tables for operations, previous-row indices, deltas and zone ranks, in that
order. Symbols with the same code length are ordered numerically. This is
followed by a u16 zone ID per rank and a u16 offset per block plus an end
offset, relative to the first block. Blocks advance south to north, with
16 rows in each. Within a row, spans advance west to east.

Each block contains four consecutive streams. Each stream starts with
u16 bitstream and escape-stream byte lengths, then those two byte strings.
Huffman codes are read most-significant bit first. Symbol 127 means 127 plus
the next unsigned LEB128 escape value. A row ends at column 2880. Operation
zero repeats the preceding row. Other operations give a span count in their
upper bits. If the low bit is set, copy the corresponding spans from the
preceding row starting at the next decoded index, adding a zigzag delta to
each old end column. Otherwise read an unsigned delta from the current
end column and a zone rank for each new span. Zone zero is unknown.

The rule payload begins with TZR2, u32 start and exclusive end UTC timestamps,
u16 zone and rule counts, and a u16 rule-pool size. It then stores a u8 rule
ID per zone (zone IDs start at one) and a u16 pool offset per rule. Each rule
stores a u16 schedule offset and signed UTC offsets in 15-minute units,
starting with the offset in effect at the start timestamp. The schedule pool
follows the rule pool. A schedule starts with a u8 transition count followed
by unsigned LEB128 deltas in minutes from the previous transition, starting
at the database epoch. This release covers 2026 through 2040 inclusive.
