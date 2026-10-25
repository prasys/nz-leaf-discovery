#!/usr/bin/env python3 -I
"""Extract a Windows CE XIP/NK image (ROMHDR at the ECEC pointer) — dumprom/eimgfs style.

Usage:
    python3 -I tools/ce-extract/ceromx.py <image.bin> [outdir] [--only name,name,...]

Default outdir: $NISSAN_ROOT/work/ce-extract/<image stem>/
Writes:
    modules/<name>   PE files rebuilt from e32_rom/o32_rom (+ decompressed sections)
    files/<name>     FILESentry bodies (decompressed when nCompFileSize != nRealFileSize)
    listing.txt      ROMHDR, modules (e32/o32), files, decompression status

Read-only on the input; nothing is executed.
"""

import datetime
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cecompress  # noqa: E402

ROMHDR_FMT = "<17I2HI2I"
ROMHDR_NAMES = ("dllfirst dlllast physfirst physlast nummods ulRAMStart ulRAMFree ulRAMEnd "
                "ulCopyEntries ulCopyOffset ulProfileLen ulProfileOffset numfiles ulKernelFlags "
                "ulFSRamPercent ulDrivglobStart ulDrivglobLen usCPUType usMiscFlags pExtensions "
                "ulTrackingStart ulTrackingLen").split()
TOC_FMT = "<8I"      # attr, ftlo, fthi, size, name, e32, o32, load
FILES_FMT = "<7I"    # attr, ftlo, fthi, real, comp, name, load
# CE6/7 e32_rom: objcnt, imageflags, entryrva, vbase, subsysmaj, subsysmin, stackmax, vsize,
# sect14rva, sect14size, timestamp, 9 x (rva,size), subsys
E32_FMT = "<HHIIHHIIIII18IH"
O32_FMT = "<6I"      # vsize, rva, psize, dataptr, realaddr, flags
ROM_EXTRA = 9
IMAGE_SCN_COMPRESSED = 0x2000

CPU_NAMES = {0x1C0: "ARM", 0x1C2: "THUMB (ARMv4I)", 0x1C4: "ARMNT", 0x1A6: "SH4", 0x1A8: "SH5",
             0x14C: "I386", 0x166: "R4000"}


