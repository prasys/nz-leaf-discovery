#!/usr/bin/env python3
"""setter-arm-mc.py - read-only ARM disassembly of a Windows CE PE at runtime VAs.

Extracts raw bytes from the PE at the mapped file offsets and disassembles
them word-by-word with llvm-mc (the system llvm-objdump cannot parse
machine=0x1c2 COFF). Never writes anything outside stdout.

Behaviour (explicit):
- Half-open span [start, end): end is exclusive. start must be < end, both
  4-byte aligned, and the whole span must map into the PE's sections.
- --limit caps the span length in bytes (default 4096); a larger span is
  rejected.
- Each 4-byte word is mapped and disassembled separately. Output lines carry
  the exact source VA, the raw bytes (little-endian stream order, i.e. file
  order), and the decode. An invalid/data word keeps its place: the raw bytes
  and the next address are still printed, so addresses never skip.
- Any llvm-mc failure for a word is reported and makes the tool exit
  non-zero; failures are never silently passed.
- PE32 ONLY (optional-header magic 0x10B); other magics are rejected.

Usage: python3 -I setter-arm-mc.py <module.dll> <va_start> <va_end>
       [--llvm /opt/homebrew/opt/llvm/bin] [--limit 4096]
"""
import argparse
import struct
import subprocess
import sys


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("start", type=lambda s: int(s, 0))
    ap.add_argument("end", type=lambda s: int(s, 0))
    ap.add_argument("--llvm", default="/opt/homebrew/opt/llvm/bin")
    ap.add_argument("--limit", type=int, default=4096)
    args = ap.parse_args()
    mc = args.llvm + "/llvm-mc"

    start, end = args.start, args.end
    if start >= end:
        print("error: reversed/empty span (start 0x%x >= end 0x%x)" % (start, end))
        return 1
    if start % 4 or end % 4:
        print("error: span must be 4-byte aligned (start 0x%x end 0x%x)" % (start, end))
        return 1
    span = end - start
    if span > args.limit:
        print("error: span %d bytes exceeds limit %d (use --limit or a smaller span)"
              % (span, args.limit))
        return 1

    with open(args.module, "rb") as f:
        data = f.read()
    pe = u32(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        print("error: no PE signature")
        return 1
    opt = pe + 24
    magic = u16(data, opt)
    if magic != 0x10B:
        print("error: PE32 only (magic=0x10B required, got 0x%X)" % magic)
        return 1
    base = u32(data, opt + 28)
    nsec = u16(data, pe + 6)
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

    failed = 0
    addr = start
    while addr < end:
        fo = r2f(addr - base)
        if fo is None:
            print("error: VA 0x%08x is not mapped by any section" % addr)
            return 1
        word = data[fo:fo + 4]  # little-endian stream order = file order
        rawhex = " ".join("%02x" % c for c in word)
        res = subprocess.run(
            [mc, "--disassemble", "--triple=armv7-none-eabi",
             "--arm-add-build-attributes"],
            input=" ".join("0x%02x" % c for c in word),
            capture_output=True, text=True)
        text = res.stdout.strip()
        if res.returncode != 0 or res.stderr.strip() or not text:
            print("0x%08x: %s  <LLVM-MC-ERROR rc=%d: %s>"
                  % (addr, rawhex, res.returncode, res.stderr.strip() or "no output"))
            failed += 1
        else:
            print("0x%08x: %s  %s" % (addr, rawhex, text))
        addr += 4
    if failed:
        print("setter-arm-mc: FAILED: %d word(s) failed to decode" % failed)
        return 2
    print("setter-arm-mc: OK %d bytes from 0x%08x to 0x%08x (exclusive)" % (span, start, end))
    return 0


if __name__ == "__main__":
    sys.exit(main())
