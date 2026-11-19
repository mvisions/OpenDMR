    .section .rodata.timezone_data,"a",@progbits
    .balign 4
    .global timezone_data_start
    .global timezone_data_end
timezone_data_start:
    .incbin "services/timezone-data/tzdb.bin"
timezone_data_end:
