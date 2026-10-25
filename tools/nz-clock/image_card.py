#!/usr/bin/env python3 -I
"""Read-only imaging of a physical SD card to $NISSAN_IMG.

If the target image exists: verify it (size, SHA256 against <image-name>.report.json,
mode 0444) and exit. Never calls diskutil or opens a device in that mode.
If it doesn't: a read-only preflight by default. --image (owner, with sudo)
opens /dev/rdiskN with O_RDONLY, copies to a temp file in the target directory,
fsyncs, re-reads and hashes it, links it into place without overwriting, writes
<image-name>.report.json and chmods both files 0444.

Never opens a device for writing, mounts or unmounts anything, overwrites a
file, or deletes anything but its own temp file. Agents never run this against
a real device; the owner does.

Exit codes: 0 ok, 1 refused or failed, 2 usage, 3 existing image failed verification.
"""
import argparse
import errno
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import stat
import subprocess
import sys

CHUNK = 8 * 1024 * 1024
GIB = 1024 * 1024 * 1024
SECTOR = 512
DEV_PREFIX = "/dev/r"
LEGACY_REPORT = "image-report.json"      # read only if its "image" field matches
RENAME_EXCL = 0x4                         # macOS renamex_np flag: fail if the target exists
TOOL = "tools/nz-clock/image_card.py"
DEFAULT_IMG = "~/nissan/sdcard/nissan-sd-485-1972-00.img"


