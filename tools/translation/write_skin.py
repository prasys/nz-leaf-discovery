#!/usr/bin/env python3 -I
"""Preflight or apply a reviewed skin build to /SkinChange/002/substance.skn on the card.

Default is a read-only preflight. --apply writes only the sectors holding
substance.skn on hidden p2 (LBA 29925953, 39,113 sectors; the 480 bytes past
the end of the file are written back unchanged), after:
  - a verified full-card backup made by tools/nz-clock/backup_card.py (pinned SHA256)
  - a same-size build whose SHA256 is pinned in BUILDS below after review
  - the live card's exFAT entry still placing the file there, contiguous
  - the live file bytes matching a pinned baseline (stock skin or a pinned build)
It saves a rollback snapshot of the live range, writes, fsyncs, reopens the
device to compare the whole range, and leaves a JSON receipt under
$NISSAN_ROOT/work/translation/writes/. Agents never run --apply; the owner does.
"""
import argparse
from datetime import datetime, timezone
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skn_format  # noqa: E402
import skn_strings  # noqa: E402

P2_LBA = 29925377
SKIN_LBA = skn_strings.SKN_SECTOR
OFFSET = SKIN_LBA * 512
FILE_LEN = skn_strings.SKN_SIZE                   # 20,025,376
SPAN = (FILE_LEN + 511) // 512 * 512              # 20,025,856: whole sectors
SKIN_PATH = ("SkinChange", "002", "substance.skn")
# stock (LeafHacker) skin, identical in the 2026-10-24 image and the verified backup
BASELINE_SHA = "ea5b5a34d912c3344e3157e453025734474d104046434537775f96c85ae06f4d"
# verified full-card backups (backup_card.py receipts). They are card-specific, so they are
# not committed: set NISSAN_BACKUP_SHA256 (comma-separated) to your own reviewed backup's sha256.
BACKUP_SHAS = {sha: "local backup pin" for sha in
               os.environ.get("NISSAN_BACKUP_SHA256", "").split(",") if sha}
# reviewed skin builds: sha256 -> description
BUILDS = {
    "6a54198aa04e6c104c6dd5bdc86005f495dca979bda95549ac687da0821ebbb7":
        "nz-en v1 in place: translations/nz-en.tsv @1ea46a9 (sha256 30ffce26), 461 cells",
    "d220720b9f282703590cdafc52616269c2882777479f2eb9fae62bbf5e5826c4":
        "nz-en v1 --repack (full wording): same tsv, 461 cells, section 2 at 0x51B680",
    "ec1138c812d5bc111ad30d2e8937b0657be1f8092f832cefb67a83916bfa192b":
        "nz-en v1 + hour row (#1): 11 bytes, Clock offset row -> SetExpOffsetHourSetting, +-12",
    "f255f86933cb2c83426bca395f74d3af8cea9bd9c7e5d330c1d6db0648f6d9a0":
        "nz-en v1 + hour row + DST toggle (#1): +5 bytes, time-indication toggle -> SetExpAutoDstSetting",
}
STOCK_TRAILER = bytes.fromhex(
    "04000204" + b"470-6253-48\0".hex() + "fd96650f" + b"SKINSK18NNNI.183".hex())
