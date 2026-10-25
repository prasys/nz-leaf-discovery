#!/usr/bin/env python3
"""Read-only WinCE ROM inventory and MTCP raw-region characterization.

Run with python3 -I. Prints JSON; does not extract or decompress CE sections.
All offsets are byte offsets; range ends are exclusive.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct


ROMHDR = struct.Struct("<17I2HI2I")
ROM_FIELDS = """dllfirst dlllast physfirst physlast nummods RAMStart RAMFree
RAMEnd CopyEntries CopyOffset ProfileLen ProfileOffset numfiles KernelFlags
FSRamPercent DrivglobStart DrivglobLen CPUType MiscFlags pExtensions
TrackingStart TrackingLen""".split()


def span(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"range outside image: {offset:#x}+{size:#x}")
    return data[offset:offset + size]


def entropy(data):
    if not data:
        return 0.0
    return -sum((n / len(data)) * math.log2(n / len(data))
                for n in Counter(data).values())


def fingerprint(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "first_32_bytes": data[:32].hex(), "entropy_bits_per_byte": entropy(data)}


def coverage(ranges, start, end):
    """Union length, so shared or overlapping section storage is counted once."""
    clipped = sorted((max(a, start), min(b, end)) for a, b in ranges
                     if a < end and b > start)
    total, cursor = 0, start
    for a, b in clipped:
        total += max(0, b - max(a, cursor))
        cursor = max(cursor, b)
    return total


def inventory(data):
    if span(data, 0x40, 4) != b"ECEC":
        raise ValueError("no ECEC signature at ROM offset 0x40")
    va, offset = struct.unpack("<II", span(data, 0x44, 8))
    base = va - offset
    header = dict(zip(ROM_FIELDS, ROMHDR.unpack(span(data, offset, ROMHDR.size))))
    if header["physfirst"] != base or header["physlast"] != base + len(data):
        raise ValueError("ROMHDR physical extent disagrees with image")
    pos = offset + ROMHDR.size
    # The complete TOC must fit before processing names and section pointers.
    span(data, pos, header["nummods"] * 32 + header["numfiles"] * 28)

    def name_at(address):
        p = address - base
        raw = span(data, p, min(256, len(data) - p))
        if b"\0" not in raw:
            raise ValueError("unterminated ROM name")
        name = raw.split(b"\0", 1)[0].decode("ascii")
        if not name or any(ord(c) < 32 or ord(c) > 126 for c in name):
            raise ValueError("invalid ROM name")
        return name, p

    modules = []
    for i in range(header["nummods"]):
        toc = pos + i * 32
        attr, low, high, size, np, ep, op, load = struct.unpack("<8I", span(data, toc, 32))
        name, name_offset = name_at(np)
        count, flags = struct.unpack("<HH", span(data, ep - base, 4))
        section_table = span(data, op - base, count * 24)
        sections = []
        for j, fields in enumerate(struct.iter_unpack("<6I", section_table)):
            vsize, rva, psize, dataptr, realaddr, section_flags = fields
            stored = dataptr - base
            if psize:
                span(data, stored, psize)
            sections.append({"index": j, "o32_offset": op - base + j * 24,
                             "virtual_size": vsize, "rva": rva,
                             "stored_size": psize, "rom_offset": stored,
                             "real_address": realaddr, "flags": section_flags,
                             "ce_compressed": bool(section_flags & 0x2000)})
        modules.append({"name": name, "toc_offset": toc, "name_offset": name_offset,
                        "attributes": attr, "filetime": (high << 32) | low,
                        "file_size": size, "e32_offset": ep - base,
                        "o32_offset": op - base, "load_address": load,
                        "e32_flags": flags, "sections": sections})
    pos += header["nummods"] * 32
    files = []
    for i in range(header["numfiles"]):
        toc = pos + i * 28
        attr, low, high, real, packed, np, address = struct.unpack("<7I", span(data, toc, 28))
        name, name_offset = name_at(np)
        span(data, address - base, packed)
        files.append({"name": name, "toc_offset": toc, "name_offset": name_offset,
                      "attributes": attr, "filetime": (high << 32) | low,
                      "real_size": real, "stored_size": packed,
                      "rom_offset": address - base})
    return {"base_address": base, "romhdr_va": va, "romhdr_offset": offset,
            "romhdr": header, "modules": modules, "files": files}


def characterize(container, rom, info):
    # Coordinates refer to this G214 sample, independently checked by MTLD.
    raw_start, raw_size, expanded_a = 0x93E000, 0x1412400, 0x147FE00
    raw = span(container, raw_start, raw_size)
    if span(rom, expanded_a, raw_size) != raw:
        raise ValueError("ROM part B differs from container part B")
    report = {"raw_part": {"container_offset": raw_start, **fingerprint(raw)},
              "windows": []}
    for start in range(0xC00000, 0x1D00000, 0x100000):
        window = span(container, start, 0x100000)
        report["windows"].append({"container_offset": start, **fingerprint(window)})
    start, end = 0xC00000, 0x1C00000
    rom_start = start - raw_start + expanded_a
    rom_end = end - raw_start + expanded_a
    hits = []
    for module in info["modules"]:
        for section in module["sections"]:
            a = section["rom_offset"]
            b = a + section["stored_size"]
            if a < rom_end and b > rom_start:
                hits.append({"module": module["name"], **section})
    block = span(container, start, end - start)
    # Hits are evidence coordinates only, not a format identification.
    signatures = {"gzip": b"\x1f\x8b\x08", "zip": b"PK\x03\x04",
                  "lz4_frame": b"\x04\x22\x4d\x18", "xz": b"\xfd7zXZ\0",
                  "squashfs": b"hsqs", "png": b"\x89PNG\r\n\x1a\n",
                  "ECEC": b"ECEC"}
    signature_hits = {}
    for label, magic in signatures.items():
        offsets, p = [], 0
        while True:
            p = block.find(magic, p)
            if p < 0:
                break
            offsets.append(start + p)
            p += 1
        signature_hits[label] = offsets
    ranges = [(s["rom_offset"], s["rom_offset"] + s["stored_size"])
              for s in hits if s["ce_compressed"]]
    report["high_entropy_region"] = {
        "container_start": start, "container_end": end,
        "rom_start": rom_start, "rom_end": rom_end, **fingerprint(block),
        "signature_hits": signature_hits, "intersecting_sections": hits,
        "ce_compressed_union_bytes": coverage(ranges, rom_start, rom_end),
        "note": "CE compression flags are metadata evidence; no section decoding or decryption attempted."}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--container", type=Path, help="original carved MTCP file")
    args = parser.parse_args()
    try:
        data = args.rom.expanduser().read_bytes()
        info = inventory(data)
        info["image"] = fingerprint(data)
        if args.container:
            container = args.container.expanduser().read_bytes()
            info["characterization"] = characterize(container, data, info)
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
