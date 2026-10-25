#!/usr/bin/env python3 -I
"""execution-: byte-diff the first 512-byte slot header of the stock G214 slot
against the packed v2 and fixed-probe candidates, and against what the
AppLaunch loader compares (FUN_ef48eb00: full 512-byte header memcmp).
Read-only; card image opened 'rb' at LBA 157696 only."""
import os
import sys
from pathlib import Path

root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
IMG = Path(os.environ.get("NISSAN_IMG", root / "sdcard/nissan-sd-485-1972-00.img"))
SLOT_LBA = 157696


def main():
    with IMG.open("rb") as s:
        s.seek(SLOT_LBA * 512)
        stock = s.read(512)
    report = []
    for name in ("packed-v2-reviewed", "probe-fixed-nzdt-v1-packed"):
        path = root / "work/nz-clock" / name / "G214-NZ-EXPERIMENTAL-slot.bin"
        if not path.is_file():
            report.append(f"{name}: MISSING {path}")
            continue
        cand = path.read_bytes()[:512]
        diffs = [(i, stock[i], cand[i]) for i in range(512) if stock[i] != cand[i]]
        ranges = []
        for i, a, b in diffs:
            if ranges and i == ranges[-1][1]:
                ranges[-1][1] = i + 1
            else:
                ranges.append([i, i + 1])
        report.append(f"{name}: {len(diffs)} changed header bytes; ranges " +
                      ", ".join(f"{a:#x}-{b-1:#x}" for a, b in ranges))
        report.append(f"  stock  +0x00..+0x0b: {stock[:12].hex()}")
        report.append(f"  cand   +0x00..+0x0b: {cand[:12].hex()}")
        report.append(f"  stock  +0x30..+0x3b: {stock[0x30:0x3c].hex()}")
        report.append(f"  cand   +0x30..+0x3b: {cand[0x30:0x3c].hex()}")
        report.append(f"  stock  +0x14..+0x15: {stock[0x14:0x16].hex()}  +0x78..+0x7b: {stock[0x78:0x7c].hex()}")
        report.append(f"  cand   +0x14..+0x15: {cand[0x14:0x16].hex()}  +0x78..+0x7b: {cand[0x78:0x7c].hex()}")
    out = root / "work/nz-clock/override-investigation/execution-header-diff.txt"
    text = "\n".join(report) + "\n"
    out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
