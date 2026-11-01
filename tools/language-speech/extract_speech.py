#!/usr/bin/env python3
"""Rebuild Speech.exe, correctly reading each page's full LZX stream header.

Run with python3 -I. Input is a read-only unpacked G214 ROM, not executable code.
The existing CE extractor skips the first four LZX bytes as a magic signature;
these actually contain the Intel E8 translation flag and file size. This scoped
adapter keeps that header and does not modify existing extracted ROMs.
"""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ce-extract"))
import ceromx
import cecompress
import lzx


def decompress(data):
    size = cecompress.u24(data, 0)
    if size > 64 * 1024 * 1024:
        raise ValueError("CE object too large")
    count = (size + 4095) // 4096
    start = 3 + 3 * count
    output = bytearray()
    for i in range(count):
        end = cecompress.u24(data, 3 + 3 * i)
        if not start + 16 <= end <= len(data):
            raise ValueError("invalid CE page extent")
        hlen, raw, packed, repeated = struct.unpack_from("<4I", data, start)
        want = min(4096, size - len(output))
        if (hlen, raw, repeated, start + hlen + packed) != (16, want, want, end):
            raise ValueError("invalid CE page header")
        body = data[start + 16:end]
        # Position zero is essential: 5b 80 80 8d is not a separate magic.
        page, consumed = lzx.decompress(body, want, 16, 0)
        if consumed > len(body) + 2:
            raise ValueError("LZX input overrun")
        output.extend(page)
        start = end
    if start != len(data):
        raise ValueError("trailing CE object bytes")
    return bytes(output)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    if args.output.resolve() == args.rom.resolve():
        ap.error("output must differ from input")
    speech = Path(os.environ.get("NISSAN_ROOT", Path.home() / "nissan")).expanduser() / "work/language-speech"
    if not args.output.resolve().is_relative_to(speech.resolve()):
        ap.error(f"output must be under {speech}/")
    rom = ceromx.Rom(args.rom.read_bytes())
    mod = next(m for m in rom.modules if rom.cstr(m[4]) == "Speech.exe")
    e32 = struct.unpack(ceromx.E32_FMT, rom.blob(mod[5], struct.calcsize(ceromx.E32_FMT)))
    units = [(e32[11 + 2*k], e32[12 + 2*k]) for k in range(ceromx.ROM_EXTRA)]
    sections = []
    for i in range(e32[0]):
        o = struct.unpack(ceromx.O32_FMT, rom.blob(mod[6] + i * 24, 24))
        raw = rom.blob(o[3], o[2])
        if o[5] & ceromx.IMAGE_SCN_COMPRESSED:
            raw = decompress(raw)
        sections.append((ceromx.section_name(o, units, i), o, raw))
    data = ceromx.build_pe(rom.hdr["usCPUType"], e32, sections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as f:
        f.write(data)
    print(f"{hashlib.sha256(data).hexdigest()}  {args.output} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
