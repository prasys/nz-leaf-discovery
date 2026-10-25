/* G214JLNI.066 / OBJDLL.dll only. A relocated .text copy owns the new cave. */
ENTRY(nz_entry)
original_resume = 0x40e2c368;
SECTIONS {
    . = 0x40e9e1c4;
    .text : { KEEP(*(.text.entry)) *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
}
ASSERT(SIZEOF(.data) == 0, "Payload must not require initialized writable data")
ASSERT(SIZEOF(.bss) == 0, "Payload must not require zeroed writable data")
ASSERT(SIZEOF(.text) <= 0xe3c, "Payload exceeds relocated section capacity")
