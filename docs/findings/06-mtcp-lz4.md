# G214 MTLD/MTCP: LZ4 decompression and WinCE inventory

Analysis is static and read-only. No firmware or extracted code was executed;
no car/card writes or decryption attempts were made. Binary outputs are in
`~/nissan/work/mtcp/`, with hashes in `binaries/MANIFEST.md`.

## Result and corrections

**[confirmed]** MTCP uses independent **standard raw LZ4 blocks**, with a
sector-aligned Clarion table around them. All 11 blocks decode to their declared
lengths and agree byte-for-byte with the installed upstream `liblz4`
`LZ4_decompress_safe` implementation. The stored checksum fields are **SUM4,
not CRC32**: sums of little-endian 32-bit words modulo 2^32 over the compressed
data **including sector padding**. All 11 chunk checks and both MTLD part checks
match (§2–3). This corrects the earlier unknown/LZSS/CRC32 description
in `01-card-layout-and-firmware.md`.

**[confirmed]** Decompressed A followed by unchanged raw B yields a `0x2892200`
byte WinCE ROM: `ECEC` at ROM `+0x40`, ROMHDR at `+0x288F918`, base VA
`0x88840000`, **287 modules and 43 files** (§4). The settings DLL is named
`NaviSetCC.dll`; there is no exact `setcc.dll` entry in this ROM's TOC.

**[likely]** The previously described roughly 16 MiB high-entropy blob largely
consists of ordinary CE-compressed module sections. ROM section records flag
96.6042% of `[container+0xC00000, +0x1C00000)` as compressed storage (§5).
Entropy alone did not establish encryption. The inner CE section codec has not
been decoded or identified by this work.

## 1. Coordinate systems and reproduction

**[confirmed]** The slot header is at card LBA **157696**, byte `0x4D00000`.
The existing carved file starts at the **next sector**, card `0x4D00200`:
its first four bytes are `4d 54 43 50` (`MTCP`). Its length is `0x1D50400`.
The preceding card sector contains `MTLD` at header `+0x70` and `NKOK` at
`+0x1FC`. Descriptor sector offsets are relative to the carved payload, not to
the preceding slot header.

Throughout this note:

- **header** offsets are relative to card `0x4D00000`;
- **container** offsets are relative to the existing MTCP carve;
- **ROM** offsets refer to the reconstructed, decompressed `g214-rom.bin`.

Run from the repo with isolated Python. Source paths can be overridden for
another local copy; extraction defaults to `~/nissan/work/mtcp/`.

```sh
python3 -I tools/mtcp/mtcp.py
python3 -I tools/mtcp/inspect_rom.py ~/nissan/work/mtcp/g214-rom.bin \
  --container ~/nissan/work/raw-areas/slot157696_G214JLNI.066_MTCP.bin \
  > ~/nissan/work/mtcp/rom-inventory.json
python3 -I tools/raw-areas/romhdr.py ~/nissan/work/mtcp/g214-rom.bin \
  > ~/nissan/work/mtcp/g214-rom.romhdr.txt
python3 -I tools/mtcp/test_mtcp.py
```

`--info` verifies without writing; `--force` replaces previously generated
outputs. `--mtcp-file PATH` selects a carve and `--card-image PATH` reads the
descriptor and payload directly from the card image. By default the existing
carve is preferred, with the optional card image (`NISSAN_IMG` or the default
image path) supplying descriptor checks. `--no-card-image` allows carve-only
decoding; part-level descriptor verification is unavailable in that mode.
`--reference PATH` optionally compares the combined bytes before writing; the
local `reference-lz4.bin` is also detected automatically when present.

The JSON inventory lists every module/file, its TOC and name offsets, and each
module's `e32`/`o32` addresses and section storage ranges. The text listing can
also be produced using the pre-existing ROMHDR parser as shown above.

## 2. MTLD descriptor

**[confirmed]** Header `+0x70` begins:

```text
0070: 4d 54 4c 44 02 00 00 00 39 d8 06 28 00 00 00 00
0090: 00 00 00 00 f0 49 00 00 00 e0 93 00 6a 0a e6 b9
00a0: 4d 54 43 50 00 00 00 00 00 00 00 00 00 00 00 00
00b0: f0 49 00 00 92 a0 00 00 00 24 41 01 52 25 21 64
00c0: 00 00 00 00 00 fe 47 01 00 00 00 00 00 00 00 00
```

The count at `+0x74` is 2. Two 32-byte records start at `+0x90`; each has
little-endian u32 fields:

| Record field | Meaning supported by this image |
|---|---|
| +0x00 | Starting sector relative to container |
| +0x04 | Stored sector count |
| +0x08 | Stored byte length |
| +0x0C | SUM4 of the stored part |
| +0x10 | `MTCP` for compressed A, zero for raw B |
| +0x14 | Destination offset within reconstructed ROM |
| +0x18, +0x1C | Zero; semantics unknown |

**[confirmed]** Values and checks:

