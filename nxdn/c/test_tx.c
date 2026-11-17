// nxdn_core.c's transmit side on the PC: a call from AMBE+2 frames (9 bytes each, a file) as dibits (one a byte) to
// stdout, for nxdn/c/check_tx.py to compare with nxdn/py/tx.py.
//   test_tx <frames.bit> <src> <dst> <ran> > out.dibits
#include <stdio.h>
#include <stdlib.h>

#include "nxdn_core.h"

int main(int argc, char **argv)
{
    if (argc < 5) {
        fprintf(stderr, "test_tx frames.bit src dst ran\n");
        return 1;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) {
        return 1;
    }
    static uint8_t d[1 << 20];
    int n = (int)fread(d, 1, sizeof(d), f) / 9;
    fclose(f);
    nxdn_tx t;
    static uint8_t out[NXDN_PREAMBLE_SYMS + NXDN_FRAME_SYMS];
    int k = nxdn_tx_begin(&t, (uint16_t)atoi(argv[2]), (uint16_t)atoi(argv[3]), (uint8_t)atoi(argv[4]), NXDN_CALL_GROUP, out);
    fwrite(out, 1, k, stdout);
    for (int i = 0; i < n; i += 4) {
        uint8_t a[4][9];
        for (int j = 0; j < 4; j++) {
            int src = (i + j < n) ? (i + j) : (n - 1); // the last repeated up to 4, as tx.py
            for (int b = 0; b < 9; b++) {
                a[j][b] = d[9 * src + b];
            }
        }
        k = nxdn_tx_voice(&t, (const uint8_t(*)[9])a, out);
        fwrite(out, 1, k, stdout);
    }
    k = nxdn_tx_end(&t, out);
    fwrite(out, 1, k, stdout);
    return 0;
}
