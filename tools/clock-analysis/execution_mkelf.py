#!/usr/bin/env python3 -I
"""execution-: wrap a flat ARM code blob in a minimal ELF32 so llvm-objdump
can disassemble it with real addresses. Read-only helper; no extracted code
is executed."""
import struct
import sys
from pathlib import Path


def wrap(source: Path, target: Path, vaddr: int, machine=40):
    data = source.read_bytes()
    ehsize, phentsize, phnum, shentsize, shnum, shstrndx = 52, 32, 1, 40, 2, 0
    text_off = ehsize + phentsize * phnum
    # section header table offset must be 4-aligned and account for padding
    # after the blob, so it is computed before the ELF header is packed
    shoff = (text_off + len(data) + 3) & ~3
    pad = shoff - (text_off + len(data))
    ident = b"\x7fELF" + bytes([1, 1, 1]) + bytes(9)          # 16 bytes
    tail = struct.pack("<HHIIIII6H",
                       2, machine, 1, 0, ehsize, shoff, 0,
                       ehsize, phentsize, phnum, shentsize, shnum, shstrndx)
    ehdr = ident + tail
    phdr = struct.pack("<8I", 1, text_off, vaddr, vaddr, len(data), len(data), 7, 0x4)
    shdr0 = struct.pack("<10I", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    shdr1 = struct.pack("<10I", 0, 1, 6, vaddr, text_off, len(data),
                        0, 0, 4, 0)  # SHT_PROGBITS, SHF_ALLOC|SHF_EXECINSTR, align 4
    # single write: header + program header + blob + alignment pad + sections
    target.write_bytes(ehdr + phdr + data + bytes(pad) + shdr0 + shdr1)
    print(f"{target} ({len(data)} bytes at VA {vaddr:#x})")


if __name__ == "__main__":
    src, dst, va = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3], 0)
    wrap(src, dst, va)