| Part | Container start | Stored sectors | Stored bytes | SUM4 | ROM destination |
|---|---:|---:|---:|---:|---:|
| A, MTCP | 0 | 0x49F0 | 0x93E000 | 0xB9E60A6A | 0 |
| B, raw | 0x93E000 | 0xA092 | 0x1412400 | 0x64212552 | 0x147FE00 |

**[confirmed]** Part A's checksum covers its table, every compressed chunk and
all chunk padding: `SUM4(container[0:0x93E000]) = 0xB9E60A6A`. B's covers
`container[0x93E000:0x1D50400]` and equals `0x64212552`.
For this slot, their sum also equals the outer header `SUM4` value at `+0x34`,
`0x1E072FBC`, independently reproduced over the entire stored payload. This
single-image observation does not settle the other slots or the header's u16
field at `+0x14`.
**[guess]** Header `+0x78 = 0x2806D839` may be another integrity/version field;
its meaning remains unresolved. Slot-wide checksums belong to
[#11](https://github.com/prasys/nz-leaf-discovery/issues/11).

## 3. MTCP chunk table and raw LZ4

**[confirmed]** Container `+0x00` is `MTCP`, `+0x04` is chunk count 11 and
`+0x08` is nominal expanded chunk size `0x200000`. Entries occupy 32 bytes
starting at `+0x20`. Each entry's first four little-endian u32 values are
`stored_sector_count, expanded_bytes, compressed_bytes, SUM4`; the remaining
16 bytes are zero in all 11 entries. Compressed data begins at `+0x200`.
Advancing by `stored_sector_count * 512` locates the next block.

**[confirmed]** Every checksum in this table matches the sector-padded compressed
range; only the declared compressed byte count is passed to the LZ4 decoder.
Chunks 0–9 expand to `0x200000` bytes, chunk 10 to `0x7FE00`, totaling
`0x147FE00`. The last stored chunk ends exactly at B's start, `0x93E000`.

| Chunk | Table offset | Data offset | Sectors | Compressed bytes | Stored SUM4 |
|---:|---:|---:|---:|---:|---:|
| 0 | 0x20 | 0x200 | 0x86B | 0x10D49F | 0xB79471C1 |
| 1 | 0x40 | 0x10D800 | 0x854 | 0x10A79F | 0xC0F974F7 |
| 2 | 0x60 | 0x218000 | 0x630 | 0xC5EE0 | 0x470C241A |
| 3 | 0x80 | 0x2DE000 | 0x702 | 0xE02CC | 0x4551CAD2 |
| 4 | 0xA0 | 0x3BE400 | 0x768 | 0xECF35 | 0x121E333C |
| 5 | 0xC0 | 0x4AB400 | 0x7DD | 0xFB966 | 0x8A4A6386 |
| 6 | 0xE0 | 0x5A6E00 | 0x655 | 0xCA969 | 0xD39AE2AA |
| 7 | 0x100 | 0x671800 | 0x7C0 | 0xF7E69 | 0x3DAF05F4 |
| 8 | 0x120 | 0x769800 | 0x5B9 | 0xB70D8 | 0x0712CD0C |
| 9 | 0x140 | 0x820A00 | 0x779 | 0xEF1A9 | 0x917D38C8 |
| 10 | 0x160 | 0x90FC00 | 0x172 | 0x2E229 | 0xE8A4F2B9 |

**[confirmed]** The bytes obey the upstream [LZ4 block format](https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md):
the token's high nibble gives literal length and low nibble gives match length
minus four. Nibble 15 uses additional length bytes, continuing while the byte
is 255. Matches use a nonzero little-endian 16-bit backward distance and allow
overlap; each block starts with empty history. The final sequence has literals
only. This is a 65535-byte-distance LZ77 format, rather than a 4 KiB LZSS
flag-bitmap format. There is no LZ4 frame header; MTCP supplies block sizes.

**[confirmed]** First block at container `+0x200` starts `fb 1a 78 8c 05 40 …`:
`fb 1a` means 15+26 = 41 literal bytes, followed by distance `01 00` and a
15-byte match. Its output contains `ECEC` at ROM `+0x40`. As a negative check,
standard CRC32 of chunk 0's expanded bytes is `0x6ED07300`, which does **not**
equal the stored `0xB79471C1`; SUM4 of its compressed padded bytes does.

No further LZO/Yaz0/XPRESS/LZX candidate search is needed for this outer layer:
all chunks decode with standard LZ4 and match an independent implementation.

## 4. Reconstructed WinCE image and modules

**[confirmed]** Concatenation is `expanded_A + unchanged_B`, as indicated by
B's destination field. ROM `+0x40` contains:

```text
0040: 45 43 45 43 18 f9 0c 8b 18 f9 88 02
```

**[confirmed]** ROMHDR VA `0x8B0CF918` minus ROMHDR offset `0x0288F918` gives
base `0x88840000`. ROMHDR `physfirst/physlast` are `0x88840000/0x8B0D2200`,
matching the reconstructed size `0x2892200`. Module count at ROMHDR `+0x10`
is `0x11F`; file count at `+0x30` is `0x2B`. The 84-byte ROMHDR is followed
by 32-byte module records, then 28-byte file records. ROMHDR CPU field at
`+0x44` is `0x01C2`; this is an additional observation for
the CPU identification in `05-ce-rom-extract.md` §3, not a new
SoC identification.

**[confirmed]** Selected TOC entries (all offsets below refer to the ROM):

| Module | TOC record | Name bytes | e32 header | o32 section table |
|---|---:|---:|---:|---:|
| timezones.dll | 0x288FB4C | 0xA41FE8 | 0x704EF0 | 0x263FC8 |
| OBJDLL.dll | 0x2890C6C | 0x1EEFEC | 0x1411998 | 0x1411A08 |
| ScreenStateCC.dll | 0x2890E6C | 0x2B7FE4 | 0xAFF7C0 | 0xAFF830 |
| NaviSetCC.dll | 0x28915EC | 0x965FC4 | 0x12AE08 | 0x12AE78 |
| Navi.exe | 0x289170C | 0xB4CFF4 | 0x2A780 | 0x12AFA8 |
| EvTimerCC.dll | 0x2891C6C | 0x902FE4 | 0x6C1CDC | 0x6C1D4C |
| Vehicle.exe | 0x2891CCC | 0x902FF4 | 0x6C1F4C | 0x13531B8 |
| Consult.exe | 0x2891D2C | 0xB8FF0 | 0x13533A0 | 0x1353410 |

**[confirmed]** Removing the outer MTCP layer does not produce standalone PE
files. Modules retain WinCE `e32_rom`/`o32_rom` metadata and some sections remain
CE-compressed. For example, Navi.exe's section 0 (`o32` at ROM `0x12AFA8`)
has virtual size `0x7244F0`, stored size `0x309440`, data VA `0x8A60D534`
(ROM `0x1DCD534`) and flags `0x60002020`. Its section 1 has virtual size
`0x2E5F338` but stored size `0xDD77`. `EvTimerCC.dll` has uncompressed code
at ROM `0x1578000` (section 0 data VA `0x89DB8000`), plus compressed data
sections. Reconstructing full PE modules is separate work.

## 5. High-entropy raw region: characterization only

**[confirmed]** Container range `[0xC00000, 0x1C00000)` is 16 MiB and maps to
ROM `[0x1741E00, 0x2741E00)`. Shannon byte entropy for the complete range is
**7.966567 bits/byte**. Its first 32 bytes at container `0xC00000` are zeros,
so the old approximate boundary does not mark a single recognizable blob
header. One-MiB windows starting `0xD00000` through `0x1B00000` range from
7.928524 to 7.981805 bits/byte. The `0xC00000` window is 7.899717 and the
following `0x1C00000` window drops to 7.117314. Exact windows, hashes and first
32 bytes are reproducible in `rom-inventory.json`.

**[confirmed]** Of 113 module section records intersecting that 16 MiB range,
112 have bit `0x2000` set. Its documented meaning is `IMAGE_SCN_COMPRESSED`
in the [dumprom implementation](https://github.com/pinkavaj/romtools/blob/master/dumprom.cpp).
Their union covers **16,207,493 bytes (96.6042%)** of the range. The inventory
unions overlapping storage spans rather than double-counting them.

**[confirmed]** Examples: `ScreenStateCC.dll` section 0 spans ROM
`[0x1A7EE0C, 0x1C4A30A)` with flags `0x60002020`; Navi.exe section 0 spans
`[0x1DCD534, 0x20D6974)` with the same flags. The remaining uncompressed
section intersecting the approximate region is `Consult.exe` section 0,
ROM `[0x1733000, 0x175A000)`, flags `0x68000020`.

**[confirmed]** A signature-byte scan of the 16 MiB range finds no gzip,
ZIP, LZ4-frame, xz, SquashFS or ECEC magic. Five PNG signatures occur at
container `0x12C102E`, `0x12C19BE`, `0x131B69C`, `0x1328A70`, `0x13322AC`;
these hits alone do not establish complete embedded PNG files.
**[likely]** High entropy reflects CE-compressed section storage rather than
one encrypted envelope. Neither the compression flag nor entropy establishes
the inner codec, and neither excludes other transformations. No attempt was
made to decrypt it, recover keys, or decompress these inner sections.

## Validation and remaining work

**[confirmed]** Validation includes all 11 chunk SUM4 checks, both part SUM4
checks, declared expanded sizes, independent liblz4 byte comparison, physical
ROM extent and all 287 module/43 file table bounds. Re-running the existing
ROMHDR parser independently reproduces the module/file counts and names.
The decoder tests cover malformed/truncated LZ4, overlap, output-size limits,
container/checksum failures and write-path protections.

The outer MTCP format is resolved. Header `+0x78` and slot header integrity
remain with [#11](https://github.com/prasys/nz-leaf-discovery/issues/11). Inner CE section decompression/PE reconstruction is the next
step ([#18](https://github.com/prasys/nz-leaf-discovery/issues/18))
before inspecting Navi.exe or compressed settings data; menu/market
gating remains [#19](https://github.com/prasys/nz-leaf-discovery/issues/19).
