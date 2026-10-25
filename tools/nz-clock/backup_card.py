#!/usr/bin/env python3 -I
"""Read-only backup of an identified 16 GB physical SD to a NEW work directory.

Never opens a device for writing, mounts/unmounts anything, or overwrites files.
macOS raw SD access may require running this tool with sudo.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess

SIZE = 16206790656
CHUNK = 8 * 1024 * 1024


def identify(device, *, require_unmounted=True):
    info = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", device]))
    if (info.get("DeviceIdentifier") != device or info.get("TotalSize") != SIZE or
            info.get("VirtualOrPhysical") != "Physical" or not info.get("RemovableMedia") or
            not info.get("WholeDisk")):
        raise ValueError("Device is not the expected whole removable physical 16 GB SD")
    if require_unmounted:
        disks = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist", device]))
        for disk in disks.get("AllDisksAndPartitions", []):
            if disk.get("DeviceIdentifier") == device:
                if any(part.get("MountPoint") for part in disk.get("Partitions", [])):
                    raise ValueError("Card partitions are mounted; operation refused")
    return {key: info.get(key) for key in ("DeviceIdentifier", "TotalSize", "DeviceTreePath", "MediaName")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="whole disk identifier, e.g. disk9")
    parser.add_argument("--work-root", required=True, type=Path, help="absolute NISSAN_ROOT/work path")
    args = parser.parse_args()
    if not re.fullmatch(r"disk[0-9]+", args.device):
        parser.error("Expected a whole disk identifier")
    work = args.work_root.expanduser().resolve()
    if not work.is_dir() or work.name != "work" or work.is_relative_to(Path("/dev")):
        parser.error("work-root must be the existing NISSAN_ROOT/work directory")
    try:
        identity = identify(args.device)
        source = Path("/dev/r" + args.device)
        # Open read-only BEFORE creating any output, so permission errors leave
        # no misleading partial backup directory.
        with source.open("rb", buffering=0) as src:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out = work / "nz-clock" / "backups" / stamp
            out.mkdir(parents=True, exist_ok=False)
            target = out / "card-before-patch.img"
            digest = hashlib.sha256()
            total = 0
            with target.open("xb") as dest:
                while total < SIZE:
                    block = src.read(min(CHUNK, SIZE - total))
                    if not block:
                        raise OSError("Short read from SD card")
                    dest.write(block)
                    digest.update(block)
                    total += len(block)
                    if total % (1024 * 1024 * 1024) == 0:
                        print(f"Backed up {total // (1024 * 1024 * 1024)} GiB", flush=True)
                dest.flush()
                os.fsync(dest.fileno())
            if identify(args.device) != identity:
                raise ValueError("Device identity changed during backup")
        check = hashlib.sha256()
        with target.open("rb") as saved:
            while block := saved.read(CHUNK):
                check.update(block)
        if digest.digest() != check.digest() or target.stat().st_size != SIZE:
            raise ValueError("Backup read-back verification failed")
        report = {"status": "VERIFIED_READ_ONLY_CARD_BACKUP", "bytes": total,
                  "sha256": digest.hexdigest(), "identity": identity,
                  "backup_path": str(target), "source_open_mode": "rb"}
        (out / "backup-report.json").write_text(json.dumps(report, indent=2) + "\n")
        target.chmod(0o444)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Backup failed: {error}\n")


if __name__ == "__main__":
    main()
