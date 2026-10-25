#!/usr/bin/env python3 -I
"""execution-: compare OBJDLL.dll e32/o32 metadata between the stock G214 ROM
and the offline v2 candidate ROM. Read-only."""
import os
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "ce-extract"))
import ceromx

root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
STOCK = root / "work/ce-extract/G214JLNI.066.nb0"
CAND = root / "work/nz-clock/candidate-v2/G214-NZ-candidate.nb0"


def info(data, label):
    rom = ceromx.Rom(data)
    matches = [m for m in rom.modules if rom.cstr(m[4]).lower() == "objdll.dll"]
    assert len(matches) == 1, label
    module = matches[0]
    e32off = rom.off(module[5])
    e32 = struct.unpack_from(ceromx.E32_FMT, data, e32off)
    o32off = rom.off(module[6])
    n = e32[0]
    lines = [f"== {label}: e32@{e32off:#x} objcnt={n} entry={e32[3]:#x} dbsize..."]
    lines.append(f"e32 fields: " + " ".join(f"{v:#x}" for v in e32))
    for i in range(n):
        o32 = struct.unpack_from(ceromx.O32_FMT, data, o32off + 24 * i)
        lines.append(f"o32[{i}] vsize={o32[0]:#x} rva={o32[1]:#x} psize={o32[2]:#x} "
                     f"dataptr={o32[3]:#x} realaddr={o32[4]:#x} flags={o32[5]:#x}")
    lines.append(f"physlast={rom.hdr['physlast']:#x} romhdr@{rom.romhdr_off:#x}")
    return lines


def main():
    stock = info(STOCK.read_bytes(), "stock")
    cand = info(CAND.read_bytes(), "candidate-v2")
    out = root / "work/nz-clock/override-investigation/execution-e32-o32-compare.txt"
    text = "\n".join(stock + [""] + cand) + "\n"
    out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