BLOCK = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def backup_card():
    """tools/nz-clock/backup_card.py: device identity and card size."""
    path = HERE.parent / "nz-clock" / "backup_card.py"
    if not path.exists():
        raise ValueError("%s is missing" % path)
    spec = importlib.util.spec_from_file_location("backup_card", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        return f"device fsync unsupported ({error.errno}); raw read-back required"


def sector_reader(stream):
    """read(offset, n) that only issues whole-sector, sector-aligned reads.

    macOS raw devices (/dev/rdiskN) reject anything else with EINVAL."""
    def read(off, n):
        start = off // 512 * 512
        end = (off + n + 511) // 512 * 512
        stream.seek(start)
        return read_exact(stream, end - start)[off - start:off - start + n]
    return read


def skin_extent(read):
    """Find substance.skn through the p2 exFAT tree. read(offset, n) -> bytes.

    Returns (byte offset, size, contiguous)."""
    base = P2_LBA * 512
    bs = read(base, 512)
    if bs[3:11] != b"EXFAT   ":
        raise ValueError("No exFAT boot sector at p2 LBA %d" % P2_LBA)
    fatofs, _, heapofs, ccount, rootc = struct.unpack_from("<IIIII", bs, 0x50)
    bps, spc = 1 << bs[0x6C], 1 << bs[0x6D]
    csz = bps * spc

    def coff(c):
        return base + heapofs * bps + (c - 2) * csz

    def clusters(c, nofat, size):
        if nofat:
            return list(range(c, c + max(1, (size + csz - 1) // csz)))
        out = []
        while 2 <= c < 0xFFFFFFF7 and len(out) < ccount:
            out.append(c)
            c, = struct.unpack("<I", read(base + fatofs * bps + 4 * c, 4))
        return out

    def find(c, nofat, size, name):
        data = b"".join(read(coff(x), csz) for x in clusters(c, nofat, size))
        for p in range(0, len(data) - 32, 32):
            if data[p] == 0:
                break
            if data[p] != 0x85:
                continue
            sec = data[p + 1]
            ent = data[p + 32:p + 32 * (sec + 1)]
            if len(ent) < 64 or ent[0] != 0xC0:
                continue
            nlen = ent[3]
            nm = b"".join(ent[q + 2:q + 32] for q in range(32, len(ent), 32) if ent[q] == 0xC1)
            if nm[:2 * nlen].decode("utf-16le", "replace") == name:
                first, = struct.unpack_from("<I", ent, 0x14)
                length, = struct.unpack_from("<Q", ent, 0x18)
                return first, bool(ent[1] & 2), length, data[p + 4] & 0x10
        raise ValueError("%s not found on p2" % name)

    c, nofat, size = rootc, False, 0
    for i, name in enumerate(SKIN_PATH):
        c, nofat, size, isdir = find(c, nofat, size, name)
        if bool(isdir) != (i < len(SKIN_PATH) - 1):
            raise ValueError("%s has the wrong type" % name)
    run = clusters(c, nofat, size)
    contiguous = nofat or run == list(range(run[0], run[0] + len(run)))
    return coff(c), size, contiguous


def check_build(build):
    """Same-size build that parses as a skin and keeps the stock trailer."""
    if len(build) != FILE_LEN:
        raise ValueError("Build is %d bytes; only same-size (%d) builds can be written"
                         % (len(build), FILE_LEN))
    if build[-skn_strings.TRAILER_LEN:] != STOCK_TRAILER:
        raise ValueError("Build trailer differs from the stock skin")
    skn_format.records(build)



def apply_range(source, offset, original, payload, identity, identify, out, metadata):
    """Exact-range write with verified rollback; also testable on ordinary files."""
    if (offset % 512 or not payload or len(payload) % 512 or len(original) % 512 or
            len(payload) != len(original)):
        raise ValueError("Write must be sector aligned and exactly cover the backed-up range")
    out.mkdir(parents=True, exist_ok=False)
    rollback = out / "substance-before-write.bin"
    with rollback.open("xb") as saved:
        saved.write(original)
        saved.flush()
        os.fsync(saved.fileno())
    if rollback.read_bytes() != original:
        raise ValueError("Rollback range verification failed")
    report = dict(metadata, status="PENDING", device=identity, offset=offset,
                  write_bytes=len(payload), rollback_sha256=sha(original),
                  payload_sha256=sha(payload))
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
            write_exact(device, payload)
            report["sync"] = sync_device(device)
        with source.open("rb", buffering=0) as check:
            check.seek(offset)
            observed = read_exact(check, len(original))
        if observed != payload:
            raise OSError("Card write read-back mismatch")
        report["status"] = "WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED"
        reportpath.write_text(json.dumps(report, indent=2) + "\n")
        rollback.chmod(0o444)
        return report
    except BaseException as error:      # includes Ctrl-C mid-write
        report["error"] = str(error) or type(error).__name__
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


def preflight(read, build, builds=None):
    """Checks shared by preflight and apply. read(offset, n) reads the live card.

    Returns (live span, payload span, live label)."""
    builds = BUILDS if builds is None else builds
    known = dict(builds, **{BASELINE_SHA: "stock skin"})
    check_build(build)
    if sha(build) not in known:
        raise ValueError("Build sha256 %s is not pinned in BUILDS (review it, then pin it)"
                         % sha(build))
    off, size, contiguous = skin_extent(read)
    if (off, size, contiguous) != (OFFSET, FILE_LEN, True):
        raise ValueError("exFAT entry moved: offset %d size %d contiguous %s" % (off, size, contiguous))
    live = read(OFFSET, SPAN)
    label = known.get(sha(live[:FILE_LEN]))
    if label is None:
        raise ValueError("Live substance.skn (sha256 %s) matches no pinned baseline"
                         % sha(live[:FILE_LEN]))
    payload = build + live[FILE_LEN:]
    if payload == live:
        raise ValueError("The card already holds this build")
    return live, payload, label


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", required=True, help="whole disk identifier, e.g. disk9")
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path,
                        help="a pinned build, e.g. work/hour-offset-ui/build-v1/substance.skn")
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"disk[0-9]+", args.device):
            raise ValueError("Expected a whole disk identifier")
        work = args.work_root.expanduser().resolve()
        backup = args.backup.expanduser().resolve()
        buildpath = args.build.expanduser().resolve()
        if work.name != "work" or not backup.is_relative_to(work) or not buildpath.is_relative_to(work):
            raise ValueError("Backup, build and reports must remain under NISSAN_ROOT/work")
        bc = backup_card()
        receipt = json.loads((backup.parent / "backup-report.json").read_text())
        if (receipt.get("status") != "VERIFIED_READ_ONLY_CARD_BACKUP" or
                receipt.get("sha256") not in BACKUP_SHAS or receipt.get("bytes") != bc.SIZE or
                backup.stat().st_size != bc.SIZE or backup.stat().st_mode & 0o222):
            raise ValueError("Pinned, read-only, verified backup required")
        with backup.open("rb") as saved:
            saved.seek(OFFSET)
            if sha(read_exact(saved, FILE_LEN)) != BASELINE_SHA:
                raise ValueError("Backup does not hold the stock skin at LBA %d" % SKIN_LBA)
        build = buildpath.read_bytes()
        identity = bc.identify(args.device)
        source = Path("/dev/r" + args.device)
        with source.open("rb", buffering=0) as live_dev:
            original, payload, label = preflight(sector_reader(live_dev), build)
        if bc.identify(args.device) != identity:
            raise ValueError("Device identity changed during preflight")
        info = {"device": args.device, "offset": OFFSET, "lba": SKIN_LBA, "write_bytes": SPAN,
                "live": label, "live_sha256": sha(original[:FILE_LEN]),
                "build": BUILDS.get(sha(build), "stock skin (restore)"),
                "build_sha256": sha(build), "backup_sha256": receipt["sha256"],
                "trailer_value": "0x0F6596FD unchanged; whether the unit checks it is unknown"}
        if not args.apply:
            print(json.dumps(dict(info, status="READ_ONLY_PREFLIGHT_PASSED"), indent=2))
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = work / "translation" / "writes" / stamp
        report = apply_range(source, OFFSET, original, payload, identity,
                             lambda: bc.identify(args.device), out, info)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Write/preflight refused or failed: {error}\n")


if __name__ == "__main__":
    main()
