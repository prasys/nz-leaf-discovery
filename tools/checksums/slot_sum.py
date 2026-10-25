#!/usr/bin/env python3
"""Verify the firmware slot checksums (issue #9). Read-only.

Usage: python3 -I tools/checksums/slot_sum.py [--img PATH] [--recompute]

PATH is the card image ($NISSAN_IMG) or anything that starts at image
sector 0, e.g. work/raw-areas/pre_s0-888832.bin. Nothing is ever written;
--recompute only prints the values a patched slot would need.

Algorithms (see docs/findings/05-checksums.md):
  sum32(b) = sum of little-endian u32 words, mod 2^32
  sum8(b)  = sum of bytes, mod 2^16 where stored as u16
  slot hdr +0x30 "SUM4" u32 = sum32(payload)
  slot hdr +0x14 u16       = sum8(payload)            (G314 only; G214 differs)
  NK image +0x30 u16       = sum8(image with +0x30..+0x31 zeroed)
  MTLD part entry sum      = sum32(part bytes)
  MTCP chunk entry sum     = sum32(chunk, padded to whole sectors)
  BASS file +0x04 u32      = sum32(file[0x08:size])
"""
import argparse
import os
import struct
import sys

SEC = 512
SLOTS = (65536, 157696, 667648, 749568, 790528)
DEFAULT_IMG = os.environ.get(
    "NISSAN_IMG", os.path.expanduser("~/nissan/sdcard/nissan-sd-485-1972-00.img"))
FALLBACK = os.path.expanduser("~/nissan/work/raw-areas/pre_s0-888832.bin")


def sum32(b):
    n = len(b) // 4
    s = sum(struct.unpack("<%dI" % n, b[:n * 4]))
    if len(b) % 4:  # pad the tail with zeros
        s += int.from_bytes(b[n * 4:] + b"\0" * (4 - len(b) % 4), "little")
    return s & 0xFFFFFFFF


def sum8(b):
    return sum(b)


class Img:
    def __init__(self, path):
        self.f = open(path, "rb")

    def read(self, sec, n):
        self.f.seek(sec * SEC)
        b = self.f.read(n)
        if len(b) != n:
            raise ValueError("short read at sector %d" % sec)
        return b


def ok(a, b):
    return "OK " if a == b else "BAD"


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def cstr(b, o, n):
    return b[o:o + n].split(b"\0")[0].decode("ascii", "replace")


def check_mtld(hdr, pay, out):
    """G214: MTLD part table in the slot header, MTCP chunk table in part 0."""
    cnt = u32(hdr, 0x74)
    out.append("    MTLD parts=%d  +0x08=0x%08X (unverified, see doc)" % (cnt, u32(hdr, 0x78)))
    good = True
    for i in range(cnt):
        e = 0x90 + i * 0x20
        ssec, nsec, size, ck = struct.unpack_from("<4I", hdr, e)
        tag = cstr(hdr, e + 0x10, 4)
        load = u32(hdr, e + 0x14)
        part = pay[ssec * SEC:ssec * SEC + size]
        c = sum32(part)
        good &= c == ck
        out.append("    part%d tag=%-4s sec+%#x n=%#x bytes=%#x load=%#x sum32 %08X/%08X %s"
                   % (i, tag or "raw", ssec, nsec, size, load, ck, c, ok(ck, c)))
        if tag == "MTCP":
            good &= check_mtcp(part, out)
    return good


def check_mtcp(part, out):
    cnt, chunk = u32(part, 4), u32(part, 8)
    off, bad, usz = SEC, 0, 0
    for i in range(cnt):
        nsec, usize, csize, ck = struct.unpack_from("<4I", part, 0x20 + i * 0x20)
        c = sum32(part[off:off + nsec * SEC])
        bad += c != ck
        usz += usize
        off += nsec * SEC
    out.append("    MTCP chunks=%d chunk=%#x unpacked=%#x  per-chunk sum32: %d/%d OK"
               % (cnt, chunk, usz, cnt - bad, cnt))
    return bad == 0


def check_slot(img, sec, recompute):
    hdr = img.read(sec, SEC)
    out = []
    good = True
    if hdr[:4] == b"BASS":
        nsec = u32(hdr, 4)
        f = img.read(sec + 1, nsec * SEC)
        size = u32(f, 0x14)
        ck, c = u32(f, 4), sum32(f[8:size])
        good = hdr[0x1FC:0x200] == b"BASS" and f[:4] == b"BASS" and ck == c
        out.append("%d BASS %s sectors=%#x file=%#x  file+0x04 sum32 %08X/%08X %s"
                   % (sec, cstr(f, 0x1C, 12), nsec, size, ck, c, ok(ck, c)))
        return good, out

    size = u32(hdr, 0)
    pay = img.read(sec + 1, size)
    nkok = hdr[0x1FC:0x200] == b"NKOK"
    if hdr[0x30:0x34] == b"SUM4":
        name = cstr(hdr, 0x16, 16)
        s4, c4 = u32(hdr, 0x34), sum32(pay)
        s2, c2 = u16(hdr, 0x14), sum8(pay) & 0xFFFF
        good = nkok and s4 == c4
        out.append("%d %s %s size=%#x NKOK=%s" % (sec, name, cstr(hdr, 0x50, 16), size, nkok))
        out.append("    +0x30 SUM4 sum32 %08X/%08X %s" % (s4, c4, ok(s4, c4)))
        out.append("    +0x14 u16  sum8  %04X/%04X %s%s" % (
            s2, c2, ok(s2, c2), "" if s2 == c2 else " (raw payload; see doc)"))
        if hdr[0x70:0x74] == b"MTLD":
            good &= check_mtld(hdr, pay, out)
        if recompute:
            out.append("    recompute: hdr+0x34=%08X hdr+0x14=%04X" % (c4, c2))
    else:
        # bootable NK image: header holds only the size, sum lives in the image
        z = bytearray(pay[:0x40])
        z[0x30:0x32] = b"\0\0"
        s2 = u16(pay, 0x30)
        c2 = (sum8(z) + sum8(pay[0x40:])) & 0xFFFF
        isz = u32(pay, 0x32)
        good = nkok and s2 == c2 and isz == size
        out.append("%d %s %s size=%#x NKOK=%s (NK image)"
                   % (sec, cstr(pay, 0x20, 16), cstr(pay, 0x50, 16), size, nkok))
        out.append("    img+0x30 u16 sum8 %04X/%04X %s  img+0x32 size %#x %s"
                   % (s2, c2, ok(s2, c2), isz, ok(isz, size)))
        out.append("    img+0x6C u32 0x%08X (unknown, not a sum32/CRC32 of the image)" % u32(pay, 0x6C))
        if recompute:
            out.append("    recompute: img+0x30=%04X" % c2)
    return good, out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--img", default=DEFAULT_IMG if os.path.exists(DEFAULT_IMG) else FALLBACK)
    ap.add_argument("--recompute", action="store_true",
                    help="also print the values a modified payload would need (no writes)")
    a = ap.parse_args()
    img = Img(a.img)
    print("source:", a.img)
    allgood = True
    for sec in SLOTS:
        good, out = check_slot(img, sec, a.recompute)
        allgood &= good
        print("\n".join(out))
    print("ALL KNOWN CHECKS OK" if allgood else "MISMATCH")
    return 0 if allgood else 1


if __name__ == "__main__":
    sys.exit(main())
