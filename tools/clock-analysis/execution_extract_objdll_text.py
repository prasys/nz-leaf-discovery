#!/usr/bin/env python3 -I
"""execution-: carve OBJDLL.dll .text out of the reviewed G214 unpacked ROM.

Read-only. Writes a flat ARM binary plus a symbol map into
$NISSAN_ROOT/work/nz-clock/override-investigation/ so llvm-objdump can
disassemble it offline. Never executes extracted code.
Mapping (confirmed in tools/nz-clock/build.py layout()): the o32 .text section
has physical bytes at ROM offset 0x827000, psize 0x9e000, runtime VA
0x40e01000. Runtime VA -> ROM offset: VA - 0x40e01000 + 0x827000.
"""
import os
import struct
import sys
from pathlib import Path

RAW_OFFSET = 0x827000
PSIZE = 0x9E000
BASE_VA = 0x40E01000
SOURCE_SHA = "8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a"

ROOT = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
OUT = ROOT / "work/nz-clock/override-investigation"


def main():
    source = ROOT / "work/ce-extract/G214JLNI.066.nb0"
    data = source.read_bytes()
    import hashlib
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        sys.exit("Source ROM SHA256 mismatch")
    text = data[RAW_OFFSET:RAW_OFFSET + PSIZE]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "execution-objdll-text.bin").write_bytes(text)
    # Entry offsets of interest from findings 07/08 (VA -> file offset)
    entries = {
        "OBJ_Time_getTotalOffset": 0x40E2C360,
        "OBJ_Time_getLocalTime": 0x40E2C3B8,
        "default_initializer_FUN_40e2c4d4": 0x40E2C4D4,
        "OBJ_Time_initialize": 0x40E2D3D4,
        "event_evaluator_FUN_40e2c068": 0x40E2C068,
        "OBJ_Time_readLocalTime": 0x40E2CAE0,
        "OBJ_Time_writeGMT": 0x40E2C8C4,
        "OBJ_Time_writeZone": 0x40E2CB60,
        "OBJ_Time_writeZoneType": 0x40E2CC38,
        "OBJ_Time_writeDst": 0x40E2CD30,
        "OBJ_Time_writeOffset": 0x40E2CDF0,
    }
    lines = ["# execution- OBJDLL.dll G214JLNI.066 VA map (.text base 0x40e01000)",
             "# format: symbol text_blob_offset runtime_va"]
    for name, va in sorted(entries.items(), key=lambda kv: kv[1]):
        off = va - BASE_VA
        if not 0 <= off < PSIZE:
            sys.exit(f"{name} VA {va:#x} outside .text")
        lines.append(f"{name} {off:#x} {va:#x}")
    (OUT / "execution-objdll-text.map.txt").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(text)} bytes -> {OUT/'execution-objdll-text.bin'}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
