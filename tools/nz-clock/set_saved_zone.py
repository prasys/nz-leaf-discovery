#!/usr/bin/env python3 -I
"""Prepare or apply a fixed +13 clock-zone edit to the backed-up owner's card.

Default is read-only preflight. --apply changes only four nav-store sectors,
after saving/verifying both complete current copies. GPS UTC stays unchanged.
This is a fixed-zone experiment, not automatic daylight saving.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backup_card

NAV_LBA = 807028
AREA_SIZE = 310 * 512
PAIR_SIZE = 2 * AREA_SIZE
CLOCK = 0x144
G214_OFFSET = 157696 * 512
G214_LENGTH = 30737920
G214_SHA = "18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876"
BACKUP_SHA = os.environ.get("NISSAN_BACKUP_SHA256", "")  # sha256 of your own verified backup_card.py image (card-specific, not committed); empty refuses
SECTORS = (0, 309, 310, 619)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sum32(data):
    if len(data) % 4:
        raise ValueError("Word sum requires aligned data")
    return sum(v[0] for v in struct.iter_unpack("<I", data)) & 0xffffffff


def read_exact(stream, length):
    output = bytearray()
    while len(output) < length:
        block = stream.read(min(length - len(output), 1024 * 1024))
        if not block:
            raise OSError("Short read")
        output.extend(block)
    return bytes(output)


def read_at(path, offset, length):
    with path.open("rb", buffering=0) as stream:
        stream.seek(offset)
        return read_exact(stream, length)


def inspect(area, copy):
    if (len(area) != AREA_SIZE or area[:4] != b"SRST" or area[-4:] != b"SRED" or
            struct.unpack_from("<I", area, 4)[0] != 0x6000000c or
            struct.unpack_from("<I", area, 12)[0] != copy or area[-12:-4] != bytes(8)):
        raise ValueError("Unexpected nav copy layout")
    stored = struct.unpack_from("<I", area, AREA_SIZE - 16)[0]
    if stored != sum32(area[:-16]):
        raise ValueError("Nav copy word-sum mismatch")
    if struct.unpack_from("<I", area, CLOCK - 4)[0] != 0:
        raise ValueError("Unexpected persisted clock prefix")
    generation = struct.unpack_from("<I", area, 8)[0]
    if not 0 < generation < 0xfffffffd:
        raise ValueError("Unsupported generation/wrap case")
    y, mo, day, hour, minute, second = struct.unpack_from("<HBBBBB", area, CLOCK)
    datetime(y, mo, day, hour, minute, second)
    if not 2008 <= y <= 2099 or struct.unpack_from("<I", area, CLOCK + 8)[0] != 1:
        raise ValueError("Unexpected saved UTC validity/date")
    zone, kind, dst, user = struct.unpack_from("<iIii", area, CLOCK + 0x14)
    if (zone, kind, dst, user) not in ((3240000, 61, 0, 0), (4680000, 0, 0, 0)):
        raise ValueError("Saved clock is not the reviewed Japan/default or fixed +13 state")
    return {"copy": copy, "generation": generation, "zone": zone,
            "zone_type": kind, "dst": dst, "user_offset": user, "word_sum": stored}


def patch_pair(original):
    if len(original) != PAIR_SIZE:
        raise ValueError("Expected both complete nav copies")
    before = [inspect(original[i * AREA_SIZE:(i + 1) * AREA_SIZE], i + 1) for i in range(2)]
    zones = {r["zone"] for r in before}
    if len(zones) != 1:
        raise ValueError("Mixed saved clock states require inspection")
    if zones == {4680000}:
        return original, {"status": "ALREADY_FIXED_PLUS_13", "before": before, "after": before}
    newest = max(r["generation"] for r in before)
    if newest >= 0xfffffffb:
        raise ValueError("Generation rollover is not supported")
    candidate = bytearray(original)
    allowed = set()
    for i in range(2):
        start = i * AREA_SIZE
        struct.pack_into("<I", candidate, start + 8, newest + i + 1)
        struct.pack_into("<iI", candidate, start + CLOCK + 0x14, 4680000, 0)
        check_at = start + AREA_SIZE - 16
        struct.pack_into("<I", candidate, check_at, sum32(candidate[start:check_at]))
        for at, length in ((start + 8, 4), (start + CLOCK + 0x14, 8), (check_at, 4)):
            allowed.update(range(at, at + length))
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(original, candidate))):
        raise ValueError("Unexpected change outside zone/type, generation or integrity word")
    after = [inspect(candidate[i * AREA_SIZE:(i + 1) * AREA_SIZE], i + 1) for i in range(2)]
    return bytes(candidate), {"status": "FIXED_PLUS_13_CANDIDATE", "before": before, "after": after}


def write_sector(stream, offset, data):
    if offset % 512 or len(data) != 512:
        raise ValueError("Expected exactly one aligned sector")
    stream.seek(offset)
    if stream.write(data) != 512:
        raise OSError("Short sector write")


def apply_pair(source, original, candidate, identity, identify, out, offset=NAV_LBA * 512,
               identify_read=None):
    # Rebuild independently from the actual baseline before any output/write.
    checked, plan = patch_pair(original)
    if checked != candidate or candidate == original:
        raise ValueError("Not the exact planned saved-zone change")
    if offset % 512:
        raise ValueError("Unaligned nav offset")
    out.mkdir(parents=True, exist_ok=False)
    for name, data in (("nav-pair-before.bin", original), ("nav-pair-fixed-plus13.bin", candidate)):
        path = out / name
        with path.open("xb") as saved:
            saved.write(data)
            saved.flush()
            os.fsync(saved.fileno())
        if path.read_bytes() != data:
            raise OSError("Saved nav snapshot verification failed")
        path.chmod(0o444)
    report = dict(plan, status="PENDING", device=identity, offset=offset,
                  backup_pair_sha256=sha(original), candidate_pair_sha256=sha(candidate),
                  write_bytes=2048, sectors=[offset // 512 + s for s in SECTORS],
                  clock_behaviour="FIXED_UTC_PLUS_13_NO_AUTOMATIC_DST")
    receipt = out / "write-report.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    started = False
    read_identity = identify_read or identify
    try:
        if identify() != identity:
            raise ValueError("Device identity changed before write")
        with source.open("r+b", buffering=0) as live:
            live.seek(offset)
            if read_exact(live, PAIR_SIZE) != original:
                raise ValueError("Nav baseline changed before write")
            for sector in SECTORS:
                at = sector * 512
                started = True
                write_sector(live, offset + at, candidate[at:at + 512])
            os.fsync(live.fileno())
        # A remounted filesystem does not prevent a read-only verification.
        # Mutations (including rollback) still use the unmounted-card check.
        if read_identity() != identity:
            raise ValueError("Device identity changed before verification")
        if read_at(source, offset, PAIR_SIZE) != candidate:
            raise OSError("Full nav-pair read-back mismatch")
        if read_identity() != identity:
            raise ValueError("Device identity changed during verification")
        report["status"] = "SAVED_PLUS_13_WRITTEN_BYTE_VERIFIED_CAR_TEST_PENDING"
    except Exception as error:
        report["error"] = str(error)
        if not started:
            report["status"] = "REFUSED_BEFORE_WRITE"
        else:
            try:
                if identify() != identity:
                    raise ValueError("Identity changed; rollback refused")
                with source.open("r+b", buffering=0) as live:
                    for sector in SECTORS:
                        at = sector * 512
                        write_sector(live, offset + at, original[at:at + 512])
                    os.fsync(live.fileno())
                if read_at(source, offset, PAIR_SIZE) != original:
                    raise OSError("Rollback read-back mismatch")
                report["status"] = "FAILED_ORIGINAL_NAV_PAIR_RESTORED"
            except Exception as rollback_error:
                report.update(status="FAILED_ROLLBACK_UNVERIFIED", rollback_error=str(rollback_error))
        receipt.write_text(json.dumps(report, indent=2) + "\n")
        raise
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--device", help="whole physical card identifier, e.g. disk9")
    inputs.add_argument("--image", type=Path, help="read-only offline check of a full-card backup")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.image and args.apply:
            raise ValueError("Never write saved images; --image is read-only")
        backup = root / "work/nz-clock/backups/20261024T073738Z/card-before-patch.img"
        receipt = json.loads((backup.parent / "backup-report.json").read_text())
        if (receipt.get("status") != "VERIFIED_READ_ONLY_CARD_BACKUP" or
                receipt.get("sha256") != BACKUP_SHA or backup.stat().st_size != backup_card.SIZE or
                backup.stat().st_mode & 0o222):
            raise ValueError("Pinned read-only full-card backup required")
        identity = None
        if args.device:
            if not re.fullmatch(r"disk[0-9]+", args.device):
                raise ValueError("Expected a whole disk identifier")
            identity = backup_card.identify(args.device)
            source = Path("/dev/r" + args.device)
            if sha(read_at(source, G214_OFFSET, G214_LENGTH)) != G214_SHA:
                raise ValueError("Card G214 differs from the reviewed v2 baseline")
        else:
            source = args.image.expanduser().resolve()
            if not source.is_file() or source.stat().st_size != backup_card.SIZE:
                raise ValueError("Expected a full-card image of known size")
        original = read_at(source, NAV_LBA * 512, PAIR_SIZE)
        candidate, plan = patch_pair(original)
        if identity is not None and backup_card.identify(args.device) != identity:
            raise ValueError("Card identity changed during preflight")
        plan.update(source_open_mode="rb", nav_lba=NAV_LBA, nav_pair_bytes=PAIR_SIZE,
                    before_sha256=sha(original), after_sha256=sha(candidate),
                    clock_behaviour="FIXED_UTC_PLUS_13_NO_AUTOMATIC_DST")
        if not args.apply or candidate == original:
            print(json.dumps(plan, indent=2))
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = root / "work/nz-clock/saved-zone-writes" / stamp
        result = apply_pair(source, original, candidate, identity,
                            lambda: backup_card.identify(args.device), out,
                            identify_read=lambda: backup_card.identify(args.device, require_unmounted=False))
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Saved-zone operation refused/failed: {error}\n")


if __name__ == "__main__":
    main()
