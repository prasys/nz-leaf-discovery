#!/usr/bin/env python3
"""manual_skin_context.py - read-only: list tagged skin records around file
offsets. Record layout (finding 06 §3): [u16 len][u16 kind][u32 type][payload]
from 0x40 to 0x51b9f0. Prints record offset, kind, type and any UTF-16LE
strings (>= 4 chars) in the payload. No bytecode is interpreted.

Usage: python3 -I manual_skin_context.py <substance.skn> <off> [<off> ...] [--span N]
"""
import re, struct, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
span = 6
if "--span" in sys.argv:
    span = int(sys.argv[sys.argv.index("--span") + 1])
    args.remove(str(span))
d = open(args[0], "rb").read()
recs, o = [], 0x40
while o < 0x51b9f0:
    ln, kind, typ = struct.unpack_from("<HHI", d, o)
    if ln < 8:
        break
    recs.append((o, ln, kind, typ))
    o += ln
for t in (int(x, 0) for x in args[1:]):
    idx = next(i for i, r in enumerate(recs) if r[0] <= t < r[0] + r[1])
    print("== target 0x%x in record #%d" % (t, idx))
    for o, ln, kind, typ in recs[max(0, idx - span): idx + span + 1]:
        strs = [m.group().decode("utf-16-le") for m in
                re.finditer(rb"(?:[\x20-\x7e]\x00){4,}", d[o + 8:o + ln])]
        print("%s0x%06x len=%-5d kind=0x%04x type=0x%08x %s" % (
            ">" if o <= t < o + ln else " ", o, ln, kind, typ, strs[:4]))
