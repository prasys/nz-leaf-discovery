#!/usr/bin/env python3 -I
"""Unpack the MTCP container used by the G214JLNI (HMI) firmware slot.

Usage:
    python3 -I tools/ce-extract/mtcp.py <slot157696_G214...bin> [out.bin]

Layout [confirmed: every chunk decodes to exactly its raw size; ECEC lands at +0x40]:
    +0x00  "MTCP", u32 chunk count, u32 chunk raw size (0x200000)
    +0x20  per chunk, 32 bytes: u32 stored length in 512-byte sectors, u32 raw size,
           u32 compressed size, u32 check value (algorithm unknown), 16 bytes zero
    +0x200 chunk 0, then each chunk padded to its sector count
    chunk = one raw LZ4 *block* (no frame header)
The bytes after the last chunk (G214: 0x1412400 bytes at +0x93E000) are the
uncompressed remainder of the same CE image: the ROMHDR (VA 0x8B0CF918, offset
0x288F918) lies there. <out> is chunks + remainder, ready for ceromx.py.
The per-chunk u32 at +12 is not CRC-32/CRC-32C/MPEG-2 of the raw or compressed
bytes; it is reported but not checked (the exact LZ4 output size is).
Default out: $NISSAN_ROOT/work/ce-extract/G214JLNI.066.nb0
"""

import os
import struct
import sys


def lz4_block(src, raw_size):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        if off == 0 or off > len(out):
            raise ValueError("bad LZ4 offset %d at %d" % (off, i))
        s = len(out) - off
        if off >= ml:
            out += out[s:s + ml]
        else:
            for k in range(ml):
                out.append(out[s + k])
    if len(out) != raw_size:
        raise ValueError("LZ4 produced %d bytes, expected %d" % (len(out), raw_size))
    return bytes(out)


def unpack(d):
    if d[:4] != b"MTCP":
        raise ValueError("no MTCP magic")
    count, csize = struct.unpack_from("<II", d, 4)
    pos = 0x200
    chunks = []
    for k in range(count):
        secs, raw, comp, crc = struct.unpack_from("<IIII", d, 0x20 + 32 * k)
        blk = lz4_block(d[pos:pos + comp], raw)
        chunks.append((k, pos, secs, raw, comp, crc))
        yield blk, chunks[-1]
        pos += secs * 512
    unpack.end = pos


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = os.environ.get("NISSAN_ROOT", os.path.expanduser("~/nissan"))
    out = argv[2] if len(argv) > 2 else os.path.join(root, "work", "ce-extract", "G214JLNI.066.nb0")
    d = open(argv[1], "rb").read()
    with open(out, "wb") as f:
        for blk, (k, pos, secs, raw, comp, crc) in unpack(d):
            f.write(blk)
            print("chunk %2d @%#09x sectors=%#x raw=%#x comp=%#x sum?=%08x"
                  % (k, pos, secs, raw, comp, crc))
        tail = d[unpack.end:]
        f.write(tail)
    print("remainder %#x bytes from %#x appended" % (len(tail), unpack.end))
    print("wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
