#!/usr/bin/env python3
"""Verify the VSRAM store checksums and A/B generations. Read-only.

Usage: python3 -I tools/checksums/vsram.py [--src PATH] [--base SECTOR] [--recompute]

PATH is the card image ($NISSAN_IMG, base 0) or a carve such as
work/raw-areas/settings_800768-818431.bin (base 800768, auto-detected by
size). Only structure and checksums are printed. The nav/bt areas hold
personal data, so their payload bytes are never printed.

Formats (see docs/findings/05-checksums.md), sum32 = sum of LE u32 words:
  VSDH sector:  +0x1F8 "VSDH", +0x1FC u32 = sum32(sector[0:0x1FC])
  SRAM copy:    +0x00 "SRST", +0x04 u32 0x6000000C, +0x08 u32 generation,
                +0x0C u32 copy (1 = A, 2 = B), payload ...,
                end-0x10 u32 sum32(copy[0:end-0x10]), 8 zero bytes, end-4 "SRED"
  MINF sector:  +0x04 u32 = sum32(sector with +0x04 zeroed)
  INITMPID:     +0x20 u32 = sum32(sector[0:0x20])
"""
import argparse
import os
import struct
import sys

SEC = 512
SETTINGS_BASE, SETTINGS_SECTORS = 800768, 17664
VSDH_SEC = 802816
SRAM_FIRST, SRAM_LAST = 806912, 809935
AREA_NAMES = ("sys", "nav", "bt")  # order on the card, per docs/findings/01
MINF_SEC, INITMPID_SEC = 800783, 800790
DEFAULT_IMG = os.environ.get(
    "NISSAN_IMG", os.path.expanduser("~/nissan/sdcard/nissan-sd-485-1972-00.img"))
FALLBACK = os.path.expanduser("~/nissan/work/raw-areas/settings_800768-818431.bin")


def sum32(b):
    return sum(struct.unpack("<%dI" % (len(b) // 4), b[:len(b) // 4 * 4])) & 0xFFFFFFFF


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class Src:
    def __init__(self, path, base):
        self.f = open(path, "rb")
        self.base = base

    def read(self, sec, n=1):
        self.f.seek((sec - self.base) * SEC)
        b = self.f.read(n * SEC)
        if len(b) != n * SEC:
            raise ValueError("short read at sector %d" % sec)
        return b


def sram_copy_sum(copy):
    """Value the trailer of an SRST..SRED copy must hold."""
    return sum32(copy[:-0x10])


def fixed_copy(copy, generation=None):
    """Return a new bytes object with the trailer (and optionally the
    generation) updated. For building a patch on a spare card; this tool
    never writes it anywhere."""
    b = bytearray(copy)
    if generation is not None:
        struct.pack_into("<I", b, 8, generation)
    struct.pack_into("<I", b, len(b) - 0x10, sram_copy_sum(b))
    return bytes(b)


def find_copies(src):
    """Walk SRST..SRED copies from SRAM_FIRST. Returns (start, nsec, bytes)."""
    out, sec = [], SRAM_FIRST
    while sec <= SRAM_LAST:
        if src.read(sec)[:4] != b"SRST":
            raise ValueError("no SRST at sector %d" % sec)
        end = sec
        while src.read(end)[0x1FC:] != b"SRED":
            end += 1
            if end > SRAM_LAST:
                raise ValueError("SRED not found after sector %d" % sec)
        n = end - sec + 1
        out.append((sec, n, src.read(sec, n)))
        sec = end + 1
    return out


def ok(a, b):
    return "OK " if a == b else "BAD"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=DEFAULT_IMG if os.path.exists(DEFAULT_IMG) else FALLBACK)
    ap.add_argument("--base", type=int, help="image sector of the file's first byte")
    ap.add_argument("--recompute", action="store_true",
                    help="print the trailer each copy would need after +1 generation (no writes)")
    a = ap.parse_args()
    base = a.base
    if base is None:
        base = SETTINGS_BASE if os.path.getsize(a.src) == SETTINGS_SECTORS * SEC else 0
    src = Src(a.src, base)
    print("source:", a.src, "base sector", base)
    good = True

    v = src.read(VSDH_SEC)
    s, c = u32(v, 0x1FC), sum32(v[:0x1FC])
    good &= v[0x1F8:0x1FC] == b"VSDH" and s == c
    print("%d VSDH  +0x1FC sum32 %08X/%08X %s" % (VSDH_SEC, s, c, ok(s, c)))

    m = bytearray(src.read(MINF_SEC))
    s = u32(m, 4)
    m[4:8] = b"\0" * 4
    c = sum32(m)
    good &= m[:4] == b"MINF" and s == c
    print("%d MINF  +0x04  sum32 %08X/%08X %s" % (MINF_SEC, s, c, ok(s, c)))

    i = src.read(INITMPID_SEC)
    s, c = u32(i, 0x20), sum32(i[:0x20])
    good &= i[:8] == b"INITMPID" and s == c
    print("%d INITMPID +0x20 sum32 %08X/%08X %s" % (INITMPID_SEC, s, c, ok(s, c)))

    copies = find_copies(src)
    if len(copies) != 2 * len(AREA_NAMES):
        print("expected %d copies, found %d" % (2 * len(AREA_NAMES), len(copies)))
        good = False
    for k, (sec, n, b) in enumerate(copies):
        name = AREA_NAMES[k // 2] if k // 2 < len(AREA_NAMES) else "?"
        gen, cp = u32(b, 8), u32(b, 0xC)
        s, c = u32(b, len(b) - 0x10), sram_copy_sum(b)
        tail_ok = b[-0xC:-4] == b"\0" * 8
        good &= s == c and tail_ok and u32(b, 4) == 0x6000000C
        print("%d-%d %-3s copy=%s n=%d bytes=%#x flags=%08X gen=%#x  sum32 %08X/%08X %s"
              % (sec, sec + n - 1, name, "AB"[cp - 1] if cp in (1, 2) else cp, n, len(b),
                 u32(b, 4), gen, s, c, ok(s, c)))
    for k in range(0, len(copies) - 1, 2):
        (_, _, x), (_, _, y) = copies[k], copies[k + 1]
        gx, gy = u32(x, 8), u32(y, 8)
        cur, old = ("A", "B") if gx > gy else ("B", "A")
        print("%-3s current copy: %s (gen %#x vs %#x)%s" % (
            AREA_NAMES[k // 2], cur, max(gx, gy), min(gx, gy),
            "" if abs(gx - gy) == 1 else "  [gens not adjacent]"))
        if a.recompute:
            # next save goes to the older copy with gen+1 (A odd, B even on this card)
            nb = bytearray(x if cur == "A" else y)
            struct.pack_into("<I", nb, 0xC, 1 if old == "A" else 2)
            nb = fixed_copy(nb, max(gx, gy) + 1)
            print("    recompute: unchanged payload saved to %s as gen %#x -> trailer %08X"
                  % (old, max(gx, gy) + 1, u32(nb, len(nb) - 0x10)))
    print("ALL OK" if good else "MISMATCH")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
