#!/usr/bin/env python3
"""manual_movw_scan.py - read-only scan of CE PE modules for ARM movw/movt
pairs that build a given 32-bit constant in one register (A1 encoding).

Usage: python3 -I manual_movw_scan.py 0x841000cd <module-or-dir> [...]
Prints module, runtime VA of the movw, and the register. Pairs are matched
when movt to the same register follows within 8 instructions. Stdlib only;
opens files read-only.
"""
import os, struct, sys

def sections(d):
    pe = struct.unpack_from("<I", d, 0x3c)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    out = []
    o = pe + 24 + opt
    for i in range(nsec):
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((va, raw, rsz))
        o += 40
    return base, out

def scan(path, val):
    d = open(path, "rb").read()
    if d[:2] != b"MZ":
        return
    base, secs = sections(d)
    lo, hi = val & 0xffff, val >> 16
    for va, raw, rsz in secs:
        words = [struct.unpack_from("<I", d, raw + i)[0] for i in range(0, rsz - 3, 4)]
        for i, w in enumerate(words):
            # movw: cond 0011 0000 imm4 Rd imm12
            if (w & 0x0ff00000) != 0x03000000:
                continue
            if ((w >> 4) & 0xf000) | (w & 0xfff) != lo:
                continue
            rd = (w >> 12) & 0xf
            for j in range(i + 1, min(i + 9, len(words))):
                t = words[j]
                if (t & 0x0ff00000) == 0x03400000 and ((t >> 12) & 0xf) == rd:
                    if ((t >> 4) & 0xf000) | (t & 0xfff) == hi:
                        print("%s 0x%08x r%d" % (os.path.basename(path), base + va + 4 * i, rd))
                    break

val = int(sys.argv[1], 0)
for p in sys.argv[2:]:
    if os.path.isdir(p):
        for f in sorted(os.listdir(p)):
            scan(os.path.join(p, f), val)
    else:
        scan(p, val)
