#!/usr/bin/env python3 -I
"""Build a TEMPORARY fixed-UTC+13 diagnostic ROM; never opens a card.

Changes two stock instructions inside OBJ_Time_getTotalOffset. No new section,
branch, trampoline, C payload, or timezone/date applicability guard. Existing
zone validation, DST addition, user offset, errors and ABI remain in place.
This is a diagnostic for the failed automatic-DST v2 test, not a final DST fix.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build


def patch(source):
    layout = build.layout(source)  # Pins the entire stock ROM and function.
    entry = layout[5]
    # ldr r2,[r5,#0x14] -> movw r2,#0x6940
    # str r2,[r4]      -> movt r2,#0x0047
    # r2 = 0x476940 = 4,680,000 centiseconds = +13 hours.
    edits = [(entry + 0x28, bytes.fromhex("142095e5"), struct.pack("<I", 0xe3062940)),
             (entry + 0x30, bytes.fromhex("002084e5"), struct.pack("<I", 0xe3402047))]
    result = bytearray(source)
    for offset, old, new in edits:
        if source[offset:offset + 4] != old:
            raise ValueError("Stock probe instruction mismatch")
        result[offset:offset + 4] = new
    allowed = {i for offset, _, _ in edits for i in range(offset, offset + 4)}
    if len(result) != len(source) or any(a != b and i not in allowed
                                       for i, (a, b) in enumerate(zip(source, result))):
        raise ValueError("Unexpected diagnostic ROM changes")
    return bytes(result), {
        "status": "TEMPORARY_FIXED_UTC_PLUS_13_PROBE_NOT_AUTOMATIC_DST",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "candidate_sha256": hashlib.sha256(result).hexdigest(),
        "rom_bytes": len(result), "base_centiseconds": 4680000,
        "edits": [{"rom_offset": hex(offset), "runtime_va": hex(build.ENTRY_VA + offset - entry),
                   "before": old.hex(), "after": new.hex()} for offset, old, new in edits],
        "limits": ["Fixed +13 baseline for diagnostic use only; no automatic DST",
                   "Existing fixed DST and manual offsets are still added",
                   "All valid zones use the fixed baseline, not just Japan",
                   "No hardware execution has been verified"],
    }


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        out = args.out.expanduser().resolve()
        work = root / "work"
        if not out.is_relative_to(work) or out == work:
            raise ValueError("Output must be a new child of NISSAN_ROOT/work")
        data = (root / "work/ce-extract/G214JLNI.066.nb0").read_bytes()
        candidate, report = patch(data)
        out.mkdir(parents=True, exist_ok=False)
        (out / "G214-fixed-NZDT-PROBE.nb0").write_bytes(candidate)
        (out / "probe-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Diagnostic build refused/failed: {error}\n")


if __name__ == "__main__":
    main()