class Refused(ValueError):
    """A read-only precondition failed; nothing was opened or written."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def report_path_for(target):
    """<image-name>.report.json; the old shared image-report.json counts only if it names this image."""
    own = target.parent / (target.name + ".report.json")
    if os.path.lexists(own):
        return own
    legacy = target.parent / LEGACY_REPORT
    try:
        if json.loads(legacy.read_text()).get("image") == target.name:
            return legacy
    except (OSError, ValueError, AttributeError):
        pass
    return own


def verify_image(target, expect_bytes=None):
    """Check size, SHA256 against the sidecar report, and mode 0444. Returns the report."""
    info = os.lstat(target)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{target} is not a regular file")
    if stat.S_IMODE(info.st_mode) != 0o444:
        raise ValueError(f"image mode is {stat.S_IMODE(info.st_mode):04o}, expected 0444")
    report_path = report_path_for(target)
    try:
        report_info = os.lstat(report_path)
    except FileNotFoundError:
        raise ValueError(f"missing sidecar {report_path.name} (hand-made image? use --adopt)") from None
    if not stat.S_ISREG(report_info.st_mode) or stat.S_IMODE(report_info.st_mode) != 0o444:
        raise ValueError(f"{report_path.name} is not a regular file with mode 0444")
    try:
        report = json.loads(report_path.read_text())
        recorded_bytes, recorded_sha, recorded_name = report["bytes"], report["sha256"], report["image"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"unreadable {report_path.name}: {error!r}") from None
    if recorded_name != target.name:
        raise ValueError(f"report is for {recorded_name!r}, not {target.name!r}")
    if info.st_size != recorded_bytes:
        raise ValueError(f"size {info.st_size} != report {recorded_bytes}")
    if expect_bytes is not None and info.st_size != expect_bytes:
        raise ValueError(f"size {info.st_size} != --expect-bytes {expect_bytes}")
    actual = sha256_file(target)
    if actual != recorded_sha:
        raise ValueError(f"SHA256 {actual} != report {recorded_sha}")
    return report


def identify(device, expect_bytes, *, require_unmounted=True):
    info = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", device]))
    if info.get("DeviceIdentifier") != device:
        raise Refused(f"diskutil reports {info.get('DeviceIdentifier')!r}, not {device}")
    if not info.get("WholeDisk"):
        raise Refused(f"{device} is not a whole disk")
    if info.get("VirtualOrPhysical") != "Physical":
        raise Refused(f"{device} is not a physical disk")
    if not info.get("RemovableMedia"):
        raise Refused(f"{device} is not removable media")
    if info.get("TotalSize") != expect_bytes:
        raise Refused(f"{device} is {info.get('TotalSize')} bytes, not --expect-bytes {expect_bytes}")
    if require_unmounted:
        disks = plistlib.loads(subprocess.check_output(["diskutil", "list", "-plist", device]))
        for disk in disks.get("AllDisksAndPartitions", []):
            if disk.get("DeviceIdentifier") == device:
                if any(part.get("MountPoint") for part in disk.get("Partitions", [])):
                    raise Refused(f"{device} has mounted partitions; unmount is the owner's step")
    return {key: info.get(key) for key in ("DeviceIdentifier", "TotalSize", "DeviceTreePath", "MediaName")}


def _renamex_np():
    """libc renamex_np (macOS) or None."""
    try:
        import ctypes
        func = ctypes.CDLL(None, use_errno=True).renamex_np
    except (ImportError, OSError, AttributeError):
        return None
    func.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    func.restype = ctypes.c_int
    return func


def rename_excl(src, dst):
    """Rename that fails with FileExistsError if dst exists (no hard links needed)."""
    func = _renamex_np()
    if func is None:
        raise OSError("renamex_np is not available")
    import ctypes
    if func(os.fsencode(src), os.fsencode(dst), RENAME_EXCL) != 0:
        err = ctypes.get_errno()
        raise (FileExistsError if err == errno.EEXIST else OSError)(err, os.strerror(err), str(dst))


def choose_publish_method(directory):
    """Probe with tiny temp files in the target directory, so a file system without
    hard links (exFAT) is refused here and never after the full copy."""
    tag = f".probe.{os.getpid()}"
    made = []
    try:
        def tiny(name):
            path = directory / (tag + name)
            write_new(path, b"x")
            made.append(path)
            return path
        first = tiny(".a")
        try:
            link = directory / (tag + ".b")
            os.link(first, link)
            made.append(link)
            return "link"
        except OSError:
            pass
        try:
            second = directory / (tag + ".c")
            rename_excl(first, second)
            made.remove(first)
            made.append(second)
            return "rename_excl"
        except OSError:
            raise Refused(f"{directory} supports neither hard links nor renamex_np RENAME_EXCL; "
                          "choose --out on an APFS/HFS+ volume") from None
    finally:
        for path in made:
            try:
                os.unlink(path)      # our own probe files only
            except FileNotFoundError:
                pass


def preflight(device, expect_bytes, target):
    """Read-only checks. Returns (device identity, publish method)."""
    if not target.parent.is_dir():
        raise Refused(f"target directory {target.parent} does not exist")
    for path in (target, target.parent / (target.name + ".report.json")):
        if os.path.lexists(path):
            raise Refused(f"{path} already exists; this tool never overwrites")
    free = shutil.disk_usage(target.parent).free
    if free < expect_bytes:
        raise Refused(f"only {free} bytes free in {target.parent}, need {expect_bytes}")
    method = choose_publish_method(target.parent)
    return identify(device, expect_bytes), method


def hand_back_ownership(fd):
    """Under sudo, give our files to the invoking user so the owner can manage them."""
    if os.geteuid() == 0 and os.environ.get("SUDO_UID", "").isdigit() and os.environ.get("SUDO_GID", "").isdigit():
        os.fchown(fd, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        hand_back_ownership(fd)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd is not None:
            os.close(fd)


def publish(temp, target, method):
    """Move temp into place without overwriting; FileExistsError if the target appeared."""
    if method == "link":
        os.link(temp, target)
        os.unlink(temp)
    else:
        rename_excl(temp, target)


def image(device, expect_bytes, target, source):
    """Copy `source` (the raw device, O_RDONLY) to `target`. Returns the report."""
    identity, method = preflight(device, expect_bytes, target)
    # Open read-only BEFORE creating any output, so permission errors leave nothing behind.
    src = os.open(source, os.O_RDONLY)
    temp = target.parent / f".{target.name}.partial.{os.getpid()}"
    temp_made = False
    try:
        digest = hashlib.sha256()
        total = 0
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        temp_made = True
        try:
            hand_back_ownership(fd)
        except OSError:
            os.close(fd)
            raise
        with os.fdopen(fd, "wb") as dest:
            while total < expect_bytes:
                block = os.read(src, min(CHUNK, expect_bytes - total))
                if not block:
                    raise OSError(f"Short read from {source}: {total} of {expect_bytes} bytes")
                dest.write(block)
                digest.update(block)
                if total // GIB != (total + len(block)) // GIB:
                    print(f"Imaged {(total + len(block)) // GIB} GiB", flush=True)
                total += len(block)
            dest.flush()
            os.fsync(dest.fileno())
        if identify(device, expect_bytes) != identity:
            raise ValueError("Device identity changed during imaging")
        if os.stat(temp).st_size != expect_bytes or sha256_file(temp) != digest.hexdigest():
            raise ValueError("Re-read verification of the temp image failed")
        os.chmod(temp, 0o444)
        publish(temp, target, method)
        temp_made = False
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        report = {"status": "IMAGED_AND_VERIFIED", "image": target.name, "bytes": total,
                  "sha256": digest.hexdigest(), "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "device": identity, "source_open_mode": "O_RDONLY"}
        report_path = target.parent / (target.name + ".report.json")
        write_new(report_path, (json.dumps(report, indent=2) + "\n").encode())
        os.chmod(report_path, 0o444)
        verify_image(target, expect_bytes)   # the verify mode must accept what we just made
        return report
    finally:
        os.close(src)
        if temp_made:
            try:
                os.unlink(temp)              # our own temp file only
            except FileNotFoundError:
                pass


def adopt(target):
    """Write a report for a hand-made image. Reads the image once; touches no device."""
    info = os.lstat(target)
    if not stat.S_ISREG(info.st_mode):
        raise Refused(f"{target} is not a regular file")
    if stat.S_IMODE(info.st_mode) != 0o444:
        raise Refused(f"image mode is {stat.S_IMODE(info.st_mode):04o}; owner must run: chmod 0444 {shlex.quote(str(target))}")
    path = report_path_for(target)
    if os.path.lexists(path):
        raise Refused(f"{path} already exists; this tool never overwrites")
    digest = sha256_file(target)
    if os.lstat(target).st_size != info.st_size:
        raise ValueError("image changed while hashing")
    report = {"status": "ADOPTED_UNVERIFIED_SOURCE", "image": target.name, "bytes": info.st_size,
              "sha256": digest, "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "device": None,
              "note": "Image made by hand. Hashed as found; the source card was not checked against it."}
    write_new(path, (json.dumps(report, indent=2) + "\n").encode())
    os.chmod(path, 0o444)
    verify_image(target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help=f"image path (default $NISSAN_IMG or {DEFAULT_IMG})")
    parser.add_argument("--device", help="whole disk identifier, e.g. disk9 (only used if the image doesn't exist)")
    parser.add_argument("--expect-bytes", type=int, help="exact card size in bytes, as you confirm it")
    parser.add_argument("--adopt", action="store_true", help="existing hand-made image with no report: hash it and write the report")
    parser.add_argument("--image", action="store_true", help="owner, with sudo: read the card into the image")
    args = parser.parse_args(argv)
    target = (args.out or Path(os.environ.get("NISSAN_IMG", DEFAULT_IMG))).expanduser()
    target = target.parent.resolve() / target.name

    if args.adopt and not os.path.lexists(target):
        parser.error("--adopt needs an existing image")
    if args.adopt and args.image:
        parser.error("--adopt and --image are exclusive")
    if args.adopt:
        try:
            report = adopt(target)
        except Refused as error:
            print(f"REFUSED: {error}")
            return 1
        except (OSError, ValueError) as error:
            print(f"ADOPT_FAILED: {error}")
            return 1
        print(f"IMAGE_ADOPTED_UNVERIFIED_SOURCE: {target} bytes={report['bytes']} sha256={report['sha256']} (no device touched)")
        return 0

    if os.path.lexists(target):
        if args.expect_bytes is not None and args.expect_bytes <= 0:
            parser.error("--expect-bytes must be positive")
        try:
            report = verify_image(target, args.expect_bytes)
        except (OSError, ValueError) as error:
            print(f"IMAGE_VERIFY_FAILED: {error}")
            return 3
        print(f"IMAGE_VERIFIED: {target} bytes={report['bytes']} sha256={report['sha256']} (no device touched)")
        return 0

    if not args.device or not re.fullmatch(r"disk[0-9]+", args.device):
        parser.error("image missing: --device diskN (a whole disk identifier) is required")
    if not args.expect_bytes or args.expect_bytes <= 0 or args.expect_bytes % SECTOR:
        parser.error("image missing: --expect-bytes N (positive multiple of 512) is required")
    source = Path(DEV_PREFIX + args.device)
    command = " ".join(["sudo", "python3", "-I", TOOL, "--device", args.device,
                        "--expect-bytes", str(args.expect_bytes), "--out", shlex.quote(str(target)), "--image"])
    try:
        if not args.image:
            identity, method = preflight(args.device, args.expect_bytes, target)
            print(f"Plan: read {source} (O_RDONLY) -> {target}, {args.expect_bytes} bytes, then verify and chmod 0444.")
            print(f"Device: {identity}; publish by {method}")
            print(f"Owner runs, with the card in the reader and unmounted:\n  {command}")
            print("READ_ONLY_PREFLIGHT_PASSED")
            return 0
        report = image(args.device, args.expect_bytes, target, source)
    except Refused as error:
        print(f"REFUSED: {error}")
        return 1
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"IMAGING_FAILED: {error}")
        return 1
    print(f"IMAGED_AND_VERIFIED: {target} bytes={report['bytes']} sha256={report['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
