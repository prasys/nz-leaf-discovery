#!/usr/bin/env python3
"""Decode the Clarion "MTLD" slot / "MTCP" container (G214JLNI.066, LEAF HMI ROM).

Format (reverse engineered from the card image; see
``~/nissan/work/mtcp/decoder-report.txt`` for the evidence trail):

MTLD slot descriptor -- one 512-byte sector at ``slot_lba`` (default 157696):

    +0x70  "MTLD" magic
    +0x74  u32   entry count (2 for this slot)
    +0x78  u32   unknown checksum (left undecoded -- not SUM4/CRC32/adler32
                 of part A, part B or the combined output)
    +0x90  entry 0, +0xb0 entry 1, ...  (32 bytes each)

MTLD entry (32 bytes)::

    +0x00 u32 sectorStart    ; offset from slot data start, in 512-byte sectors
    +0x04 u32 sectorCount    ; stored span, in 512-byte sectors
    +0x08 u32 storedBytes    ; real bytes stored (<= sectorCount*512)
    +0x0c u32 SUM4           ; checksum over stored data, sector padded
    +0x10 u32 magic          ; b"MTCP" if the part is compressed, 0 if raw
    +0x14 u32 outputOffset   ; offset in the decoded combined image
    +0x18 u32 0
    +0x1c u32 0

Part A is an ``MTCP`` container (the slot data starts at sector ``slot_lba+1``)::

    +0x00 "MTCP"
    +0x04 u32 count          ; number of chunks (11)
    +0x08 u32 chunkSize      ; full uncompressed chunk size (0x200000)
    +0x0c 20 zero bytes
    +0x20 32-byte table entry * count

MTCP table entry (32 bytes)::

    +0x00 u32 sectorCount    ; stored span in 512-byte sectors
    +0x04 u32 unpackedSize   ; decompressed length
    +0x08 u32 packedSize     ; LZ4 block length (<= sectorCount*512)
    +0x0c u32 SUM4           ; checksum over sector-padded packed data
    +0x10 16 zero bytes

Packed data starts at absolute offset 512 of the container and each chunk is
padded with zeroes to ``sectorCount*512``.  Each chunk is a raw LZ4 *block*
(no LZ4 frame wrapper).  ``SUM4`` is the sum of little-endian u32 words over
the (zero-padded) packed bytes, modulo 2**32.

Part B is raw (uncompressed) data and is appended at entry-B ``outputOffset``.

Everything is read-only.  The source image/file is never opened for writing,
and output paths that alias a source (symlink or hardlink), the sdcard
directory, or the git checkout are refused.

Run with ``python3 -I tools/mtcp/mtcp.py``.
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile

SECTOR = 512
MTCP_MAGIC = b"MTCP"
MTLD_MAGIC = b"MTLD"
SLOT_SUM4_MAGIC = b"SUM4"
SLOT_END_MAGIC = b"NKOK"

DEFAULT_SLOT_LBA = 157696
DEFAULT_IMG = os.path.expanduser("~/nissan/sdcard/nissan-sd-485-1972-00.img")
DEFAULT_CARVE = os.path.expanduser(
    "~/nissan/work/raw-areas/slot157696_G214JLNI.066_MTCP.bin"
)
DEFAULT_OUTDIR = os.path.expanduser("~/nissan/work/mtcp")
DEFAULT_REFERENCE = os.path.expanduser("~/nissan/work/mtcp/reference-lz4.bin")
DEFAULT_SDCARD_DIR = os.path.expanduser("~/nissan/sdcard")

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Bounds chosen to reject corrupt/hostile headers without rejecting real data.
MAX_COUNT = 4096
MAX_CHUNK_OUTPUT = 16 << 20
MAX_PART_OUTPUT = 128 << 20


class MTCPError(Exception):
    """Raised for a malformed container, bad checksum or unsafe output path."""


class LZ4Error(ValueError):
    """Raised when a raw LZ4 block is malformed or would overrun its bound."""


# --------------------------------------------------------------------------
# checksum


def sum4(data):
    """SUM4: sum of little-endian u32 words, modulo 2**32.

    Trailing bytes (if the buffer is not a multiple of four) are zero padded.
    Upstream the checksum is always taken over sector-padded data, so callers
    normally pass an already padded buffer; padding here is just defensive.
    """
    rem = len(data) & 3
    if rem:
        data = data + b"\x00" * (4 - rem)
    total = 0
    for (word,) in struct.iter_unpack("<I", data):
        total += word
    return total & 0xFFFFFFFF


# --------------------------------------------------------------------------
# raw LZ4 block decoder (LZ4 block format, *not* the LZ4 frame format)


def lz4_block_decode(src, max_output):
    """Decode one raw LZ4 block, bounded to ``max_output`` bytes.

    Implements the standard LZ4 block sequence:

        token            high nibble = literal length, low nibble = match len-4
        [lit len ext]    if literal length == 15, add 0xff-terminated bytes
        literals
        offset           2 bytes little endian            (absent on last seq)
        [match len ext]  if match len nibble == 15, add 0xff-terminated bytes
        match copy       match length = low nibble + 4; may overlap output

    The final sequence contains literals only (the input runs out after them).
    Every access is bounds checked; malformed input raises ``LZ4Error``.
    """
    if max_output < 0:
        raise ValueError("max_output must be non-negative")

    out = bytearray()
    i = 0
    n = len(src)

    while i < n:
        token = src[i]
        i += 1

        # literal length
        lit = token >> 4
        if lit == 15:
            while True:
                if i >= n:
                    raise LZ4Error("truncated literal-length extension")
                b = src[i]
                i += 1
                lit += b
                if b != 0xFF:
                    break

        if i + lit > n:
            raise LZ4Error(
                "literal run (%d bytes) exceeds remaining input (%d)"
                % (lit, n - i)
            )
        if len(out) + lit > max_output:
            raise LZ4Error(
                "literal run would exceed output bound %d" % max_output
            )
        out += src[i : i + lit]
        i += lit

        # End of block: the last sequence has no offset/match.
        if i >= n:
            break

        # match offset
        if i + 2 > n:
            raise LZ4Error("truncated match offset")
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise LZ4Error("zero match offset")
        if offset > len(out):
            raise LZ4Error(
                "match offset %d beyond output length %d" % (offset, len(out))
            )

        # match length
        mlen = (token & 0x0F) + 4
        if (token & 0x0F) == 15:
            while True:
                if i >= n:
                    raise LZ4Error("truncated match-length extension")
                b = src[i]
                i += 1
                mlen += b
                if b != 0xFF:
                    break

        if len(out) + mlen > max_output:
            raise LZ4Error(
                "match would push output past bound %d (%d + %d)"
                % (max_output, len(out), mlen)
            )

        # Copy the match.  LZ4 allows the match to overlap the bytes being
        # written, so copy in doubling slices: the number of bytes available
        # from `start` begins at `offset` and grows as the output grows.
        start = len(out) - offset
        remaining = mlen
        while remaining:
            take = len(out) - start
            if take > remaining:
                take = remaining
            out += out[start : start + take]
            remaining -= take

    return bytes(out)


# --------------------------------------------------------------------------
# container parsing


def _u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def parse_mtcp(data):
    """Parse the ``MTCP`` container header/table.  Bounds checked."""
    if len(data) < SECTOR:
        raise MTCPError(
            "MTCP container too small: %d bytes (need at least one %d-byte sector)"
            % (len(data), SECTOR)
        )
    if data[:4] != MTCP_MAGIC:
        raise MTCPError("bad MTCP magic: %r" % data[:4])

    count = _u32(data, 4)
    chunk_size = _u32(data, 8)

    if not 1 <= count <= MAX_COUNT:
        raise MTCPError("MTCP count %d outside 1..%d" % (count, MAX_COUNT))
    if not 1 <= chunk_size <= MAX_CHUNK_OUTPUT:
        raise MTCPError("implausible chunk size 0x%x" % chunk_size)

    table_end = 0x20 + count * 0x20
    if table_end > SECTOR:
        raise MTCPError(
            "MTCP table ends at 0x%x, past the one-sector header (0x%x)"
            % (table_end, SECTOR)
        )

    entries = []
    for index in range(count):
        off = 0x20 + index * 0x20
        sector_count, unpacked_size, packed_size, stored_sum4 = struct.unpack_from(
            "<IIII", data, off
        )
        if sector_count == 0:
            raise MTCPError("chunk %d has zero sectorCount" % index)
        if unpacked_size == 0:
            raise MTCPError("chunk %d has zero unpackedSize" % index)
        if unpacked_size > chunk_size:
            raise MTCPError(
                "chunk %d unpackedSize 0x%x exceeds chunkSize 0x%x"
                % (index, unpacked_size, chunk_size)
            )
        if packed_size == 0:
            raise MTCPError("chunk %d has zero packedSize" % index)
        span = sector_count * SECTOR
        if packed_size > span:
            raise MTCPError(
                "chunk %d packedSize 0x%x exceeds sector span 0x%x"
                % (index, packed_size, span)
            )
        if index < count - 1 and unpacked_size != chunk_size:
            raise MTCPError(
                "chunk %d unpackedSize 0x%x != chunkSize 0x%x (only the last "
                "chunk may be short)" % (index, unpacked_size, chunk_size)
            )
        entries.append(
            {
                "index": index,
                "tableOffset": off,
                "sectorCount": sector_count,
                "unpackedSize": unpacked_size,
                "packedSize": packed_size,
                "sum4Stored": stored_sum4,
            }
        )

    # Packed chunks are stored contiguously from absolute offset 512.
    storage = SECTOR
    unpacked_total = 0
    for entry in entries:
        entry["storageOffset"] = storage
        entry["storedSpan"] = entry["sectorCount"] * SECTOR
        storage += entry["storedSpan"]
        unpacked_total += entry["unpackedSize"]

    if unpacked_total > MAX_PART_OUTPUT:
        raise MTCPError(
            "declared unpacked total 0x%x exceeds sanity bound 0x%x"
            % (unpacked_total, MAX_PART_OUTPUT)
        )

    return {
        "magic": MTCP_MAGIC.decode("ascii"),
        "count": count,
        "chunkSize": chunk_size,
        "packedStart": SECTOR,
        "packedEnd": storage,
        "unpackedTotal": unpacked_total,
        "table": entries,
    }


def decode_part_a(data, info):
    """Verify SUM4, decode every chunk and return (bytes, reports)."""
    if info["packedEnd"] > len(data):
        raise MTCPError(
            "declared packed data ends at 0x%x but container is only 0x%x bytes"
            % (info["packedEnd"], len(data))
        )

    out = bytearray()
    reports = []
    for entry in info["table"]:
        index = entry["index"]
        start = entry["storageOffset"]
        span = entry["storedSpan"]
        if start + span > len(data):
            raise MTCPError(
                "chunk %d storage [0x%x,0x%x) past container end 0x%x"
                % (index, start, start + span, len(data))
            )

        block = data[start : start + span]
        packed = block[: entry["packedSize"]]
        # Include actual stored padding, rather than substituting zeroes.
        computed_sum4 = sum4(block)
        if computed_sum4 != entry["sum4Stored"]:
            raise MTCPError(
                "chunk %d SUM4 mismatch: stored 0x%08x computed 0x%08x"
                % (index, entry["sum4Stored"], computed_sum4)
            )

        try:
            decoded = lz4_block_decode(packed, entry["unpackedSize"])
        except LZ4Error as exc:
            raise MTCPError("chunk %d LZ4 error: %s" % (index, exc)) from exc

        if len(decoded) != entry["unpackedSize"]:
            raise MTCPError(
                "chunk %d length mismatch: decoded 0x%x, expected 0x%x"
                % (index, len(decoded), entry["unpackedSize"])
            )

        out += decoded
        reports.append(
            {
                **entry,
                "index": index,
                "sectorCount": entry["sectorCount"],
                "unpackedSize": entry["unpackedSize"],
                "packedSize": entry["packedSize"],
                "sum4Stored": "0x%08x" % entry["sum4Stored"],
                "sum4Computed": "0x%08x" % computed_sum4,
                "sum4Ok": True,
                "lz4Ok": True,
                "lengthOk": True,
                "sha256": hashlib.sha256(decoded).hexdigest(),
            }
        )

    return bytes(out), reports


def parse_mtld_sector(sector, slot_lba):
    """Parse the MTLD descriptor embedded in a slot-header sector."""
    if len(sector) < SECTOR:
        raise MTCPError("short slot-header sector: %d bytes" % len(sector))
    if sector[0x70:0x74] != MTLD_MAGIC:
        raise MTCPError(
            "no MTLD magic at +0x70 of LBA %d sector (got %r)"
            % (slot_lba, sector[0x70:0x74])
        )

    count = _u32(sector, 0x74)
    unknown_checksum = _u32(sector, 0x78)
    if count != 2:
        raise MTCPError("this decoder requires exactly two MTLD parts")

    entries = []
    for index in range(count):
        off = 0x90 + index * 0x20
        if off + 0x20 > SECTOR:
            raise MTCPError("MTLD entry %d runs past the sector" % index)
        sector_start, sector_count, stored_bytes, stored_sum4 = struct.unpack_from(
            "<IIII", sector, off
        )
        magic_word, output_offset, reserved0, reserved1 = struct.unpack_from(
            "<IIII", sector, off + 0x10
        )
        if sector_count == 0:
            raise MTCPError("MTLD entry %d has zero sectorCount" % index)
        span = sector_count * SECTOR
        if stored_bytes == 0 or stored_bytes > span:
            raise MTCPError(
                "MTLD entry %d storedBytes 0x%x outside 1..0x%x"
                % (index, stored_bytes, span)
            )
        if span > MAX_PART_OUTPUT:
            raise MTCPError("MTLD part exceeds supported storage bound")
        entries.append(
            {
                "index": index,
                "sectorStart": sector_start,
                "sectorCount": sector_count,
                "storedBytes": stored_bytes,
                "sum4Stored": stored_sum4,
                "magic": (
                    magic_word.to_bytes(4, "little").decode("ascii", "replace")
                    if magic_word
                    else None
                ),
                "magicWord": magic_word,
                "outputOffset": output_offset,
                "reserved": [reserved0, reserved1],
            }
        )

    return {
        "slotLba": slot_lba,
        "magic": MTLD_MAGIC.decode("ascii"),
        "count": count,
        "unknownChecksum": "0x%08x" % unknown_checksum,
        "entries": entries,
    }


# --------------------------------------------------------------------------
# source handling


def _read_file(path):
    if os.path.getsize(path) > MAX_PART_OUTPUT:
        raise MTCPError("input file exceeds supported size bound: %s" % path)
    with open(path, "rb") as handle:
        return handle.read()


def read_mtld_descriptor(image_path, slot_lba):
    """Read and parse the MTLD descriptor sector from a card image."""
    if slot_lba < 0:
        raise MTCPError("slot LBA must be non-negative")
    image_size = os.path.getsize(image_path)
    if (slot_lba + 1) * SECTOR > image_size:
        raise MTCPError(
            "MTLD sector LBA %d past image end (0x%x bytes)"
            % (slot_lba, image_size)
        )
    with open(image_path, "rb") as image:
        image.seek(slot_lba * SECTOR)
        sector = image.read(SECTOR)
    return parse_mtld_sector(sector, slot_lba)


def load_from_card(image_path, slot_lba):
    """Read the MTLD descriptor and both stored parts from the card image."""
    image_size = os.path.getsize(image_path)
    slot_data_offset = (slot_lba + 1) * SECTOR
    if slot_data_offset > image_size:
        raise MTCPError(
            "slot data offset 0x%x past image end 0x%x"
            % (slot_data_offset, image_size)
        )

    descriptor = read_mtld_descriptor(image_path, slot_lba)

    parts = []
    with open(image_path, "rb") as image:
        for entry in descriptor["entries"]:
            start = slot_data_offset + entry["sectorStart"] * SECTOR
            length = entry["storedBytes"]
            if start + length > image_size:
                raise MTCPError(
                    "MTLD entry %d [0x%x,0x%x) past image end 0x%x"
                    % (
                        entry["index"],
                        start,
                        start + length,
                        image_size,
                    )
                )
            image.seek(start)
            parts.append(image.read(length))

    return descriptor, parts


def load_from_mtcp_file(path):
    """Read a carved MTCP file; split part A (container) from raw part B."""
    data = _read_file(path)
    if len(data) < SECTOR:
        raise MTCPError("MTCP file too small: %d bytes" % len(data))
    # Parse just enough of the header to learn where the packed data ends.
    probe = parse_mtcp(data)
    part_a = data[: probe["packedEnd"]]
    part_b = data[probe["packedEnd"] :]
    return part_a, part_b, probe["packedEnd"]


# --------------------------------------------------------------------------
# output safety


def _is_within(path, directory):
    path = os.path.realpath(path)
    directory = os.path.realpath(directory)
    return path == directory or path.startswith(directory + os.sep)


def guard_outputs(outputs, sources, protected_dirs, force):
    """Refuse source aliases, protected directories and accidental overwrite."""
    seen = set()
    for name, path in outputs.items():
        real = os.path.realpath(path)
        if real in seen:
            raise MTCPError("output paths alias each other")
        seen.add(real)
        if os.path.islink(path):
            raise MTCPError("refusing symlink output: %s" % path)
        if os.path.exists(path) and os.stat(path).st_nlink > 1:
            raise MTCPError("refusing multiply-linked output: %s" % path)

        for source in sources:
            if not source:
                continue
            if real == os.path.realpath(source):
                raise MTCPError(
                    "output %s aliases source %s; refusing to overwrite"
                    % (name, source)
                )
            if os.path.exists(path) and os.path.exists(source):
                try:
                    if os.path.samefile(path, source):
                        raise MTCPError(
                            "output %s is a hardlink to source %s; refusing"
                            % (name, source)
                        )
                except OSError:
                    pass

        for directory in protected_dirs:
            if directory and _is_within(path, directory):
                raise MTCPError(
                    "refusing to write %s under protected directory %s"
                    % (name, directory)
                )

        if os.path.exists(path) and not force:
            raise MTCPError(
                "output already exists: %s (pass --force to overwrite)" % path
            )


def write_bytes(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
            temporary = handle.name
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


# --------------------------------------------------------------------------
# reporting


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def build_metadata(args, source_kind, source_path, descriptor, info, chunk_reports,
                   part_a, part_b, part_b_offset, part_b_stored_sum4, combined,
                   output_info, reference, part_a_stored_sum4, part_b_sum4):
    return {
        "tool": "tools/mtcp/mtcp.py",
        "format": "MTLD/MTCP (raw LZ4 blocks)",
        "source": {
            "kind": source_kind,
            "path": os.path.abspath(source_path),
            "slotLba": args.slot_lba,
        },
        "mtld": descriptor,
        "mtcp": {
            "magic": info["magic"],
            "count": info["count"],
            "chunkSize": info["chunkSize"],
            "packedStart": info["packedStart"],
            "packedEnd": info["packedEnd"],
            "unpackedTotal": info["unpackedTotal"],
            "table": chunk_reports,
            "sum4": {
                "partAStored": "0x%08x" % part_a_stored_sum4,
                "partB": "0x%08x" % part_b_sum4,
            },
        },
        "parts": {
            "a": {
                "storedSize": info["packedEnd"],
                "decodedSize": len(part_a),
                "sha256": sha256_bytes(part_a),
            },
            "b": {
                "storedOffset": info["packedEnd"],
                "romOffset": part_b_offset,
                "size": len(part_b),
                "sum4Stored": (
                    "0x%08x" % part_b_stored_sum4
                    if part_b_stored_sum4 is not None
                    else None
                ),
                "sum4Computed": "0x%08x" % part_b_sum4,
                "sum4Ok": (
                    part_b_stored_sum4 == part_b_sum4
                    if part_b_stored_sum4 is not None
                    else None
                ),
                "sha256": sha256_bytes(part_b),
            },
            "combined": {
                "size": len(combined),
                "sha256": sha256_bytes(combined),
            },
        },
        "outputs": output_info,
        "reference": reference,
    }


def print_summary(descriptor, info, chunk_reports, part_a, part_b, combined,
                  reference, output_info):
    print("MTCP: count=%d chunkSize=0x%x packed=[0x%x,0x%x) unpacked=0x%x"
          % (info["count"], info["chunkSize"], info["packedStart"],
             info["packedEnd"], info["unpackedTotal"]))
    print("  idx  sectors  packed     unpacked    SUM4       sha256")
    for report in chunk_reports:
        print("  %3d  %7d  0x%-8x 0x%-8x %s %s"
              % (report["index"], report["sectorCount"], report["packedSize"],
                 report["unpackedSize"], report["sum4Stored"],
                 report["sha256"][:16]))
    print("part A: %d bytes  sha256=%s" % (len(part_a), sha256_bytes(part_a)))
    print("part B: %d bytes  sha256=%s" % (len(part_b), sha256_bytes(part_b)))
    print("combined: %d bytes (0x%x)  sha256=%s"
          % (len(combined), len(combined), sha256_bytes(combined)))
    if reference is not None:
        print("reference: %s" % ("MATCH" if reference["match"] else "MISMATCH"))
    if output_info:
        print("outputs:")
        for name, entry in output_info.items():
            print("  %-16s %12d bytes  sha256=%s"
                  % (name, entry["size"], entry["sha256"][:16]))


# --------------------------------------------------------------------------
# main


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Decode the MTLD/MTCP LZ4-compressed G214JLNI.066 ROM.",
    )
    parser.add_argument(
        "--card-image",
        help="card image to read the MTLD descriptor and data from "
             "(default: $NISSAN_IMG or %s if it exists)" % DEFAULT_IMG,
    )
    parser.add_argument(
        "--mtcp-file",
        help="carved MTCP container file (default: %s if it exists)"
             % DEFAULT_CARVE,
    )
    parser.add_argument(
        "--slot-lba",
        type=lambda value: int(value, 0),
        default=DEFAULT_SLOT_LBA,
        help="LBA of the MTLD descriptor sector (default: %d)" % DEFAULT_SLOT_LBA,
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUTDIR,
        help="output directory (default: %s)" % DEFAULT_OUTDIR,
    )
    parser.add_argument(
        "--reference",
        help="combined-output reference file to compare against "
             "(default: %s if it exists)" % DEFAULT_REFERENCE,
    )
    parser.add_argument(
        "--no-card-image",
        action="store_true",
        help="do not auto-detect a card image for descriptor validation",
    )
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="skip the reference comparison",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="parse, verify and print, but write no output files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing output files (never overwrites a source)",
    )
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.slot_lba < 0:
        raise MTCPError("slot LBA must be non-negative")

    # Resolve the optional card image (used for descriptor parsing/validation).
    if args.no_card_image:
        card_image = None
    elif args.card_image:
        if not os.path.isfile(args.card_image):
            parser.error("card image not found: %s" % args.card_image)
        card_image = args.card_image
    else:
        candidate = os.environ.get("NISSAN_IMG") or DEFAULT_IMG
        card_image = candidate if os.path.isfile(candidate) else None

    # Choose the data source.  An explicit --mtcp-file / --card-image wins;
    # otherwise prefer the carved MTCP file, then the card image.
    if args.mtcp_file:
        source_kind, source_path = "mtcp-file", args.mtcp_file
    elif args.card_image:
        source_kind, source_path = "card-image", args.card_image
    elif os.path.isfile(DEFAULT_CARVE):
        source_kind, source_path = "mtcp-file", DEFAULT_CARVE
    elif card_image:
        source_kind, source_path = "card-image", card_image
    else:
        raise MTCPError(
            "no source found; pass --card-image or --mtcp-file (looked for %s "
            "and %s)" % (DEFAULT_CARVE, DEFAULT_IMG)
        )

    if not os.path.isfile(source_path):
        raise MTCPError("source not found: %s" % source_path)

    descriptor = None
    part_b_stored_sum4 = None
    part_b_offset = None

    if source_kind == "card-image":
        descriptor, parts = load_from_card(source_path, args.slot_lba)
        part_a_stored = parts[0]
        # MTLD entry 0 is the MTCP container; entry 1 is raw part B.
        if len(parts) >= 2:
            part_b_raw = parts[1]
            part_b_stored_sum4 = descriptor["entries"][1]["sum4Stored"]
            part_b_offset = descriptor["entries"][1]["outputOffset"]
        else:
            part_b_raw = b""
        info = parse_mtcp(part_a_stored)
        part_a, chunk_reports = decode_part_a(part_a_stored, info)
        if part_b_offset is None:
            part_b_offset = info["unpackedTotal"]
    else:
        part_a_stored, part_b_raw, _packed_end = load_from_mtcp_file(source_path)
        info = parse_mtcp(part_a_stored)
        part_a, chunk_reports = decode_part_a(part_a_stored, info)
        part_b_offset = info["unpackedTotal"]
        # When a card image is also available, cross-check against its MTLD.
        if card_image and os.path.isfile(card_image):
            descriptor = read_mtld_descriptor(card_image, args.slot_lba)
            part_b_stored_sum4 = descriptor["entries"][1]["sum4Stored"]
            part_b_offset = descriptor["entries"][1]["outputOffset"]

    part_b = part_b_raw

    # Stored-data checksums (part A is over the compressed bytes, part B raw).
    part_a_stored_sum4 = sum4(part_a_stored)
    part_b_sum4 = sum4(part_b)

    # Descriptor cross-checks when we have one.
    if descriptor:
        if descriptor["count"] < 2:
            raise MTCPError("MTLD descriptor has fewer than two entries")
        entry_a = descriptor["entries"][0]
        entry_b = descriptor["entries"][1]
        if entry_a["sectorStart"] != 0 or entry_a["outputOffset"] != 0:
            raise MTCPError("MTLD part A must start at container/ROM offset zero")
        if entry_a["storedBytes"] != entry_a["sectorCount"] * SECTOR:
            raise MTCPError("unsupported partial-sector MTLD part A")
        if entry_b["sectorStart"] * SECTOR != info["packedEnd"]:
            raise MTCPError("MTLD part B is not contiguous with part A")
        if entry_b["magicWord"] != 0:
            raise MTCPError("MTLD part B is not raw data")
        if entry_b["storedBytes"] != len(part_b):
            raise MTCPError("MTLD part B length disagrees with source")
        if entry_b["storedBytes"] != entry_b["sectorCount"] * SECTOR:
            raise MTCPError("unsupported partial-sector MTLD part B")
        if entry_a["magicWord"] != struct.unpack("<I", MTCP_MAGIC)[0]:
            raise MTCPError(
                "MTLD entry A magic is %r, expected MTCP"
                % entry_a["magic"]
            )
        if entry_a["storedBytes"] != info["packedEnd"]:
            raise MTCPError(
                "MTLD entry A storedBytes 0x%x != MTCP packedEnd 0x%x"
                % (entry_a["storedBytes"], info["packedEnd"])
            )
        if part_a_stored_sum4 != entry_a["sum4Stored"]:
            raise MTCPError(
                "MTLD entry A SUM4 mismatch: stored 0x%08x computed 0x%08x"
                % (entry_a["sum4Stored"], part_a_stored_sum4)
            )
        if part_b_stored_sum4 is not None and part_b_sum4 != part_b_stored_sum4:
            raise MTCPError(
                "MTLD entry B SUM4 mismatch: stored 0x%08x computed 0x%08x"
                % (part_b_stored_sum4, part_b_sum4)
            )

    if part_b_offset != info["unpackedTotal"]:
        raise MTCPError(
            "part B output offset 0x%x != part A unpacked total 0x%x"
            % (part_b_offset, info["unpackedTotal"])
        )

    combined = part_a + part_b
    if len(combined) > MAX_PART_OUTPUT:
        raise MTCPError("combined output too large: %d" % len(combined))

    # Reference comparison.
    reference = None
    reference_path = None
    if not args.no_reference:
        reference_path = args.reference
        if not reference_path:
            if os.path.isfile(DEFAULT_REFERENCE):
                reference_path = DEFAULT_REFERENCE
        if reference_path and os.path.isfile(reference_path):
            expected = _read_file(reference_path)
            reference = {
                "path": os.path.abspath(reference_path),
                "size": len(expected),
                "sha256": sha256_bytes(expected),
                "match": expected == combined,
            }
        elif args.reference:
            raise MTCPError("reference file not found: %s" % args.reference)
    if reference is not None and not reference["match"]:
        raise MTCPError("combined output does not match the reference file")

    # Build outputs and guard them before writing anything.
    out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
    output_paths = {
        "part-a.bin": os.path.join(out_dir, "part-a.bin"),
        "part-b.bin": os.path.join(out_dir, "part-b.bin"),
        "g214-rom.bin": os.path.join(out_dir, "g214-rom.bin"),
        "metadata.json": os.path.join(out_dir, "metadata.json"),
    }

    protected = {REPO_ROOT, DEFAULT_SDCARD_DIR}
    if source_kind == "card-image":
        protected.add(os.path.dirname(os.path.abspath(source_path)))
    if card_image:
        protected.add(os.path.dirname(os.path.abspath(card_image)))

    sources = [source_path]
    if card_image and os.path.abspath(card_image) != os.path.abspath(source_path):
        sources.append(card_image)
    if reference_path:
        sources.append(reference_path)

    if not args.info:
        guard_outputs(output_paths, sources, protected, args.force)
        os.makedirs(out_dir, exist_ok=True)

    output_info = {}
    if not args.info:
        part_a_path = output_paths["part-a.bin"]
        part_b_path = output_paths["part-b.bin"]
        rom_path = output_paths["g214-rom.bin"]
        write_bytes(part_a_path, part_a)
        write_bytes(part_b_path, part_b)
        write_bytes(rom_path, combined)

        for name, path, data in (
            ("part-a.bin", part_a_path, part_a),
            ("part-b.bin", part_b_path, part_b),
            ("g214-rom.bin", rom_path, combined),
        ):
            output_info[name] = {
                "path": os.path.abspath(path),
                "size": len(data),
                "sha256": sha256_bytes(data),
            }

    metadata = build_metadata(
        args, source_kind, source_path, descriptor, info, chunk_reports,
        part_a, part_b, part_b_offset, part_b_stored_sum4, combined,
        output_info, reference, part_a_stored_sum4, part_b_sum4,
    )

    if not args.info:
        meta_path = output_paths["metadata.json"]
        write_bytes(
            meta_path,
            (json.dumps(metadata, indent=2, sort_keys=False) + "\n").encode("utf-8"),
        )
        output_info["metadata.json"] = {
            "path": os.path.abspath(meta_path),
            "size": os.path.getsize(meta_path),
            "sha256": sha256_bytes(_read_file(meta_path)),
        }

    print_summary(
        descriptor, info, chunk_reports, part_a, part_b, combined,
        reference, output_info,
    )

    if reference is not None and not reference["match"]:
        print("ERROR: combined output does not match the reference file",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MTCPError, OSError) as exc:
        print("mtcp: error: %s" % exc, file=sys.stderr)
        sys.exit(2)
