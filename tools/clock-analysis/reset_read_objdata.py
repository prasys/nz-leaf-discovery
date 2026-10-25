#!/usr/bin/env python3
"""reset_read_objdata.py -- read-only PE .data reader for G214 OBJDLL.dll.

Dumps the OBJDLL object-class restore/store table entries for selected class
IDs so the restore-mode fields used by FUN_40e229d0/FUN_40e22ce8 can be
confirmed statically.  Read-only; parses the extracted module file only.

Usage: python3 -I reset_read_objdata.py <path-to-OBJDLL.dll>
"""
import struct
import sys

# Runtime VAs of the four table base pointers referenced by OBJDLL code.
# DAT_40e22a7c = commit(SRAM) restore table, DAT_40e22d54 = stored table,
# DAT_40e22ca8 = commit lock table, DAT_40e22e64 = save table.
PTRS = {
    "restore_table(22a7c)": 0x40E22A7C,
    "commitlock_table(22ca8)": 0x40E22CA8,
    "stored_table(22d54)": 0x40E22D54,
    "save_table(22e64)": 0x40E22E64,
    "status_table(22f74)": 0x40E22F74,
    "write_table(22b44)": 0x40E22B44,
    "write2_table(22bf4)": 0x40E22BF4,
    "write3_table(22dcc)": 0x40E22DCC,
    "setstatus_table(22fe4)": 0x40E22FE4,
    "readstatus_table(22f04)": 0x40E22F04,
}
ENTRY = 0x38
CLASSES = [0, 2, 3, 7, 9, 10]  # include the Time class (2)


def load_headers(data):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew : e_lfanew + 4] == b"PE\0\0", "not a PE file"
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt = coff + 20
    imagebase = struct.unpack_from("<I", data, opt + 28)[0]
    sections = []
    off = opt + struct.unpack_from("<H", data, coff + 16)[0]
    for i in range(nsec):
        s = off + i * 40
        name = data[s : s + 8].rstrip(b"\0").decode()
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, s + 8)
        sections.append((name, va, vsize, rawptr, rawsize))
    return imagebase, sections


def va2off(va, imagebase, sections):
    rva = va - imagebase
    for name, s_va, s_vsize, s_raw, s_rawsize in sections:
        if s_va <= rva < s_va + max(s_vsize, s_rawsize):
            if rva - s_va < s_rawsize:
                return s_raw + (rva - s_va)
    return None


def rd32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], "rb") as f:  # read-only
        data = f.read()
    imagebase, sections = load_headers(data)
    print(f"imagebase=0x{imagebase:08x}")
    for label, pva in PTRS.items():
        off = va2off(pva, imagebase, sections)
        table = rd32(data, off)
        toff = va2off(table, imagebase, sections)
        print(f"\n{label}: ptr@0x{pva:08x} -> 0x{table:08x}")
        if toff is None:
            print("  <unmapped>")
            continue
        for cls in CLASSES:
            e = toff + cls * ENTRY
            mode = rd32(data, e)
            idx = rd32(data, e + 0x34)
            words = [rd32(data, e + i * 4) for i in range(14)]
            print(
                f"  class {cls:2d}: mode={mode} idx={idx} words="
                + " ".join(f"{w:08x}" for w in words)
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
