#!/usr/bin/env python3 -I
"""Preflight or apply the explicitly authorized G214 production-card experiment.

Default is read-only preflight. --apply writes only the pinned G214 slot range,
after a fresh verified backup and a byte-exact live baseline comparison. Two
unresolved header fields remain stock: this is an experiment, not proven bootable.
"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backup_card
import pack_slot

BACKUP_SHA = os.environ.get("NISSAN_BACKUP_SHA256", "")  # sha256 of your own verified backup_card.py image (card-specific, not committed); empty refuses
SLOT_SHA = "b32441b1f42707348bfac2b273fcd983ff54488bf77e3886ac100bf25a07db70"
VARIANTS = {
    "v2": {"slot_sha256": SLOT_SHA, "rom_sha256": pack_slot.CANDIDATE_SHA,
           "baseline_sha256": "8c9edf0086e71f94cabcd23b360e73c91bd0d950b8b84e5ae4822dc0e3aa98e3",
           "clock_behaviour": "NZ_AUTOMATIC_DST_CANDIDATE"},
    "fixed-nzdt-probe": {
        "slot_sha256": "a232889da7e317b5a1c749008dcd72a02131e478379994c75b0216c9ce07078d",
        "rom_sha256": pack_slot.CANDIDATES["fixed-nzdt-probe"],
        "baseline_sha256": "18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876",
        "clock_behaviour": "TEMPORARY_FIXED_UTC_PLUS_13_NO_AUTOMATIC_DST"},
}
OFFSET = 157696 * 512
OLD_LENGTH = 512 + 30737408
BLOCK = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_exact(stream, length):
    output = bytearray()
    while len(output) < length:
        data = stream.read(min(BLOCK, length - len(output)))
        if not data:
            raise OSError("Short read")
        output.extend(data)
    return bytes(output)


def write_exact(stream, data):
    position = 0
    while position < len(data):
        count = stream.write(memoryview(data)[position:position + BLOCK])
        if not count:
            raise OSError("Short write")
        position += count


def sync_device(stream):
    stream.flush()
    try:
        os.fsync(stream.fileno())
        return "fsync completed"
    except OSError as error:
        if error.errno not in (errno.EINVAL, errno.ENOTSUP):
            raise
        # Some device nodes do not implement file fsync. Record that limitation
        # explicitly and require closing/reopening for the raw read-back.
        return f"device fsync unsupported ({error.errno}); raw read-back required"


def apply_range(source, offset, original, slot, identity, identify, out, metadata):
    """Exact-range write with verified rollback; also testable on ordinary files."""
    if (offset % 512 or not slot or len(slot) % 512 or len(original) % 512 or
            len(slot) > len(original)):
        raise ValueError("Write must be sector aligned and contained in the backed-up range")
    out.mkdir(parents=True, exist_ok=False)
    rollback = out / "G214-before-write.bin"
    with rollback.open("xb") as saved:
        saved.write(original)
        saved.flush()
        os.fsync(saved.fileno())
    if rollback.read_bytes() != original:
        raise ValueError("Rollback range verification failed")
    report = dict(metadata, status="PENDING", device=identity, offset=offset,
                  write_bytes=len(slot), rollback_sha256=sha(original))
    reportpath = out / "write-report.json"
    reportpath.write_text(json.dumps(report, indent=2) + "\n")
    write_started = False
    try:
        if identify() != identity:
            raise ValueError("Device identity changed before write")
        with source.open("r+b", buffering=0) as device:
            device.seek(offset)
            if read_exact(device, len(original)) != original:
                raise ValueError("Live baseline changed before write")
            device.seek(offset)
            write_started = True
            write_exact(device, slot)
            report["sync"] = sync_device(device)
        with source.open("rb", buffering=0) as check:
            check.seek(offset)
            observed = read_exact(check, len(original))
        if observed != slot + original[len(slot):]:
            raise OSError("Card write read-back mismatch")
        report["status"] = "WRITTEN_AND_BYTE_VERIFIED_HARDWARE_BOOT_UNTESTED"
        reportpath.write_text(json.dumps(report, indent=2) + "\n")
        rollback.chmod(0o444)
        return report
    except Exception as error:
        report["error"] = str(error)
        if not write_started:
            report["status"] = "REFUSED_BEFORE_WRITE_NO_ROLLBACK_NEEDED"
            reportpath.write_text(json.dumps(report, indent=2) + "\n")
            raise
        try:
            if identify() != identity:
                raise ValueError("Device identity changed; automatic rollback refused")
            with source.open("r+b", buffering=0) as device:
                device.seek(offset)
                write_exact(device, original)
                report["rollback_sync"] = sync_device(device)
            with source.open("rb", buffering=0) as check:
                check.seek(offset)
                if read_exact(check, len(original)) != original:
                    raise OSError("Rollback verification failed")
            report["status"] = "FAILED_AND_ORIGINAL_RANGE_RESTORED"
        except Exception as restore_error:
            report["status"] = "FAILED_ROLLBACK_NOT_VERIFIED"
            report["rollback_error"] = str(restore_error)
        reportpath.write_text(json.dumps(report, indent=2) + "\n")
        raise


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--slot", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="v2")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"disk[0-9]+", args.device):
            raise ValueError("Expected a whole disk identifier")
        work = args.work_root.expanduser().resolve()
        backup = args.backup.expanduser().resolve()
        slotpath = args.slot.expanduser().resolve()
        if work.name != "work" or not backup.is_relative_to(work) or not slotpath.is_relative_to(work):
            raise ValueError("Backup, candidate and reports must remain under NISSAN_ROOT/work")
        receipt = json.loads((backup.parent / "backup-report.json").read_text())
        if (receipt.get("status") != "VERIFIED_READ_ONLY_CARD_BACKUP" or
                receipt.get("sha256") != BACKUP_SHA or receipt.get("bytes") != backup_card.SIZE or
                backup.stat().st_size != backup_card.SIZE or backup.stat().st_mode & 0o222):
            raise ValueError("Pinned, read-only, verified backup required")
        slot = slotpath.read_bytes()
        variant = VARIANTS[args.variant]
        if sha(slot) != variant["slot_sha256"] or len(slot) % 512 or len(slot) > pack_slot.SLOT_BYTES:
            raise ValueError("Unknown or invalid packed slot candidate")
        candidate = pack_slot.decode(slot[:512], slot[512:])
        if sha(candidate) != variant["rom_sha256"]:
            raise ValueError("Packed candidate does not decode to reviewed ROM")
        with backup.open("rb") as saved:
            saved.seek(OFFSET)
            original = read_exact(saved, OLD_LENGTH)
        if (sha(original[:512]) != pack_slot.HEADER_SHA or
                sha(original[512:]) != pack_slot.ORIGINAL_PACKED_SHA):
            raise ValueError("Backup G214 baseline mismatch")
        identity = backup_card.identify(args.device)
        source = Path("/dev/r" + args.device)
        with source.open("rb", buffering=0) as live:
            live.seek(OFFSET)
            observed = read_exact(live, OLD_LENGTH)
            if sha(observed) != variant["baseline_sha256"]:
                raise ValueError("Live card differs from the pinned baseline for this variant")
            # Save/restore the CURRENT range, including v2 when testing the
            # fixed probe. The untouched original full-card backup stays intact.
            original = observed
        if backup_card.identify(args.device) != identity:
            raise ValueError("Device identity changed during preflight")
        if not args.apply:
            print(json.dumps({"status": "READ_ONLY_PREFLIGHT_PASSED", "device": args.device,
                              "offset": OFFSET, "write_bytes": len(slot),
                              "variant": args.variant, "clock_behaviour": variant["clock_behaviour"],
                              "unresolved_header_fields": "preserved, enforcement unknown"}, indent=2))
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = work / "nz-clock" / "writes" / stamp
        report = apply_range(source, OFFSET, original, slot, identity,
                             lambda: backup_card.identify(args.device), out,
                             {"slot_sha256": variant["slot_sha256"], "backup_sha256": BACKUP_SHA,
                              "variant": args.variant, "clock_behaviour": variant["clock_behaviour"],
                              "unresolved_header_fields": "stock values preserved; boot acceptance unverified"})
        print(json.dumps(report, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Write/preflight refused or failed: {error}\n")


if __name__ == "__main__":
    main()
