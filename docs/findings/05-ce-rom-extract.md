# CE ROM extraction, compression and CPU (issues #2, #5, head start on #3)

Tools: `tools/ce-extract/` (stdlib-only, run with `python3 -I`):

| tool | what |
|---|---|
| `ceromx.py <image> [outdir] [--only a,b]` | Parses ROMHDR → TOC (modules) → FILES. Rebuilds a PE for every module from `e32_rom`/`o32_rom`, decompresses sections and files, and writes `listing.txt` |
| `cecompress.py` | Block wrapper of the CE romimage compressor (see §2) |
| `lzx.py` | Pure-Python LZX decoder (port of libmspack `lzxd` logic) |
| `cehive.py <hive> [--grep RE] [--path PREFIX]` | Dumps CE registry hives (`boot.hv`, `default.hv`, `user.hv`) |

Output: `$NISSAN_ROOT/work/ce-extract/<image>/{modules,files,listing.txt}` plus `*.hv.txt` dumps. Hashes of the priority files are in `binaries/MANIFEST.md`.

```sh
R=~/nissan/work/raw-areas
python3 -I tools/ce-extract/ceromx.py $R/slot749568_PM13XKNI.039_nk.nb0.bin   # ~7 s
python3 -I tools/ce-extract/ceromx.py $R/slot667648_UP14XNNI.139_nk.nb0.bin   # ~4 s
python3 -I tools/ce-extract/ceromx.py $R/slot065536_G314JLNI.066.bin
python3 -I tools/ce-extract/cehive.py ~/nissan/work/ce-extract/PM13XKNI.039/files/default.hv --path "HKEY_LOCAL_MACHINE\\Time Zones"
```

## 1. Result

| image | ROMHDR (va / base) | modules | files | LZX sections | LZX files | errors |
|---|---|---|---|---|---|---|
| PM13XKNI.039 (main OS) | 0x8927A06C / 0x88000000 | 246 | 25 | 598 | 12 | 0 |
| UP14XNNI.139 (updater) | 0x898E028C / 0x88000000 | 213 | 26 | 412 | 13 | 0 |
| G314JLNI.066 (XIP region) | 0x8BA5E4A4 / 0x8B8D0000 | 17 | 0 | 30 | 0 | 0 |

Priority targets **[confirmed]**:
- `navdrv.dll`: PM13 and UP14. In PM13 the `.text` section is LZX (17700 → 45026 bytes). After decompression it contains `NavDrv >> GPS:SetTimeZoneFromSystem SetTimeZoneInformation ret = %d, Error = %d`, `Tokyo Standard Time`, `Tokyo Daylight Time`. So the PM13 (main OS) driver has the same hard-coded Tokyo TZ as UP14. vbase 0xEEDF0000, entry RVA 0x5100.
- `timezones.dll`: PM13 only. Resource-only (entry 0); `.rsrc` holds the MUI strings that the `Time Zones` registry entries reference (`timezones.dll,#NNNNN`).
- `VSramSD.dll`: PM13 and UP14.
- `boot.hv`, `default.hv`, `user.hv`: both images, all decompressed (§4).
- `objdll.dll`: **not in PM13, UP14 or G314**. The only references are import-name strings inside G214JLNI (the MTCP slot), so the module itself lives in G214's MTCP-compressed part (issue #6). G214's decompressed content also uses this LZX block format (10,654 `5B 80 80 8D` magics in the slot), and `ECEC` appears at +0x237 of its first chunk. So once #6's outer layer is reversed, `ceromx.py` should be able to extract it **[likely]**.

## 2. Compression: CE romimage LZX — [confirmed]

Modules mark compressed sections with `o32_flags & 0x2000` (IMAGE_SCN_COMPRESSED). Compressed files have `nCompFileSize < nRealFileSize`, and their TOC attr includes 0x800. Both use the same container:

```
+0   u24 uncompressed size S
+3   u24 end offset of block 0 .. block n-1   (n = ceil(S/4096), offsets from +0)
block: u32 0x10 | u32 raw (0x1000, last shorter) | u32 comp (incl. magic) | u32 raw
       5B 80 80 8D  + raw LZX bitstream
```
user.hv (PM13, load VA 0x89011F38) as an example:
```
00 70 00 | dc 00 00  26 01 00  70 01 00  ba 01 00  04 02 00  e0 06 00  da 09 00     S=0x7000, 7 block ends, last = 0x9DA = nCompFileSize
10 00 00 00  00 10 00 00  b4 00 00 00  00 10 00 00 | 5b 80 80 8d | 01 10 01 00 ...
```
The first LZX word 0x1001 decodes MSB-first as E8 bit = 0, block type = 1 (verbatim), size = 0x001000.

