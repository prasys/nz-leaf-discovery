#!/usr/bin/env python3 -I
"""Verify the firmware slot checksums on a card image (read-only).

Usage: python3 -I tools/ce-extract/slotsum.py [image]   (default $NISSAN_IMG)

SUM4  (slot header sector, G314/G214 style): header +0x00 u32 size, +0x30 "SUM4",
      +0x34 u32 = sum of little-endian u32 words of the `size` bytes that follow
      the 512-byte header (zero-padded to a multiple of 4), mod 2^32.
MTCP  (G214 container): per-chunk u32 at +0x2C+32*k = the same word sum over that
      chunk's compressed bytes (comp size from the chunk table).
"""
import os
import struct
import sys

SLOTS = (65536, 157696, 667648, 749568, 790528)


def sum32(b):
    b = b + b"\0" * (-len(b) % 4)
    return sum(struct.unpack("<%dI" % (len(b) // 4), b)) & 0xFFFFFFFF


def main(argv):
    img = argv[1] if len(argv) > 1 else os.environ.get(
        "NISSAN_IMG", os.path.expanduser("~/nissan/sdcard/nissan-sd-485-1972-00.img"))
    bad = 0
    with open(img, "rb") as f:
        for sec in SLOTS:
            f.seek(sec * 512)
            h = f.read(512)
            size = struct.unpack_from("<I", h, 0)[0]
            if h[0x30:0x34] != b"SUM4":
                print("%8d  no SUM4 in header sector (tail %r)" % (sec, h[0x1FC:]))
                continue
            stored = struct.unpack_from("<I", h, 0x34)[0]
            data = f.read(size)
            calc = sum32(data)
            ok = calc == stored
            bad += not ok
            print("%8d  SUM4 size=%#x stored=%#010x calc=%#010x %s" % (sec, size, stored, calc, "OK" if ok else "MISMATCH"))
            if data[:4] == b"MTCP":
                count = struct.unpack_from("<I", data, 4)[0]
                pos = 0x200
                for k in range(count):
                    secs, raw, comp, chk = struct.unpack_from("<IIII", data, 0x20 + 32 * k)
                    c = sum32(data[pos:pos + comp])
                    bad += c != chk
                    print("          MTCP chunk %2d comp=%#x stored=%#010x calc=%#010x %s"
                          % (k, comp, chk, c, "OK" if c == chk else "MISMATCH"))
                    pos += secs * 512
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
