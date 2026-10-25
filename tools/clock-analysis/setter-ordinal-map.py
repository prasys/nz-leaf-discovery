#!/usr/bin/env python3
"""setter-ordinal-map.py - read-only dump of a PE export table keyed by ordinal.

CE modules export mostly by ordinal; this prints EVERY ordinal with its name
(or '(unnamed)') so import-by-ordinal can be resolved.

Scope/assumptions (explicit):
- PE32 ONLY: optional-header magic must be 0x10B (PE32). Other magics are
  rejected with an error.
- Export directory uses the STANDARD IMAGE_EXPORT_DIRECTORY layout:
  Name +12, Base +16, NumberOfFunctions +20, NumberOfNames +24,
  AddressOfFunctions +28, AddressOfNames +32, AddressOfNameOrdinals +36
  (verified against llvm-readobj --coff-exports on OBJDLL.dll/coredll.dll).
- An export function RVA inside the export-directory span
  [export_rva, export_rva + export_size) is a FORWARDER (ASCII
  "DLL.EntryPoint" string), not executable code; tagged FORWARDER and the
  printed VA is not an execution address.

Usage: python3 -I setter-ordinal-map.py <module.dll> [ordinal ...]
       --grep RE filters output on names.
"""
import argparse
import re
import struct
import sys


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def cstr(b, o):
    e = b.find(b"\x00", o)
    return b[o:e if e >= 0 else o].decode("latin-1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("ords", nargs="*", type=int)
    ap.add_argument("--grep", default=None)
    args = ap.parse_args()
    pat = re.compile(args.grep) if args.grep else None

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

    ddir = opt + 96  # PE32 data directory offset
    exp_rva = u32(data, ddir)
    exp_size = u32(data, ddir + 4)
    off = r2f(exp_rva)
    if off is None:
        print("error: export RVA 0x%x not mapped" % exp_rva)
        return 1
    # STANDARD IMAGE_EXPORT_DIRECTORY layout (see module docstring)
    n_funcs = u32(data, off + 20)
    n_names = u32(data, off + 24)
    ord_base = u32(data, off + 16)
    a_names = r2f(u32(data, off + 32))
    a_funcs = r2f(u32(data, off + 28))
    a_ords = r2f(u32(data, off + 36))
    by_idx = {}
    for i in range(n_names):
        try:
            nm = cstr(data, r2f(u32(data, a_names + i * 4)))
        except struct.error:
            continue
        by_idx[u16(data, a_ords + i * 2)] = nm
    wanted = set(args.ords)
    for k in range(n_funcs):
        ordno = ord_base + k
        if wanted and ordno not in wanted:
            continue
        nm = by_idx.get(k, "(unnamed)")
        rva = u32(data, a_funcs + k * 4)
        if exp_rva <= rva < exp_rva + exp_size:
            fwd = cstr(data, r2f(rva))
            match_text = nm + " FORWARDER->" + fwd
            line = "ord=%-6d %-40s FORWARDER -> %s" % (ordno, nm, fwd)
        else:
            match_text = nm
            line = "ord=%-6d %-40s rva=0x%-6x va=0x%x" % (ordno, nm, rva, base + rva)
        if pat and not pat.search(match_text):
            continue
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
