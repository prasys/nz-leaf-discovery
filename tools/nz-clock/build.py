#!/usr/bin/env python3 -I
"""Build an OFFLINE unpacked G214 ROM candidate; never writes a card/image.

Accepts only the pinned, unmodified extracted G214 .nb0. Outputs must be a new
directory under $NISSAN_ROOT/work. This does not create a flash-ready SD slot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "ce-extract"))
import ceromx

SOURCE_SHA = "8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a"
ENTRY_VA = 0x40E2C360
CAVE_VA = 0x40E9E1C4
PROLOGUE = bytes.fromhex("30402de90140a0e1")
STOCK_FUNCTION = bytes.fromhex(
    "30402de90140a0e10050b0e10f00000a000054e30d00000a140095e5b67401eb"
    "0000b0e10900000a142095e50000a0e3002084e51c3095e5022083e0002084e5"
    "203095e5023083e0003084e53080bde80100e0e33080bde8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def arm_branch(at, target):
    displacement = target - at - 8
    if displacement % 4 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("ARM branch is unaligned or out of range")
    return struct.pack("<I", 0xEA000000 | ((displacement >> 2) & 0xFFFFFF))


def branch_target(at, instruction):
    word = struct.unpack("<I", instruction)[0]
    if word >> 24 != 0xEA:
        raise ValueError("Expected unconditional ARM branch")
    displacement = word & 0xFFFFFF
    if displacement & 0x800000:
        displacement -= 1 << 24
    return at + 8 + 4 * displacement


def layout(data):
    if sha(data) != SOURCE_SHA:
        raise ValueError("Source SHA256 does not match the reviewed G214 ROM")
    rom = ceromx.Rom(data)
    matches = [m for m in rom.modules if rom.cstr(m[4]).lower() == "objdll.dll"]
    if len(matches) != 1:
        raise ValueError("Expected one OBJDLL module")
    module = matches[0]
    e32 = struct.unpack_from(ceromx.E32_FMT, data, rom.off(module[5]))
    o32_offset = rom.off(module[6])
    section = struct.unpack_from(ceromx.O32_FMT, data, o32_offset)
    vsize, rva, psize, dataptr, realaddr, flags = section
    if (e32[3], vsize, rva, psize, realaddr, flags) != (
            0x40E00000, 0x9D1C3, 0x1000, 0x9E000, 0x40E01000, 0x68000020):
        raise ValueError("Unexpected OBJDLL raw .text layout")
    raw_offset = rom.off(dataptr)
    entry_offset = raw_offset + ENTRY_VA - realaddr
    cave_offset = raw_offset + CAVE_VA - realaddr
    if data[entry_offset:entry_offset + len(STOCK_FUNCTION)] != STOCK_FUNCTION:
        raise ValueError("Stock function bytes do not match the reviewed disassembly")
    if cave_offset != raw_offset + ((vsize + 3) & ~3):
        raise ValueError("Cave is not at the aligned virtual section end")
    capacity = raw_offset + psize - cave_offset
    return rom, module, e32, section, o32_offset, entry_offset, cave_offset, capacity


def patch(data, payload):
    rom, module, e32, section, o32off, entryoff, caveoff, capacity = layout(data)
    if not payload or len(payload) > capacity:
        raise ValueError("Empty payload or payload does not fit verified padding")
    new_vsize = CAVE_VA - section[4] + len(payload)
    # romimage packs other modules' metadata beyond this section's virtual end.
    # Split off only the last virtual page into a new o32 section, copying its
    # declared bytes to a new physical page with owned padding for the payload.
    # All runtime addresses and the overall virtual page count stay unchanged.
    raw_offset = rom.off(section[3])
    new_raw_offset = (len(data) + 0xfff) & ~0xfff
    split = section[0] & ~0xfff
    tail_bytes = section[0] - split
    new_page = bytearray(0x1000)
    new_page[:tail_bytes] = data[raw_offset + split:raw_offset + section[0]]
    cave_relative = CAVE_VA - section[4] - split
    new_page[cave_relative:cave_relative + len(payload)] = payload
    new_entryoff = entryoff
    new_caveoff = new_raw_offset + cave_relative
    table_offset = new_raw_offset + 0x1000
    sections = [struct.unpack_from(ceromx.O32_FMT, data, o32off + 24 * i)
                for i in range(e32[0])]
    first = (split, section[1], split, section[3], section[4], section[5])
    last = (cave_relative + len(payload), section[1] + split, 0x1000,
            rom.base + new_raw_offset, section[4] + split, section[5])
    new_sections = [first, last] + sections[1:]
    table = b"".join(struct.pack(ceromx.O32_FMT, *item) for item in new_sections)
    result = bytearray(data) + bytearray(new_raw_offset - len(data)) + new_page + table
    result.extend(b"\0" * (-len(result) % 512))
    result[entryoff:entryoff + 4] = arm_branch(ENTRY_VA, CAVE_VA)
    e32off = rom.off(module[5])
    struct.pack_into("<H", result, e32off, len(new_sections))
    toc_offset = rom.romhdr_off + struct.calcsize(ceromx.ROMHDR_FMT) + rom.modules.index(module) * 32
    struct.pack_into("<I", result, toc_offset + 24, rom.base + table_offset)
    physlast_offset = rom.romhdr_off + 12
    if rom.hdr["physlast"] != rom.base + len(data):
        raise ValueError("Original ROM physical end does not match file length")
    struct.pack_into("<I", result, physlast_offset, rom.base + len(result))
    expected = [(entryoff, entryoff + 4), (e32off, e32off + 2),
                (toc_offset + 24, toc_offset + 28), (physlast_offset, physlast_offset + 4)]
    # All other pre-existing bytes, including the old o32 table, are preserved.
    changes = sum(a != b for a, b in zip(data, result))
    outside = 0
    position = 0
    for start, end in sorted(expected):
        outside += data[position:start] != result[position:start]
        position = end
    outside += data[position:] != result[position:len(data)]
    if outside:
        raise ValueError("Unexpected changes outside the approved patch ranges")
    if branch_target(ENTRY_VA, result[new_entryoff:new_entryoff + 4]) != CAVE_VA:
        raise ValueError("Entry branch verification failed")
    if result[new_caveoff:new_caveoff + len(payload)] != payload:
        raise ValueError("Payload read-back failed")
    report = {
        "status": "OFFLINE_UNPACKED_ROM_CANDIDATE_NOT_FLASH_READY",
        "source_sha256": sha(data), "output_sha256": sha(result),
        "payload_sha256": sha(payload), "payload_bytes": len(payload),
        "entry_va": hex(ENTRY_VA), "entry_rom_offset": hex(new_entryoff),
        "cave_va": hex(CAVE_VA), "cave_rom_offset": hex(new_caveoff),
        "cave_capacity": capacity, "o32_rom_offset": hex(table_offset),
        "original_o32_rom_offset": hex(o32off),
        "original_text_rom_offset": hex(raw_offset), "new_tail_page_rom_offset": hex(new_raw_offset),
        "tail_page_va": hex(section[4] + split), "text_split_offset": hex(split),
        "old_section_count": e32[0], "new_section_count": len(new_sections),
        "original_rom_bytes": len(data), "candidate_rom_bytes": len(result),
        "old_text_virtual_size": hex(section[0]), "new_text_total_virtual_size": hex(new_vsize),
        "changed_existing_bytes": changes, "appended_bytes": len(result) - len(data),
        "allowed_ranges": [[hex(a), hex(b)] for a, b in expected],
        "limitations": ["MTCP/MTLD and outer slot packaging not produced",
                        "No boot, dash, VCM, or timer behaviour verified on hardware",
                        "CE remains in its stock timezone; app computes NZ rules directly",
                        "Rules valid for 2008..2099 only; other dates use stock calculation"],
    }
    return bytes(result), report


def find_tool(name, fallback):
    found = shutil.which(name) or (fallback if Path(fallback).is_file() else None)
    if not found:
        raise ValueError(f"Missing {name}; install LLVM/LLD or put it on PATH")
    return found


def main():
    root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=root / "work/ce-extract/G214JLNI.066.nb0")
    parser.add_argument("--out", type=Path, required=True, help="new directory under $NISSAN_ROOT/work")
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    work = root / "work"
    try:
        if not out.is_relative_to(work) or out == work:
            raise ValueError("Output directory must be a new child under $NISSAN_ROOT/work")
        source = args.rom.expanduser().resolve()
        with source.open("rb") as stream:
            data = stream.read()
        layout(data)  # Fail before building or creating output for any unknown source.
        clang = find_tool("clang", "/usr/bin/clang")
        linker = find_tool("ld.lld", "/opt/homebrew/opt/lld/bin/ld.lld")
        objcopy = find_tool("llvm-objcopy", "/opt/homebrew/opt/llvm/bin/llvm-objcopy")
        objdump = find_tool("llvm-objdump", "/opt/homebrew/opt/llvm/bin/llvm-objdump")
        out.mkdir(parents=True, exist_ok=False)
        common = [clang, "--target=armv7-none-eabi", "-mcpu=cortex-a9", "-marm", "-mfloat-abi=soft",
                  "-Oz", "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
                  "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-pic",
                  "-fno-pie", "-fno-addrsig", "-Wall", "-Wextra", "-Werror"]
        commands = [common + ["-c", str(HERE / "clock.c"), "-o", str(out / "clock.o")],
                    common + ["-c", str(HERE / "entry.S"), "-o", str(out / "entry.o")],
                    [linker, "-T", str(HERE / "payload.ld"), "--build-id=none", "-o",
                     str(out / "payload.elf"), str(out / "entry.o"), str(out / "clock.o")],
                    [objcopy, "-O", "binary", "--only-section=.text",
                     str(out / "payload.elf"), str(out / "payload.bin")]]
        for command in commands:
            subprocess.run(command, check=True, cwd=HERE)
        payload = (out / "payload.bin").read_bytes()
        result, report = patch(data, payload)
        with (out / "G214-NZ-candidate.nb0").open("xb") as stream:
            stream.write(result)
        disassembly = subprocess.check_output([objdump, "-d", "--no-show-raw-insn", str(out / "payload.elf")], text=True)
        (out / "payload-disassembly.txt").write_text(disassembly)
        report["commands"] = commands
        report["source_files"] = {name: sha((HERE / name).read_bytes())
                                  for name in ("clock.c", "clock.h", "entry.S", "payload.ld", "build.py")}
        report["tools"] = {name: subprocess.check_output([path, "--version"], text=True).splitlines()[0]
                           for name, path in (("clang", clang), ("lld", linker), ("objcopy", objcopy))}
        (out / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k not in ("commands", "source_files")}, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build refused/failed: {error}\n")


if __name__ == "__main__":
    main()
