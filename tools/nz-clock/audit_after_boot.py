#!/usr/bin/env python3 -I
"""Read-only G214 audit after a car test; never writes or mounts anything.

Distinguishes the exact written v2 range, restored stock bytes, and other data.
This establishes card contents, not which code the head unit executed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backup_card

OFFSET = 157696 * 512
LENGTH = 30737920
ORIGINAL_SHA = "8c9edf0086e71f94cabcd23b360e73c91bd0d950b8b84e5ae4822dc0e3aa98e3"
PATCH_SHA = "b32441b1f42707348bfac2b273fcd983ff54488bf77e3886ac100bf25a07db70"
PROBE_SHA = "a232889da7e317b5a1c749008dcd72a02131e478379994c75b0216c9ce07078d"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_range(path):
    with path.open("rb", buffering=0) as stream:
        stream.seek(OFFSET)
        output = bytearray()
        while len(output) < LENGTH:
            block = stream.read(min(1024 * 1024, LENGTH - len(output)))
            if not block:
                raise OSError("Short G214 read")
            output.extend(block)
    return bytes(output)


def clock_stores(path):
    """Only fixed clock/header fields; never expose other nav-area contents.

    These are persisted snapshots at a likely OBJ_Time location, not live RAM.
    No claim is made that either snapshot is the currently selected copy.
    """
    stores = []
    with path.open("rb", buffering=0) as stream:
        for copy, lba in (("A", 807028), ("B", 807338)):
            stream.seek(lba * 512)
            # Raw macOS SD nodes require sector-aligned offsets/read lengths.
            # Read one sector but expose only header/clock fields below.
            sector = stream.read(512)
            header = sector[:16]
            clock = sector[0x144:0x168]
            if len(sector) != 512 or header[:4] != b"SRST":
                raise ValueError("Unexpected nav store header/short clock snapshot")
            year, month, day, hour, minute, second = struct.unpack_from("<HBBBBB", clock)
            zone, ztype, dst, user = struct.unpack_from("<iIii", clock, 0x14)
            stores.append({"copy": copy, "lba": lba, "clock_offset": lba * 512 + 0x144,
                           "generation": struct.unpack_from("<I", header, 8)[0],
                           "gmt_fields": [year, month, day, hour, minute, second],
                           "validity": struct.unpack_from("<I", clock, 8)[0],
                           "zone": zone, "zone_type": ztype, "dst": dst, "user_offset": user})
    return stores


def classify(observed, original, patch, probe=None):
    if (len(original) != LENGTH or sha(original) != ORIGINAL_SHA or
            len(patch) != 30708224 or sha(patch) != PATCH_SHA):
        raise ValueError("Reviewed original/patch hashes required")
    if len(observed) != LENGTH:
        raise ValueError("Incomplete observed range")
    expected = patch + original[len(patch):]
    if probe is not None and (len(probe) != 30700032 or sha(probe) != PROBE_SHA):
        raise ValueError("Reviewed fixed-probe hash required")
    if probe is not None and observed == probe + expected[len(probe):]:
        state = "FIXED_NZDT_PROBE_PRESERVED_EXACTLY_NO_AUTOMATIC_DST"
    elif observed == expected:
        state = "PATCH_V2_PRESERVED_EXACTLY"
    elif observed == original:
        state = "ORIGINAL_G214_PRESENT"
    else:
        state = "OTHER_G214_CONTENTS"
    return {"status": state, "offset": OFFSET, "lba": OFFSET // 512,
            "read_bytes": LENGTH, "observed_range_sha256": sha(observed),
            "patched_prefix_matches": observed[:len(patch)] == patch,
            "untouched_trailing_bytes_match": observed[len(patch):] == original[len(patch):],
            "limits": "Card contents only; active module and hook execution unproven"}


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
    work = root / "work/nz-clock"
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", help="whole physical card identifier, e.g. disk9")
    source.add_argument("--image", type=Path, help="read-only audit of a saved full-card image")
    parser.add_argument("--clock-store", action="store_true",
                        help="also inspect only the known persisted nav clock fields, not live RAM")
    parser.add_argument("--original", type=Path,
                        default=work / "writes/20261024T084550Z/G214-before-write.bin")
    parser.add_argument("--patch", type=Path,
                        default=work / "packed-v2-reviewed/G214-NZ-EXPERIMENTAL-slot.bin")
    parser.add_argument("--probe", type=Path,
                        default=work / "probe-fixed-nzdt-v1-packed/G214-NZ-EXPERIMENTAL-slot.bin",
                        help="also recognize the pinned fixed +13 probe when this file exists")
    args = parser.parse_args()
    try:
        original = args.original.expanduser().read_bytes()
        patch = args.patch.expanduser().read_bytes()
        probe_path = args.probe.expanduser()
        probe = probe_path.read_bytes() if probe_path.is_file() else None
        # Validate references before any device access.
        classify(original, original, patch, probe)
        identity = None
        if args.device:
            if not re.fullmatch(r"disk[0-9]+", args.device):
                raise ValueError("Expected a whole disk identifier")
            identity = backup_card.identify(args.device)
            path = Path("/dev/r" + args.device)
        else:
            path = args.image.expanduser().resolve()
            if not path.is_file() or path.stat().st_size != backup_card.SIZE:
                raise ValueError("Expected a saved full-card image of the known size")
        observed = read_range(path)
        if identity is not None and backup_card.identify(args.device) != identity:
            raise ValueError("Device identity changed during audit")
        if read_range(path) != observed:
            raise ValueError("G214 changed between reopened reads")
        stores = None
        if args.clock_store:
            stores = clock_stores(path)
            if clock_stores(path) != stores:
                raise ValueError("Clock snapshots changed between reopened reads")
        if identity is not None and backup_card.identify(args.device) != identity:
            raise ValueError("Device identity changed during second audit read")
        report = classify(observed, original, patch, probe)
        report.update(timestamp_utc=datetime.now(timezone.utc).isoformat(),
                      source=str(path), source_open_mode="rb", reopened_reads_equal=True)
        if identity is not None:
            report["device"] = identity
        if stores is not None:
            report["persisted_clock_snapshots"] = stores
            report["clock_snapshot_limits"] = "Likely OBJ_Time layout; active copy/live values unproven; area word sums not checked"
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Read-only audit refused/failed: {error}\n")


if __name__ == "__main__":
    main()
