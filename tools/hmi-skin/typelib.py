#!/usr/bin/env python3 -I
"""List interfaces and member DISPIDs from an MSFT type library embedded in a PE/DLL.

Usage: python3 -I tools/hmi-skin/typelib.py <module.dll> [name-regex]
Layout follows Wine's MSFT reader (dlls/oleaut32/typelib.c). Read-only.
"""
import re
import struct
import sys

KINDS = ["ENUM", "RECORD", "MODULE", "INTERFACE", "DISPATCH", "COCLASS", "ALIAS", "UNION"]


def parse(t):
    (magic, _ver, _posguid, _lcid, _lcid2, varflags, _v, _flags, ntypes) = struct.unpack_from("<4sIIIIIIII", t, 0)
    p = 0x54 + (4 if varflags & 0x100 else 0)
    p += 4 * ntypes
    seg = [struct.unpack_from("<IIII", t, p + 16 * k) for k in range(15)]
    ti_off, name_off = seg[0][0], seg[7][0]

    def name(o):
        n = t[name_off + o + 8]
        return t[name_off + o + 12:name_off + o + 12 + n].decode("latin1")

    out = []
    for i in range(ntypes):
        b = ti_off + 0x64 * i
        kind, memoff = struct.unpack_from("<II", t, b)
        celem = struct.unpack_from("<I", t, b + 0x18)[0]
        nameoff = struct.unpack_from("<I", t, b + 0x2C)[0]
        nfunc, nvar = celem & 0xFFFF, celem >> 16
        tname = name(nameoff)
        members = []
        if nfunc + nvar and memoff not in (0, 0xFFFFFFFF):
            infolen = struct.unpack_from("<I", t, memoff)[0]
            ids = memoff + 4 + infolen
            for k in range(nfunc + nvar):
                memid = struct.unpack_from("<I", t, ids + 4 * k)[0]
                noff = struct.unpack_from("<I", t, ids + 4 * (nfunc + nvar) + 4 * k)[0]
                members.append((memid, "func" if k < nfunc else "var", name(noff)))
        out.append((KINDS[kind & 0xF] if (kind & 0xF) < 8 else kind, tname, members))
    return out


def main(argv):
    d = open(argv[1], "rb").read()
    i = d.find(b"MSFT")
    if i < 0:
        print("no MSFT typelib")
        return 1
    rx = re.compile(argv[2], re.I) if len(argv) > 2 else None
    for kind, tname, members in parse(d[i:]):
        ms = [m for m in members if not rx or rx.search(m[2])]
        if rx and not ms:
            continue
        print("%s %s (%d members)" % (kind, tname, len(members)))
        for memid, inv, n in ms:
            print("   %#010x %-8s %s" % (memid, inv, n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