- **Variant: LZX with a 2^16 window (32 position slots), Intel E8 translation off, and fresh Huffman/R0–R2 state per 4 KiB block.** Windows 15 and 20–21 fail with an index error, and 17–19 with an over-subscribed tree. Window 16 consumes each block to exactly its recorded end.
- XPRESS (plain LZ77 / LZ77+Huffman) does not fit. The 180-byte block above is too small to hold a 256-byte Huffman table, and the first flag word reads as a match.
- Verification: some modules are LZX in PM13 but stored raw in UP14 with the same e32 timestamp (regenum, kbdhid, toolhelp, conshid, MouHid, errhandapi, ActivateCtlDriver, oalioctl). Their decompressed sections match the raw copies everywhere except 32-bit words that differ by exactly the vbase delta (e.g. 0xFFFB0000 = 0xEFCC0000 − 0xEFD10000) or by small constant import-thunk deltas (0x16DC, 0x8BC). This is the expected relocation difference, so the decoded bytes are correct.

### PE rebuild notes
- `e32_rom` (CE 6/7 layout, 112 bytes) carries objcnt, imageflags, entry RVA, vbase, subsystem version, stack, vsize, sect14, timestamp, 9 `{rva,size}` units and subsys. All modules show subsystem 9 (WINDOWS_CE_GUI) with subsystem version 7.0.
- **`e32_rom` has no Machine field.** Like dumprom, the rebuilt PE takes Machine from ROMHDR `usCPUType`. So the PE Machine field is not independent evidence for #5 (see §3).
- romimage drops `.reloc` but keeps the FIX directory entry. The rebuild zeroes any data directory that no section covers, which Ghidra needs.
- Section names are guessed (`.text`/`.data`/`.rdata`/`.pdata`/`.rsrc`) from flags and directories. XIP data sections have `o32_realaddr` in RAM (e.g. 0x8D300000) and their initial image in ROM at `o32_dataptr`. The rebuild uses the ROM copy.

## 3. CPU architecture (#5) — ARM Cortex-A9, not SH-4A [confirmed]

| evidence | where |
|---|---|
| ROMHDR `usCPUType = 0x1C2` (IMAGE_FILE_MACHINE_THUMB, which is how CE labels **ARMV4I** builds) | all three images, `listing.txt` |
| nk.exe (OAL) UTF-16 strings `Cortex-A9` (+0x5464), `R8A7778` (+0x5478), `Renesas Electronics R0P7778A00020S` (+0x5488), `Renesas Electronics` (+0x20E0) | PM13 `modules/nk.exe` |
| nk.exe entry `00 00 00 eb / cc 1b 00 ea / d3 00 a0 e3 / 00 f0 21 e1` = `bl; b; mov r0,#0xD3; msr cpsr_c,r0` (ARM reset into SVC mode with IRQ/FIQ off) | PM13 nk.exe RVA 0x1000 |
| Every sampled `.text` is 32-bit ARM mode: 47–68 % of words have cond=AL; `stmfd sp!,{…,lr}` prologues: navdrv 94, coredll 1726. Thumb `push {…,lr}`/`bx lr` and the SH-4 prologue `sts.l pr,@-r15` (0x4F22) are at noise level (0 for SH) | navdrv, VSramSD, coredll, nk.exe, `*_SH4A.dll`, `*_VPU5HD.dll` |
| ARMv7-only barriers in the OAL: 8× `dsb`, 7× `isb` (0xF57FF04x/0xF57FF06F) | nk.exe |
| BSP path `c:\wince700\platform\argo\...`. The OS is **Windows Embedded Compact 7**; the platform is named "argo" | `AACEncoderFilter_SH4A.dll` strings |
| Platform identity `HKLM\Platform\Name = "Clarion GPF AV-Navi Platform"`, USB product "Clarion 12AVN GPF - DCU IF" | PM13 default.hv |

