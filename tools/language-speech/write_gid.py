#!/usr/bin/env python3
"""Pinned GID p1 writer: read-only by default; --apply belongs to the owner.

Only a same-size public GID with allowlisted greeting/EV modifications is
accepted. The writer trims identical leading/trailing sectors, so every write
is wholly inside the GID file. The final partial sector is never written.
Never run --apply as an agent. Tests exercise ordinary temporary files only.

Other owners pass --pins FILE (JSON: card_bytes, backup_sha256, builds) with
their own card size, verified backup hash and reviewed build hashes. With
--pins the GID is located through the card's own FAT32 instead of our pinned
geometry; the file must still be the stock-size, contiguous SJP00300.GID.
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
from gid_patch import OUTER_SHA, sha, validate

P1_LBA = 888833
OFFSET = 13346210304
FILE_LEN = 37882424
SPAN = (FILE_LEN+511)//512*512
BLOCK = 1024*1024
# Owner-reviewed English voice builds: sha256 -> description
BUILDS = {
    "7e007bfb5c40f0039dc30fc1749ce91d819352bf5275c317cfb83cca075af0c1":
        "Penny v1: welcome clips 764-819 in NZ English, SSC, same size",
    "0a80b63701918d323230f39188fa0d8fb6570242b659a7bfbf3d93a0ff994ed4":
        "Penny v1.1: v1 clips loudness-matched to stock (-16 dBFS RMS target, -2 dBFS peak)",
    "4635b41235237f13492154b40fba35ec3cd9dc297b4752bd9a9dfe9a57c7b090":
        "Penny v2: v1.1 greeting plus 41 EV alert clips (428-442/444/548/1297-1302/1320/1322/1345/1416/1417/1537/1573/1594/1709/1721-1723/1740/1743-1746/1840)",
}
BACKUP_SHAS = {"b0bb50ec76086585221080b72dd23e1219ad2470c2a21c3059a9ff53658c7540"}
# EV builds keep their apply receipts with the EV render/fit artifacts.
RECEIPT_PATHS = {
    "4635b41235237f13492154b40fba35ec3cd9dc297b4752bd9a9dfe9a57c7b090":
        "language-speech/en-ev/writes",
}
SIZE = 16206790656
WORK = Path(os.environ.get("NISSAN_ROOT", Path.home()/"nissan")).expanduser()/"work"


def load_pins(path):
    """Owner pins: {"card_bytes": int, "backup_sha256": [hex], "builds": {hex: label}}."""
    pins = json.loads(Path(path).expanduser().read_text())
    hexes = list(pins.get("backup_sha256", [])) + list(pins.get("builds", {}))
    if (not isinstance(pins.get("card_bytes"), int) or pins["card_bytes"] < SPAN or
            pins["card_bytes"] % 512 or not pins.get("backup_sha256") or
            not all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in hexes)):
        raise ValueError("pins file needs card_bytes, backup_sha256 [..] and builds {sha256: label}")
    return pins


def backup_card():
    spec = importlib.util.spec_from_file_location("backup_card", HERE.parent/"nz-clock/backup_card.py")
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


def save_report(path,report):
    with path.open("w") as f:
        f.write(json.dumps(report,indent=2)+"\n")
        f.flush()
        os.fsync(f.fileno())


def apply_range(source, offset, original, payload, identity, identify, out, metadata, verify=None):
    """Exact-range write with verified rollback; also testable on ordinary files."""
    if (offset % 512 or not payload or len(payload) % 512 or len(original) % 512 or
            len(payload) != len(original)):
        raise ValueError("Write must be sector aligned and exactly cover the backed-up range")
    out.mkdir(parents=True, exist_ok=False)
    rollback = out / "gid-before-write.bin"
    with rollback.open("xb") as saved:
        saved.write(original)
        saved.flush()
        os.fsync(saved.fileno())
    if rollback.read_bytes() != original:
        raise ValueError("Rollback range verification failed")
    rollback.chmod(0o444)
    report = dict(metadata, status="PENDING", device=identity, offset=offset,
                  write_bytes=len(payload), rollback_sha256=sha(original),
                  payload_sha256=sha(payload))
    reportpath = out / "write-report.json"
    save_report(reportpath,report)
    write_started = False
    try:
        if identify() != identity:
            raise ValueError("Device identity changed before write")
        if verify:
            verify(original)
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
        if verify:
            verify(payload)
        report["status"] = "WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED"
        save_report(reportpath,report)
        rollback.chmod(0o444)
        return report
    except BaseException as error:      # includes Ctrl-C mid-write
        report["error"] = str(error) or type(error).__name__
        if not write_started:
            report["status"] = "REFUSED_BEFORE_WRITE_NO_ROLLBACK_NEEDED"
            save_report(reportpath,report)
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
            if verify:
                verify(original)
            report["status"] = "FAILED_AND_ORIGINAL_RANGE_RESTORED"
        except Exception as restore_error:
            report["status"] = "FAILED_ROLLBACK_NOT_VERIFIED"
            report["rollback_error"] = str(restore_error)
        save_report(reportpath,report)
        raise


def gid_extent(read, pinned=True, card_bytes=None):
    """Walk only SPEECH/JP/GID short directory entries and both FAT copies.

    The pinned file's 579 clusters are contiguous on this image. Refuse moved,
    resized, fragmented or mirrored-FAT-inconsistent files; never change FAT.
    pinned=False (owner --pins) accepts another card's p1 LBA and FAT32
    geometry, but still requires a stock-size contiguous file, and bounds the
    volume, both FATs and the GID sector envelope by p1 and by card_bytes.
    """
    mbr = read(0, 512)
    p1, p1_sectors = struct.unpack_from("<II", mbr, 454)
    if mbr[510:] != b"\x55\xaa" or (pinned and p1 != P1_LBA) or not p1:
        raise ValueError("p1 MBR mismatch")
    if not pinned:
        if card_bytes is None:
            raise ValueError("card size required for discovered geometry")
        if mbr[450] not in (0x0b, 0x0c) or not p1_sectors or (p1+p1_sectors)*512 > card_bytes:
            raise ValueError("p1 MBR entry is not a FAT32 partition inside the card")
        for k in (1, 2, 3):
            start, count = struct.unpack_from("<II", mbr, 446+16*k+8)
            if count and start < p1+p1_sectors and p1 < start+count:
                raise ValueError("p1 overlaps another MBR partition")
    b = read(p1*512, 512)
    bps, spc, reserved, copies = struct.unpack_from("<HBHB", b, 11)
    fatsz, root = struct.unpack_from("<I", b, 36)[0], struct.unpack_from("<I", b, 44)[0]
    total = struct.unpack_from("<I", b, 32)[0]
    if pinned and (bps,spc,reserved,copies,fatsz,root,total) != (512,128,38,2,1773,2,29036544):
        raise ValueError("pinned p1 FAT32 geometry mismatch")
    if (b[82:90] != b"FAT32   " or bps != 512 or copies != 2 or spc not in (1,2,4,8,16,32,64,128)
            or not reserved or not fatsz or root < 2 or not total):
        raise ValueError("p1 is not a two-FAT FAT32 volume with 512-byte sectors")
    if (not pinned and total > p1_sectors) or reserved+copies*fatsz >= total:
        raise ValueError("FAT32 volume does not fit its partition")
    fat0 = p1*512 + reserved*bps
    fat = read(fat0, fatsz*bps)
    mirror = read(fat0+fatsz*bps, fatsz*bps)
    data0 = fat0+copies*fatsz*bps
    csz = bps*spc
    limit = (total-reserved-copies*fatsz)//spc+2
    if limit*4 > fatsz*bps:
        raise ValueError("FAT too small for the volume's clusters")
    volume_end = (p1+total)*512

    def chain(cluster):
        result, seen = [], set()
        while 2 <= cluster < 0xffffff8:
            if cluster >= limit or cluster in seen:
                raise ValueError("FAT chain out of range/cyclic/too long")
            seen.add(cluster)
            result.append(cluster)
            pos = cluster*4
            nxt = struct.unpack_from("<I", fat, pos)[0] & 0xfffffff
            if nxt != struct.unpack_from("<I", mirror, pos)[0] & 0xfffffff:
                raise ValueError("mirrored FAT chain mismatch")
            cluster = nxt
        if cluster < 0xffffff8:
            raise ValueError("invalid FAT chain terminator")
        return result

    def coff(c):
        return data0+(c-2)*csz

    def find(c, name):
        directory = b"".join(read(coff(x),csz) for x in chain(c))
        matches = []
        for p in range(0,len(directory),32):
            e = directory[p:p+32]
            if e[0] == 0:
                break
            if e[0] == 0xe5 or e[11] == 15 or e[11] & 8:
                continue
            short = e[:8].decode("ascii","replace").strip()
            ext = e[8:11].decode("ascii","replace").strip()
            if short+("."+ext if ext else "") != name:
                continue
            first = (struct.unpack_from("<H",e,20)[0]<<16)|struct.unpack_from("<H",e,26)[0]
            matches.append((first,struct.unpack_from("<I",e,28)[0],bool(e[11]&16)))
        if len(matches) != 1:
            raise ValueError("expected unique public speech directory entry")
        return matches[0]

    c = root
    for name in ("SPEECH","JP","GID"):
        c, _, isdir = find(c,name)
        if not isdir:
            raise ValueError("speech path is not a directory")
    c, size, isdir = find(c,"SJP00300.GID")
    run = chain(c)
    if isdir or len(run) != (size+csz-1)//csz or run != list(range(c,c+len(run))):
        raise ValueError("GID allocation is not the pinned contiguous file")
    result = coff(c), size
    if result != (OFFSET,FILE_LEN) and (pinned or size != FILE_LEN or result[0] % 512):
        raise ValueError("GID moved or resized")
    if result[0]+SPAN > volume_end:
        raise ValueError("GID sector envelope extends past the FAT32 volume")
    return result


def preflight(read, stock, build, builds=None, pinned=True, card_bytes=None):
    builds = BUILDS if builds is None else builds
    known = {OUTER_SHA: "stock GID", **builds}
    if sha(build) not in known:
        raise ValueError("payload hash is not pinned; owner-selected voice build required")
    validate(stock, build, "all")
    offset, _ = gid_extent(read, pinned, card_bytes)
    live = read(offset,SPAN)
    if len(live) != SPAN:
        raise ValueError("short live GID sector envelope")
    label = known.get(sha(live[:FILE_LEN]))
    if label is None:
        raise ValueError("live GID baseline hash is not pinned")
    validate(stock,live[:FILE_LEN],"all")
    payload = build + live[FILE_LEN:]
    if payload == live:
        raise ValueError("device already holds this GID build")
    return live,payload,label


def write_window(original,payload):
    """One sector-aligned changed window, strictly contained in the GID file."""
    if len(original) != SPAN or len(payload) != SPAN:
        raise ValueError("full GID sector views required")
    first,last = 0,SPAN
    while first < last and original[first:first+512] == payload[first:first+512]:
        first += 512
    while last > first and original[last-512:last] == payload[last-512:last]:
        last -= 512
    if first == last or last > FILE_LEN:
        raise ValueError("empty write or write beyond the GID file")
    return first,last


def verified_backup(path, expected_size=SIZE, backup_shas=None, pinned=True):
    """Hash the whole backup, then read its stock GID (geometry bounded by its size)."""
    backup_shas = BACKUP_SHAS if backup_shas is None else backup_shas
    report = json.loads((path.parent/"backup-report.json").read_text())
    if (report.get("status") != "VERIFIED_READ_ONLY_CARD_BACKUP" or
            report.get("sha256") not in backup_shas or report.get("bytes") != expected_size or
            path.stat().st_size != expected_size or path.stat().st_mode & 0o222):
        raise ValueError("pinned read-only verified full-card backup required")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while b := f.read(8*BLOCK):
            digest.update(b)
        if digest.hexdigest() != report["sha256"]:
            raise ValueError("full backup hash mismatch")
        offset, _ = gid_extent(sector_reader(f), pinned, expected_size)
        f.seek(offset)
        stock = read_exact(f,FILE_LEN)
    if sha(stock) != OUTER_SHA:
        raise ValueError("backup does not contain the pinned stock GID")
    return stock,report["sha256"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--device", help="whole removable diskN; owner only")
    target.add_argument("--image", type=Path, help="read-only offline preflight; never accepts --apply")
    ap.add_argument("--backup",type=Path,required=True)
    ap.add_argument("--build",type=Path,required=True,help="pinned English GID, or pinned stock GID to roll back")
    ap.add_argument("--work-root",type=Path,required=True,help="$NISSAN_ROOT/work (default ~/nissan/work)")
    ap.add_argument("--pins",type=Path,help="other owners: JSON with your card_bytes, backup_sha256 and builds")
    ap.add_argument("--apply",action="store_true",help="OWNER ONLY; default is read-only")
    args = ap.parse_args()
    try:
        if args.apply and args.image:
            raise ValueError("--apply is forbidden for images")
        if args.device and not re.fullmatch(r"disk[0-9]+",args.device):
            raise ValueError("expected whole disk identifier diskN")
        work,backup,buildpath = (p.expanduser().resolve() for p in (args.work_root,args.backup,args.build))
        if (work != WORK.resolve() or not work.is_dir() or
                not backup.is_relative_to(work) or not buildpath.is_relative_to(work)):
            raise ValueError(f"backup/build/receipts must remain under {WORK}")
        pins = load_pins(args.pins) if args.pins else None
        pinned = pins is None
        size = SIZE if pinned else pins["card_bytes"]
        builds = BUILDS if pinned else {**BUILDS, **pins.get("builds", {})}
        build = buildpath.read_bytes()
        if sha(build) not in {OUTER_SHA,*builds}:
            raise ValueError("payload hash is not pinned; no generated voice build has been pinned after voice selection")
        stock,backup_sha = verified_backup(backup, size, None if pinned else set(pins["backup_sha256"]), pinned)
        bc = backup_card()
        source = Path("/dev/r"+args.device) if args.device else args.image.expanduser().resolve()
        if args.image and (not source.is_file() or source.stat().st_size != size):
            raise ValueError("offline image must be a full-size ordinary file")
        def identify():
            # The resolved GID extent is part of the identity, so any relocation
            # between preflight and write refuses.
            identity = bc.identify(args.device, expect_bytes=size) if args.device else {"offline_image": str(source)}
            with source.open("rb",buffering=0) as f:
                extent = gid_extent(sector_reader(f), pinned, size)
            return dict(identity, gid_extent=list(extent))
        identity = identify()
        offset = identity["gid_extent"][0]
        with source.open("rb",buffering=0) as f:
            original,payload,label = preflight(sector_reader(f),stock,build,builds,pinned,size)
        if identify() != identity:
            raise ValueError("device identity changed during preflight")
        first,last = write_window(original,payload)
        info = {"file_offset": offset,"file_bytes": FILE_LEN,"sector_envelope_bytes": SPAN,
                "unchanged_tail_bytes": SPAN-FILE_LEN,"live":label,"build_sha256":sha(build),
                "live_file_sha256":sha(original[:FILE_LEN]),"backup_sha256":backup_sha,
                "write_offset":offset+first,"write_bytes":last-first,
                "scope":"welcome clips 764–819 plus allowlisted EV alert clips; FAT/directories/other audio unchanged"}
        if not args.apply:
            print(json.dumps(dict(info,status="READ_ONLY_PREFLIGHT_PASSED"),indent=2))
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        out = work/RECEIPT_PATHS.get(sha(build), "language-speech/en-greeting/writes")/stamp
        def verify(part):
            expected = payload if part == payload[first:last] else original
            with source.open("rb",buffering=0) as f:
                if sector_reader(f)(offset,SPAN) != expected:
                    raise OSError("full GID/tail read-back mismatch")
        report = apply_range(source,offset+first,original[first:last],payload[first:last],
                             identity,identify,out,info,verify=verify)
        print(json.dumps(report,indent=2))
    except (OSError,ValueError,struct.error,subprocess.CalledProcessError) as e:
        ap.exit(1,f"GID write/preflight refused or failed: {e}\n")


if __name__ == "__main__":
    main()
