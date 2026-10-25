#!/usr/bin/env python3
"""setter-va-hexdump.py - read-only dump of PE memory at runtime VAs.

Maps VA -> file offset using the PE section table and prints a hex/word dump.
Useful for inspecting dispatch tables referenced from decompiled code.

Usage: python3 -I setter-va-hexdump.py <module.dll> <va1> [va2 ...]
Options:
  --words      print as LE u32 words (default: bytes + words)
  --before N   also dump N*4 bytes before each address
  --span N     total words to print per address (default 16)
"""
import argparse
import struct
import sys


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("vas", nargs="+", type=lambda s: int(s, 0))
    ap.add_argument("--words", action="store_true")
    ap.add_argument("--before", type=int, default=0)
    ap.add_argument("--span", type=int, default=16)
    args = ap.parse_args()

    with open(args.module, "rb") as f:
        data = f.read()
    pe = u32(data, 0x3C)
    nsec = u16(data, pe + 6)
    opt = pe + 24
    magic = u16(data, opt)
    base = u32(data, opt + 28) if magic == 0x10B else 0
    sh = opt + u16(data, pe + 20)
    secs = []
    for i in range(nsec):
        s = sh + i * 40
        va, psz, raw = u32(data, s + 12), u32(data, s + 16), u32(data, s + 20)
        if psz:
            secs.append((va, psz, raw))

    def r2f(rva):
        for va, sz, raw in secs:
            if va <= rva < va + sz:
                return raw + (rva - va)
        return None

    print("image_base=0x%x" % base)
    for va in args.vas:
        start = va - args.before * 4
        print("-- VA 0x%08x (rva 0x%x) span %d words" % (va, va - base, args.span + args.before))
        off = r2f(va - base)
        if off is None:
            print("   <not mapped>")
            continue
        for k in range(args.span + args.before):
            a = start + k * 4
            fo = r2f(a - base)
            if fo is None:
                print("  0x%08x  <unmapped>" % a)
                continue
            w = u32(data, fo)
            line = "  0x%08x  %08x" % (a, w)
            if not args.words:
                by = data[fo:fo + 4]
                line += "  " + " ".join("%02x" % c for c in by)
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
