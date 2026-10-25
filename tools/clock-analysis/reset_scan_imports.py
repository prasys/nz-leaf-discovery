#!/usr/bin/env python3
"""reset_scan_imports.py -- read-only CE PE import-table scanner.

Dumps the import directory of an extracted Windows CE module (COFF/o32 PE),
mapping each import thunk VA (IAT slot address = imagebase + RVA) to its DLL
and (hint-)name or ordinal.  Used to correlate call sites like
`ldr r12,[pc]; ldr r12,[r12]; bx r12` thunks with the imported OBJ_Time_*
writers.  Read-only; stdlib only.

Usage: python3 -I reset_scan_imports.py <module.dll> [name-regex]
"""
import re
import struct
import sys


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    rx = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
    with open(path, "rb") as f:  # read-only
        data = f.read()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    optsz = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x10B:  # PE32
        imagebase = struct.unpack_from("<I", data, opt + 28)[0]
        dd = opt + 96
    else:
        raise SystemExit(f"unsupported optional header magic 0x{magic:x}")
    imp_rva, imp_size = struct.unpack_from("<II", data, dd + 8)  # dir 1 = import
    secs = []
    off = opt + optsz
    for i in range(nsec):
        s = off + i * 40
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, s + 8)
        secs.append((va, vsize, rawptr, rawsize))

    def rva2off(rva):
        for va, vsize, raw, rawsize in secs:
            if va <= rva < va + max(vsize, rawsize) and rva - va < rawsize:
                return raw + (rva - va)
        return None

    def cstr(off, maxn=256):
        end = data.find(b"\0", off, off + maxn)
        return data[off:end].decode("latin1")

    if imp_rva == 0:
        print("no import directory")
        return 0
    o = rva2off(imp_rva)
    if o is None:
        print("import directory RVA unmapped")
        return 0
    max_entries = imp_size // 20 if imp_size else 4096
    n = 0
    while n < max_entries:
        iva, tds, fwd, name_rva, iat_rva = struct.unpack_from("<IIIII", data, o + n * 20)
        n += 1
        if iva == 0 and name_rva == 0:
            break
        noff = rva2off(name_rva)
        thunk_off = rva2off(iva)
        if noff is None or thunk_off is None:
            print(f"entry {n}: unmapped (iva=0x{iva:08x} name=0x{name_rva:08x})")
            continue
        dll = cstr(noff)
        k = 0
        while True:
            v = struct.unpack_from("<I", data, thunk_off + k * 4)[0]
            if v == 0:
                break
            if v & 0x80000000:
                label = f"ordinal {v & 0x7fffffff}"
            else:
                noff2 = rva2off(v)
                if noff2 is None:
                    label = f"<bad hint rva 0x{v:08x}>"
                else:
                    hint = struct.unpack_from("<H", data, noff2)[0]
                    label = f"hint {hint} {cstr(noff2 + 2)}"
            slot_va = imagebase + iat_rva + k * 4
            if rx is None or rx.search(label):
                print(f"0x{slot_va:08x}  {dll}  {label}")
            k += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
