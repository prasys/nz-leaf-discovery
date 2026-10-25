#!/usr/bin/env python3
"""Print the saved clock-offset settings from a card image or settings carve (issue #1).

Read-only, files only (never a device).  Prints nothing but these setting words:

  ExpSet (OBJ_Setting class 5, Setting+0x40, OBJ_ExpSet_write 0x40e48be8):
      word 5 ExpOffsetHour (stored h+12, 0x80000000 = never set)
      word 6 ExpOffsetMin  (stored m+59, 0x80000000 = never set)
      word 7 ExpAutoDst    (1 = on)
    found at +0x1A0 of LBA 808677 (copy A) and 809821 (copy B), i.e. +1029 sectors
    into the SRST areas at LBA 807648 / 808792.
  OBJ_Time record (class 2) at nav area +0x144 (LBA 807028 / 807338):
      +0x14 zone, +0x18 zone type, +0x1C DST, +0x20 user offset (1/100 s)

Usage: expset_scan.py [image-or-settings-carve]
"""
import os
import struct
import sys

SETTINGS_FIRST_LBA, SETTINGS_SECTORS = 800768, 818431 - 800768 + 1
DEFAULT = os.path.expanduser("~/nissan/work/raw-areas/settings_800768-818431.bin")
UNSET = 0x80000000
EXPSET = (("A", 807648, 808677, 0x1A0), ("B", 808792, 809821, 0x1A0))
NAV = (("A", 807028), ("B", 807338))


def reader(path):
    f = open(path, "rb")
    size = os.fstat(f.fileno()).st_size
    if size == SETTINGS_SECTORS * 512:
        base = SETTINGS_FIRST_LBA
    elif size >= (SETTINGS_FIRST_LBA + SETTINGS_SECTORS) * 512:
        base = 0
    else:
        raise SystemExit("not a card image or settings carve: %d bytes" % size)

    def read(lba, off, n):
        f.seek((lba - base) * 512 + off)
        return f.read(n)
    return read


def decode_expset(words):
    hour, minute, dst = words[5], words[6], words[7]
    h = None if hour == UNSET else hour - 12
    m = None if minute == UNSET else minute - 59
    # FUN_4285ea98: unset fields contribute nothing
    total = (h or 0) * 360000 + (m or 0) * 6000
    return h, m, dst == 1, total


def main(argv):
    read = reader(argv[0] if argv else DEFAULT)
    for name, area, lba, off in EXPSET:
        magic = read(area, 0, 4)
        gen = struct.unpack("<I", read(area, 8, 4))[0]
        words = struct.unpack("<8I", read(lba, off, 32))
        h, m, dst, total = decode_expset(words)
        print("ExpSet %s (area LBA %d %s gen %d): hour word 0x%08X -> %s h, min word 0x%08X -> %s min,"
              " AutoDst %s, offset written on next set = %d (%+.2f h)"
              % (name, area, magic.decode("latin1"), gen, words[5], "unset" if h is None else "%+d" % h,
                 words[6], "unset" if m is None else "%+d" % m, dst, total, total / 360000))
    for name, lba in NAV:
        magic = read(lba, 0, 4)
        gen = struct.unpack("<I", read(lba, 8, 4))[0]
        zone, ztype, dst, offset = struct.unpack("<iiii", read(lba, 0x144 + 0x14, 16))
        print("Time   %s (nav LBA %d %s gen %d): zone %d (%+.2f h) type %d DST %d user offset %d (%+.2f h)"
              % (name, lba, magic.decode("latin1"), gen, zone, zone / 360000, ztype, dst, offset,
                 offset / 360000))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