def filetime(lo, hi):
    t = (hi << 32) | lo
    try:
        return (datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=t // 10)).strftime("%Y-%m-%d %H:%M:%S")
    except OverflowError:
        return "%#x" % t


class Rom:
    def __init__(self, data):
        self.d = data
        if data[0x40:0x44] != b"ECEC":
            raise ValueError("no ECEC signature at 0x40")
        self.romhdr_va, self.romhdr_off = struct.unpack_from("<II", data, 0x44)
        self.base = self.romhdr_va - self.romhdr_off
        vals = struct.unpack_from(ROMHDR_FMT, data, self.romhdr_off)
        self.hdr = dict(zip(ROMHDR_NAMES, vals))
        p = self.romhdr_off + struct.calcsize(ROMHDR_FMT)
        self.modules = []
        for _ in range(self.hdr["nummods"]):
            self.modules.append(struct.unpack_from(TOC_FMT, data, p))
            p += 32
        self.files = []
        for _ in range(self.hdr["numfiles"]):
            self.files.append(struct.unpack_from(FILES_FMT, data, p))
            p += 28

    def off(self, va):
        o = va - self.base
        if not 0 <= o < len(self.d):
            raise ValueError("VA %#x outside image" % va)
        return o

    def cstr(self, va):
        o = self.off(va)
        return self.d[o:self.d.index(b"\0", o)].decode("latin1")

    def blob(self, va, n):
        o = self.off(va)
        return self.d[o:o + n]


def section_name(o, e32units, idx):
    vsize, rva, psize, dataptr, realaddr, flags = o
    for unit, nm in ((2, ".rsrc"), (3, ".pdata"), (5, ".reloc")):
        if e32units[unit][0] and e32units[unit][0] == rva:
            return nm
    if flags & 0x20:
        return ".text"
    if flags & 0x80000000:
        return ".data"
    if flags & 0x40:
        return ".rdata"
    return ".sec%d" % idx


def build_pe(machine, e32, sections):
    """sections: list of (name, o32 tuple, raw bytes)."""
    (objcnt, imageflags, entryrva, vbase, ssmaj, ssmin, stackmax, vsize,
     s14rva, s14size, timestamp) = e32[:11]
    units = [(e32[11 + 2 * k], e32[12 + 2 * k]) for k in range(ROM_EXTRA)]
    subsys = e32[11 + 2 * ROM_EXTRA]
    falign = 0x200
    nsec = len(sections)
    hdr_size = 0x80 + 4 + 20 + 0xE0 + 40 * nsec
    hdr_size = (hdr_size + falign - 1) & ~(falign - 1)
    dirs = [(0, 0)] * 16
    for k in range(ROM_EXTRA):
        dirs[k] = units[k]
    dirs[14] = (s14rva, s14size)
    # romimage drops sections such as .reloc but keeps their directory entry;
    # zero any directory that no section's data covers so PE loaders don't choke
    for k, (rva, size) in enumerate(dirs):
        if rva and not any(o[1] <= rva < o[1] + max(len(raw), o[0]) for _, o, raw in sections):
            dirs[k] = (0, 0)
    sec_table = b""
    body = b""
    fptr = hdr_size
    size_code = size_idata = size_udata = 0
    base_code = base_data = 0
    for name, o, raw in sections:
        osize, rva, psize, dataptr, realaddr, flags = o
        flags &= ~IMAGE_SCN_COMPRESSED
        rawsz = (len(raw) + falign - 1) & ~(falign - 1)
        if flags & 0x20:
            size_code += rawsz
            base_code = base_code or rva
        elif flags & 0x40:
            size_idata += rawsz
            base_data = base_data or rva
        elif flags & 0x80:
            size_udata += osize
        sec_table += struct.pack("<8sIIIIIIHHI", name.encode()[:8], osize, rva, rawsz,
                                 fptr if rawsz else 0, 0, 0, 0, 0, flags)
        body += raw + b"\0" * (rawsz - len(raw))
        fptr += rawsz
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    coff = struct.pack("<HHIIIHH", machine, nsec, timestamp, 0, 0, 0xE0, imageflags)
    opt = struct.pack("<HBBIIIIIIIIIHHHHHHIIIIHHIIIIII",
                      0x10B, 0, 0, size_code, size_idata, size_udata, entryrva, base_code, base_data,
                      vbase, 0x1000, falign, ssmaj, ssmin, 0, 0, ssmaj, ssmin, 0,
                      vsize, hdr_size, 0, subsys, 0, stackmax, 0x1000, 0x100000, 0x1000, 0, 16)
    opt += b"".join(struct.pack("<II", *dd) for dd in dirs)
    hdr = bytes(dos) + b"PE\0\0" + coff + opt + sec_table
    return hdr + b"\0" * (hdr_size - len(hdr)) + body


def safe_name(n):
    n = n.replace("/", "_").replace("\\", "_")
    return n if n not in ("", ".", "..") else "_" + n


def main(argv):
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = {x.lower() for x in argv[i + 1].split(",")}
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    img = argv[1]
    stem = os.path.basename(img)
    for pre in ("slot",):
        if stem.startswith(pre):
            stem = stem.split("_", 1)[1]
    stem = stem.replace("_nk.nb0.bin", "").replace(".bin", "")
    root = os.environ.get("NISSAN_ROOT", os.path.expanduser("~/nissan"))
    outdir = argv[2] if len(argv) > 2 else os.path.join(root, "work", "ce-extract", stem)
    with open(img, "rb") as f:
        data = f.read()
    rom = Rom(data)
    cpu = rom.hdr["usCPUType"]
    os.makedirs(os.path.join(outdir, "modules"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "files"), exist_ok=True)
    L = []
    L.append("image %s (%d bytes)" % (img, len(data)))
    L.append("ROMHDR va %#x off %#x base %#x" % (rom.romhdr_va, rom.romhdr_off, rom.base))
    for k in ROMHDR_NAMES:
        L.append("  %-16s %#x" % (k, rom.hdr[k]))
    L.append("  usCPUType -> %s" % CPU_NAMES.get(cpu, "?"))
    errors = 0
    L.append("")
    L.append("MODULES %d" % len(rom.modules))
    for attr, lo, hi, size, namep, e32p, o32p, load in rom.modules:
        name = rom.cstr(namep)
        e32 = struct.unpack_from(E32_FMT, data, rom.off(e32p))
        objcnt, imageflags, entryrva, vbase = e32[:4]
        units = [(e32[11 + 2 * k], e32[12 + 2 * k]) for k in range(ROM_EXTRA)]
        L.append("M %-30s size=%-8d attr=%#06x %s e32=%#x vbase=%#x entry=%#x flags=%#06x subsys=%d ts=%#x"
                 % (name, size, attr, filetime(lo, hi), e32p, vbase, entryrva, imageflags,
                    e32[11 + 2 * ROM_EXTRA], e32[10]))
        if only is not None and name.lower() not in only:
            continue
        secs = []
        for k in range(objcnt):
            o = struct.unpack_from(O32_FMT, data, rom.off(o32p) + 24 * k)
            vsize, rva, psize, dataptr, realaddr, flags = o
            nm = section_name(o, units, k)
            status = "raw"
            raw = b""
            if psize:
                src = rom.blob(dataptr, psize)
                if flags & IMAGE_SCN_COMPRESSED:
                    try:
                        raw, _ = cecompress.decompress(src)
                        status = "lzx %d->%d" % (psize, len(raw))
                    except Exception as e:  # keep going, record the failure
                        errors += 1
                        status = "FAILED: %s" % e
                        raw = src
                else:
                    raw = src[:vsize] if vsize else src
            L.append("    o32 %-7s rva=%#07x vsize=%#07x psize=%#07x data=%#x real=%#x flags=%#010x %s"
                     % (nm, rva, vsize, psize, dataptr, realaddr, flags, status))
            secs.append((nm, o, raw))
        pe = build_pe(cpu, e32, secs)
        with open(os.path.join(outdir, "modules", safe_name(name)), "wb") as f:
            f.write(pe)
    L.append("")
    L.append("FILES %d" % len(rom.files))
    for attr, lo, hi, real, comp, namep, load in rom.files:
        name = rom.cstr(namep)
        line = "F %-36s real=%-9d comp=%-9d attr=%#06x %s load=%#x" % (name, real, comp, attr, filetime(lo, hi), load)
        if only is not None and name.lower() not in only:
            L.append(line)
            continue
        src = rom.blob(load, comp)
        if comp != real:
            try:
                body, _ = cecompress.decompress(src, real)
                line += " lzx ok"
            except Exception as e:
                errors += 1
                body = src
                line += " FAILED: %s" % e
        else:
            body = src
        L.append(line)
        with open(os.path.join(outdir, "files", safe_name(name)), "wb") as f:
            f.write(body)
    L.append("")
    L.append("errors: %d" % errors)
    with open(os.path.join(outdir, "listing.txt"), "w") as f:
        f.write("\n".join(L) + "\n")
    print("wrote %s (%d modules, %d files, %d errors)" % (outdir, len(rom.modules), len(rom.files), errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
