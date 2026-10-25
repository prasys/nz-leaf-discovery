#!/usr/bin/env python3
"""setter-pe-tables.py - read-only PE export/import table dumper.

Reads an extracted Windows CE PE module and prints its export table
(names, ordinals, RVAs) and import table (DLL + imported names).
Never writes anything. Stdlib only.

Scope/assumptions (explicit):
- PE32 ONLY: optional-header magic must be 0x10B (PE32). PE32+ (0x20B) and any
  other magic are rejected with an error.
- Export directory uses the STANDARD IMAGE_EXPORT_DIRECTORY layout:
  Characteristics +0, TimeDateStamp +4, MajorVersion +8, MinorVersion +10,
  Name +12, Base +16, NumberOfFunctions +20, NumberOfNames +24,
  AddressOfFunctions +28, AddressOfNames +32, AddressOfNameOrdinals +36
  (verified against llvm-readobj --coff-exports on OBJDLL.dll/coredll.dll).
- An export function RVA that falls inside the export-directory span
  [export_rva, export_rva + export_size) is a FORWARDER: the "RVA" points at
  an ASCII "DLL.EntryPoint" string, not executable code. Such entries are
  tagged FORWARDER with the string; the VA is not an execution address.

Usage: python3 -I setter-pe-tables.py <module.dll> [--imports] [--exports] [--grep RE]

VA base is taken from ImageBase in the optional header so RVAs can be shown as
runtime VAs for comparison with Ghidra addresses.
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
    ap.add_argument("--imports", action="store_true", help="print import table")
    ap.add_argument("--exports", action="store_true", help="print export table")
    ap.add_argument("--grep", default=None, help="regex filter on names")
    args = ap.parse_args()
    show_e = args.exports or not (args.imports or args.exports)
    show_i = args.imports or not (args.imports or args.exports)
    pat = re.compile(args.grep) if args.grep else None

    with open(args.module, "rb") as f:
        data = f.read()
    if data[:2] != b"MZ":
        print("error: not a PE/MZ image")
        return 1
    pe = u32(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        print("error: no PE signature")
        return 1
    machine = u16(data, pe + 4)
    nsec = u16(data, pe + 6)
    opt = pe + 24
    magic = u16(data, opt)
    if magic != 0x10B:
        print("error: PE32 only (magic=0x10B required, got 0x%X)" % magic)
        return 1
    image_base = u32(data, opt + 28)
    ddir = opt + 96  # PE32 data directory starts at +96 in the optional header
    exp_rva, exp_size = u32(data, ddir), u32(data, ddir + 4)
    imp_rva = u32(data, ddir + 8)

    # build RVA->file offset map from sections
    sh = opt + u16(data, pe + 20)  # optional header size
    secs = []
    for i in range(nsec):
        s = sh + i * 40
        va, psz, raw = u32(data, s + 12), u32(data, s + 16), u32(data, s + 20)
        secs.append((va, max(psz, 1), raw))
    # sections are sorted by VA; map any RVA

    def r2f(rva):
        for va, sz, raw in secs:
            if va <= rva < va + sz:
                return raw + (rva - va)
        return None

    print("machine=0x%x image_base=0x%x sections=%d" % (machine, image_base, nsec))

    if show_e and exp_rva:
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
        print("EXPORTS base_ordinal=%d functions=%d names=%d"
              % (ord_base, n_funcs, n_names))
        for i in range(n_names):
            name = cstr(data, r2f(u32(data, a_names + i * 4)))
            ord_idx = u16(data, a_ords + i * 2)
            fn_rva = u32(data, a_funcs + ord_idx * 4)
            if exp_rva <= fn_rva < exp_rva + exp_size:
                fwd = cstr(data, r2f(fn_rva))
                nm = ("EXP %-46s ord=%-5d FORWARDER -> %s"
                      % (name, ord_base + ord_idx, fwd))
                match_text = name + " FORWARDER->" + fwd
            else:
                nm = "EXP %-46s ord=%-5d rva=0x%-6x va=0x%x" % (
                    name, ord_base + ord_idx, fn_rva, image_base + fn_rva)
                match_text = name
            if pat is None or pat.search(match_text):
                print(nm)
    elif show_e:
        print("EXPORTS none")

    if show_i and imp_rva:
        off = r2f(imp_rva)
        if off is None:
            print("error: import RVA 0x%x not mapped" % imp_rva)
            return 1
        print("IMPORTS")
        i = 0
        while True:
            e = off + i * 20
            ilt_rva = u32(data, e)
            if ilt_rva == 0:
                break
            dll = cstr(data, r2f(u32(data, e + 12)))
            lookup = ilt_rva
            names = []
            while True:
                t = u32(data, r2f(lookup))
                if t == 0:
                    break
                if not t & 0x80000000:
                    names.append(cstr(data, r2f(t + 2)))
                else:
                    names.append("#%d" % (t & 0xFFFF))
                lookup += 4
            keep = [n for n in names if pat is None or pat.search(n)]
            if keep:
                print("  DLL %s (%d names, showing %d)" % (dll, len(names), len(keep)))
                for n in keep:
                    print("    %s" % n)
            i += 1
    elif show_i:
        print("IMPORTS none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