**What the `_SH4A` / `_VPU5HD` names mean [likely]:** R8A7778 is the Renesas **R-Car M1A**. It pairs an ARM Cortex-A9 application core with an on-chip **SH-4A** core and media IP: **VPU5HD** video codec, SPU2 sound DSP, VIO6C video I/O. `AACEncoderFilter_SH4A.dll`, `ATRAC3DecoderFilter_SH4A.dll`, `MPEG4DecoderFilter_VPU5HD.dll`, `WMVDecoderFilter_VPU5HD.dll` and `VideoRenderer_VIO6C.dll` are ordinary **ARM** DirectShow filter DLLs. Their entry points are ARM (`70 40 2d e9` = `stmfd sp!,{r4-r6,lr}`). The suffix names the accelerator each filter offloads to, not the CPU it runs on. Any SH-4A code would be a payload these DLLs load onto the coprocessor. None was identified in this pass.

This **contradicts** `02-unit-and-clock.md`, which said "CPU is Renesas SH-4A [likely]" and recommended Ghidra "SuperH4 LE". That doc is updated.

**Ghidra:** import the rebuilt PEs with language **`ARM:LE:32:v7`**, compiler spec `windows`:
```
analyzeHeadless ~/nissan/work/ghidra <proj> -import <module> -processor ARM:LE:32:v7 -cspec windows
```
Tested on PM13 navdrv.dll with Ghidra 12.2: 253 functions, and exports disassemble as clean ARM (`mov r0,#0x1; bx lr`, `cpy r12,sp; stmdb sp!,{r4,r11,r12,lr}`). Ghidra's auto-pick (`ARM:LE:32:v8`/windows, from Machine 0x1C2) also works. v7 matches the Cortex-A9. Ghidra logs "Exception Data unsupported architecture: 0x1c2" for `.pdata`, which is harmless. Set the image base to the e32 vbase; the rebuilt PE already does this. Don't use SuperH4.

## 4. Registry hives (head start for #3)

CE 6/7 hive format, worked out here **[likely]** (`cehive.py` docstring). Signature `EKIM` at +8. One root record (tag 0xB0) at +0x6010 holds links to the first subkey of HKCR, HKCU, HKLM and HKU. Key records (0xC0) are `{handle, next, firstsub, firstval, name}`; value records (0xD0) are `{handle, next, type, len, name, data}`. Every key in boot.hv and user.hv is reachable; in default.hv 1289 of 1303 are (the other 14 are probably free/stale records).

| hive (PM13) | content |
|---|---|
| boot.hv | HKCU + HKLM, 104 keys |
| default.hv | HKCR + HKLM, 1303 keys, 2776 values |
| user.hv | HKCU, 19 keys (`Locale = 0409`, `LocaleName = en-US`) |

Clock-relevant **[confirmed]** (PM13 default.hv; UP14 is the same for `Time Zones\Default`):
```
[HKEY_LOCAL_MACHINE\Time Zones]
  Default = SZ:'Pacific Standard Time'                      <- untouched CE default; no Tokyo here
[HKEY_LOCAL_MACHINE\Time Zones\Tokyo Standard Time]
  ID = 2110   TZI Bias=-540 (UTC+9), no DST
[HKEY_LOCAL_MACHINE\Time Zones\New Zealand Standard Time]
  ID = 2410   TZI Bias=-720 (UTC+12), DltBias=-60, std 1st Sun Apr 03:00, dst last Sun Sep 02:00
[HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Clock]   AutoDST = 1
[HKEY_LOCAL_MACHINE\Services\DSTSVC]            Dll = dstsvc.dll
[HKEY_LOCAL_MACHINE\Drivers\Launch\Navigation]  Dll = navdrv.dll, Prefix NAV, Order 9
```
- 146 `Time Zones` entries. The NZ entry has the post-2007 DST rules, so the OS could keep NZ time with DST by itself.
- No `DefaultTZID`, `TimeZoneInformation`, area, market or destination keys were found. `HKLM\SOFTWARE\Clarion` holds only DirectShow filter settings.
- Taken with §1, JST is **not** set by the registry. navdrv.dll forces it at runtime via `SetTimeZoneInformation` (issue #4 is the next step). The ROM registry is the factory image; the unit's persistent registry, if any, may live elsewhere (VSRAM?). That is open.

## Open questions
1. Disassemble `GPS:SetTimeZoneFromSystem` in PM13 navdrv.dll (#4): is the Tokyo TZI a constant, and is there a code path that honours `Time Zones\Default` or a VSRAM setting?
2. Does the unit persist registry changes (hive-based registry on SD/flash)? If it does, a registry-level fix might be possible without patching ROM.
3. Is any SH-4A firmware payload inside the `_SH4A` filters or loaded from a file?
4. G214 (#6): reverse the outer MTCP layer, then run `ceromx.py` on the inner image to get objdll.dll, evtimercc.dll and setcc.dll.
