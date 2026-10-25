#!/usr/bin/env python3 -I
"""execution-: read UTF-16 strings at AppLaunch.dll VAs and print PE sections.

Read-only helper. Parses the PE properly: e_lfanew at 0x3c, section count in
the COFF header (pe+6), optional header at pe+24, section table at
pe+24+SizeOfOptionalHeader (read from pe+20). Strings are contiguous
UTF-16LE in the file: decode data[fo:end] directly (no stride slicing)."""
import struct
import sys
from pathlib import Path


def main(path, vas):
    data = Path(path).read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[pe:pe + 4] == b"PE\0\0", "bad PE signature"
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    imagebase = struct.unpack_from("<I", data, opt + 28)[0]
    sec_off = opt + opt_size
    secs = []
    for i in range(nsec):
        name, vsize, vaddr, rawsize, rawptr = struct.unpack_from("<8sIIII", data, sec_off + 40 * i)
        secs.append((name.rstrip(b"\0").decode(errors="replace"), vsize, vaddr, rawsize, rawptr))
        print(f"sec {secs[-1][0]} vsize={vsize:#x} va={vaddr:#x} raw={rawsize:#x} ptr={rawptr:#x}")
    print(f"ImageBase {imagebase:#x}")

    def va2fo(va):
        rva = va - imagebase
        for _, vsize, vaddr, rawsize, rawptr in secs:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawptr + (rva - vaddr)
        return None

    def utf16(va):
        fo = va2fo(va)
        if fo is None or fo < 0 or fo >= len(data) - 1:
            return None
        end = fo
        while end + 1 < len(data) and (data[end] or data[end + 1]):
            end += 2
        return data[fo:end].decode("utf-16-le", "replace")

    def u32(va):
        fo = va2fo(va)
        return struct.unpack_from("<I", data, fo)[0] if fo is not None else None

    for va in vas:
        target = u32(va)
        if target is not None and utf16(target):
            print(f"pool {va:#x} -> {target:#x} {utf16(target)!r}")
        else:
            print(f"{va:#x} {utf16(va)!r}")


if __name__ == "__main__":
    main(sys.argv[1], [int(v, 0) for v in sys.argv[2:]])
