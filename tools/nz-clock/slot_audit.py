#!/usr/bin/env python3 -I
"""Read-only comparison of G214 slot header fields with packed/unpacked sums."""
import hashlib
import json
import os
from pathlib import Path
import struct
import binascii
import zlib
import argparse


def sum32(data):
    data += b"\0" * (-len(data) % 4)
    return sum(v[0] for v in struct.iter_unpack("<I", data)) & 0xffffffff


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=Path(os.environ.get(
        "NISSAN_IMG", root / "sdcard/nissan-sd-485-1972-00.img")))
    args = parser.parse_args()
    img = args.image.expanduser()
    with img.open("rb") as stream:
        stream.seek(157696 * 512)
        header = stream.read(512)
        if len(header) != 512 or struct.unpack_from("<I", header)[0] != 30737408:
            parser.error("Unexpected or incomplete G214 header")
        packed = stream.read(30737408)
        if len(packed) != 30737408:
            parser.error("Incomplete G214 payload")
    raw = (root / "work/ce-extract/G214JLNI.066.nb0").read_bytes()
    print(json.dumps({
        "header_sha256": hashlib.sha256(header).hexdigest(),
        "packed_sha256": hashlib.sha256(packed).hexdigest(),
        "packed_matches_reviewed_source": hashlib.sha256(packed).hexdigest() ==
            "3c90f444fc2a5ab5490ec07d4c8d011763d1bf7f6d2265bc80cfb6e20e41200b",
        "header_14": hex(struct.unpack_from("<H", header, 0x14)[0]),
        "header_34": hex(struct.unpack_from("<I", header, 0x34)[0]),
        "header_78": hex(struct.unpack_from("<I", header, 0x78)[0]),
        "packed_sum8": hex(sum(packed) & 0xffff), "packed_sum32": hex(sum32(packed)),
        "raw_sum8": hex(sum(raw) & 0xffff), "raw_sum32": hex(sum32(raw)),
        "raw_prefix_sum8": hex(sum(raw[:0x147fe00]) & 0xffff),
        "raw_tail_sum8": hex(sum(raw[0x147fe00:]) & 0xffff),
        "header_sum8": hex(sum(header) & 0xffff), "header_sum32": hex(sum32(header)),
        "raw_crc32": hex(zlib.crc32(raw)), "packed_crc32": hex(zlib.crc32(packed)),
        "raw_adler32": hex(zlib.adler32(raw)), "packed_adler32": hex(zlib.adler32(packed)),
        "raw_crc16_ccitt_0": hex(binascii.crc_hqx(raw, 0)),
        "raw_crc16_ccitt_ffff": hex(binascii.crc_hqx(raw, 0xffff)),
        "packed_crc16_ccitt_0": hex(binascii.crc_hqx(packed, 0)),
        "packed_crc16_ccitt_ffff": hex(binascii.crc_hqx(packed, 0xffff)),
    }, indent=2))


if __name__ == "__main__":
    main()
