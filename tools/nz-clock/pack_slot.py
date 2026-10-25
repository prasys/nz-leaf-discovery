#!/usr/bin/env python3 -I
"""Repack the reviewed offline ROM for ANALYSIS; never opens a card for writing.

Unresolved slot fields +0x14 and +0x78 are preserved and explicitly unverified.
Boot acceptance remains unverified. All known sums and a complete
independent decompression round trip must pass before any output is produced.
Requires the already installed liblz4 with LZ4_compress_HC.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ce-extract"))
import mtcp

ORIGINAL_ROM_SHA = "8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a"
ORIGINAL_PACKED_SHA = "3c90f444fc2a5ab5490ec07d4c8d011763d1bf7f6d2265bc80cfb6e20e41200b"
HEADER_SHA = "c74f77bccca7c601069cb16de877990931065c51bb5d0f8cda9a5c56bac22001"
CANDIDATE_SHA = "5a4d6e640ec723d10e85c32bdaa611b2d4ae6ee384be298c443ddcf7971e4a55"
CANDIDATES = {
    "v2": CANDIDATE_SHA,
    "fixed-nzdt-probe": "7ba3020cf90bb644701989e3e9375c17355374c7531a4b35071635c78fa44b82",
}
SLOT_LBA = 157696
SLOT_BYTES = (217856 - SLOT_LBA) * 512


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sum32(data):
    if len(data) % 4:
        data += b"\0" * (-len(data) % 4)
    return sum(v[0] for v in struct.iter_unpack("<I", data)) & 0xffffffff


def decode(header, payload):
    if len(header) != 512 or header[0x70:0x74] != b"MTLD" or header[0x1fc:] != b"NKOK":
        raise ValueError("Bad slot header")
    length = struct.unpack_from("<I", header)[0]
    if length != len(payload) or struct.unpack_from("<I", header, 0x34)[0] != sum32(payload):
        raise ValueError("Slot length/SUM4 mismatch")
    if header[0x30:0x34] != b"SUM4" or struct.unpack_from("<I", header, 0x74)[0] != 2:
        raise ValueError("Expected SUM4 and two MTLD parts")
    parts = []
    output = bytearray()
    for index in range(2):
        start, sectors, size, check = struct.unpack_from("<4I", header, 0x90 + index * 32)
        if size != sectors * 512 or start * 512 != sum(len(p) for p in parts):
            raise ValueError("Non-contiguous or unaligned MTLD parts")
        part = payload[start * 512:start * 512 + size]
        if len(part) != size or sum32(part) != check:
            raise ValueError("MTLD part sum/length mismatch")
        if struct.unpack_from("<I", header, 0xa4 + index * 32)[0] != len(output):
            raise ValueError("MTLD output offset mismatch")
        parts.append(part)
        if index == 0:
            for raw, (k, pos, secs, usize, csize, stored) in mtcp.unpack(part):
                if sum32(part[pos:pos + secs * 512]) != stored:
                    raise ValueError("MTCP chunk sum mismatch")
                output.extend(raw)
            if mtcp.unpack.end != len(part):
                raise ValueError("Unexpected bytes after MTCP chunks")
        else:
            output.extend(part)
    if sum(map(len, parts)) != len(payload):
        raise ValueError("Bytes outside declared MTLD parts")
    return bytes(output)


def compressor():
    path = ctypes.util.find_library("lz4") or "/opt/homebrew/opt/lz4/lib/liblz4.dylib"
    lib = ctypes.CDLL(path)
    lib.LZ4_compressBound.argtypes = [ctypes.c_int]
    lib.LZ4_compressBound.restype = ctypes.c_int
    lib.LZ4_compress_HC.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.LZ4_compress_HC.restype = ctypes.c_int
    def compress(data):
        source = ctypes.create_string_buffer(data)
        capacity = lib.LZ4_compressBound(len(data))
        target = ctypes.create_string_buffer(capacity)
        size = lib.LZ4_compress_HC(source, target, len(data), capacity, 12)
        if size <= 0:
            raise ValueError("LZ4 HC compression failed")
        return target.raw[:size]
    return compress


def pack(header, original, candidate, variant="v2"):
    if (variant not in CANDIDATES or sha(header) != HEADER_SHA or
            sha(original) != ORIGINAL_PACKED_SHA or sha(candidate) != CANDIDATES[variant]):
        raise ValueError("Unknown source/header/candidate SHA256")
    baseline = decode(header, original)
    if sha(baseline) != ORIGINAL_ROM_SHA:
        raise ValueError("Untouched source round trip failed")
    compress = compressor()
    chunk_header = bytearray(original[:512])
    chunks = []
    pos = 0
    for index in range(struct.unpack_from("<I", original, 4)[0]):
        raw_size = struct.unpack_from("<I", original, 0x24 + 32 * index)[0]
        raw = candidate[pos:pos + raw_size]
        if len(raw) != raw_size:
            raise ValueError("Candidate too short for original chunk layout")
        packed = compress(raw)
        if mtcp.lz4_block(packed, raw_size) != raw:
            raise ValueError("Independent LZ4 decode differs from input")
        sector_data = packed + b"\0" * (-len(packed) % 512)
        struct.pack_into("<4I", chunk_header, 0x20 + 32 * index,
                         len(sector_data) // 512, raw_size, len(packed), sum32(sector_data))
        chunks.append(sector_data)
        pos += raw_size
    part0 = bytes(chunk_header) + b"".join(chunks)
    part1 = candidate[pos:]
    if len(part1) % 512:
        raise ValueError("Raw tail is not sector aligned")
    payload = part0 + part1
    if len(payload) + 512 > SLOT_BYTES:
        raise ValueError(f"Repacked candidate exceeds G214 slot allocation: {len(payload) + 512} > {SLOT_BYTES}")
    result = bytearray(header)
    struct.pack_into("<2I", result, 0, len(payload), len(payload) // 512)
    struct.pack_into("<I", result, 0x34, sum32(payload))
    struct.pack_into("<4I", result, 0x90, 0, len(part0) // 512, len(part0), sum32(part0))
    struct.pack_into("<4I", result, 0xb0, len(part0) // 512, len(part1) // 512, len(part1), sum32(part1))
    if decode(result, payload) != candidate:
        raise ValueError("Complete packed candidate round trip failed")
    if result[0x14:0x16] != header[0x14:0x16] or result[0x78:0x7c] != header[0x78:0x7c]:
        raise ValueError("Unresolved fields were modified")
    return bytes(result) + payload, {
        "status": "EXPERIMENTAL_PACKED_CANDIDATE_BOOT_ACCEPTANCE_UNVERIFIED",
        "variant": variant,
        "clock_behaviour": "TEMPORARY_FIXED_UTC_PLUS_13_NO_AUTOMATIC_DST" if variant == "fixed-nzdt-probe" else "NZ_AUTOMATIC_DST_CANDIDATE",
        "untouched_roundtrip_sha256": sha(baseline), "candidate_rom_sha256": sha(candidate),
        "slot_bytes": len(payload) + 512, "slot_allocation_bytes": SLOT_BYTES,
        "part0_bytes": len(part0), "part1_bytes": len(part1),
        "known_checks_verified": ["outer SUM4", "both MTLD part sums", "all MTCP chunk sums",
                                  "complete decompression equals candidate ROM"],
        "unverified_fields_preserved": {"slot+0x14": header[0x14:0x16].hex(),
                                        "slot+0x78": header[0x78:0x7c].hex()},
    }


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=root / "sdcard/nissan-sd-485-1972-00.img")
    parser.add_argument("--candidate", type=Path, default=root / "work/nz-clock/candidate-v2/G214-NZ-candidate.nb0")
    parser.add_argument("--variant", choices=sorted(CANDIDATES), default="v2")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        out = args.out.expanduser().resolve()
        work = (root / "work").resolve()
        if not out.is_relative_to(work) or out == work:
            raise ValueError("Output must be a NEW directory under NISSAN_ROOT/work")
        with args.image.expanduser().open("rb") as src:
            src.seek(SLOT_LBA * 512)
            header = src.read(512)
            original = src.read(30737408)
        slot, report = pack(header, original, args.candidate.expanduser().read_bytes(), args.variant)
        out.mkdir(parents=True, exist_ok=False)
        target = out / "G214-NZ-EXPERIMENTAL-slot.bin"
        with target.open("xb") as saved:
            saved.write(slot)
        report["slot_sha256"] = sha(slot)
        (out / "pack-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Pack refused/failed: {error}\n")


if __name__ == "__main__":
    main()
