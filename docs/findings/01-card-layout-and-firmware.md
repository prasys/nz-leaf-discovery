# raw-areas — forensics of everything outside p1's filesystem

Image: `~/nissan/sdcard/nissan-sd-485-1972-00.img` (31,653,888 × 512-byte sectors). All work was read-only (python `open(...,'rb')` / `dd if=`).
Carved outputs: `~/nissan/work/raw-areas/` (see "Artifacts" at the end).

## TL;DR

1. **This card is more than a map card. It is the head unit's main storage.** The unpartitioned area before p1 (sectors 1–888,832) holds:
   - a Clarion shadow partition table ("CLARION ID"),
   - **four Windows CE 6/7 firmware images** (ARMv4I/Thumb, CPU type 0x1C2) plus one sub-micom image, stored raw in fixed slots,
   - a firmware-version table (MINF),
   - a **"virtual SRAM on SD" (VSRAM) store** where the unit backs up its settings and state. That store contains clock timestamps, a Japanese holiday table, paired Bluetooth devices and what look like location points.
2. **The "gap" between p1 and p5 is a hidden exFAT partition (p2).** Only the CLARION ID table at sector 1 lists it; the real MBR at sector 0 has that slot blanked. It is the unit's live user-data volume (phonebook, CARWINGS/CWS data, voice-recognition grammars, and a modified (non-stock) `SkinChange/002/substance.skn`, see [11](11-skin-pipeline.md)).
3. **p5/p6 were not wiped by desktop Windows.** They are TexFAT-flavoured exFAT (2 FATs, 2 bitmaps, 0xA1 padding entries). Only Windows CE writes that format, so the head unit (or a Clarion tool) almost certainly formatted them. A desktop Windows PC in a UTC+12 zone then mounted them on 2024-06-09 12:34 (+12:00) and created `System Volume Information`. Everything else on p5/p6 is 0xFF (erased or discarded), so **nothing older can be recovered from them**.
4. **Clock / timezone (main lead):** `navdrv.dll` in the firmware has a function `GPS:SetTimeZoneFromSystem` that calls `SetTimeZoneInformation`. The only timezone names next to it are "Tokyo Standard Time" / "Tokyo Daylight Time", so the timezone looks hard-coded to JST. The card supports this independently: unit-written file times on hidden p2 run **+9 h** ahead of the UTC-looking timestamps in VSRAM (details below). **Likely conclusion: the unit sets its clock from GPS and always shows Japan time (UTC+9). That is the "wrong clock" if the car is not in UTC+9.** Confidence: medium-high. It still needs the owner's confirmation (see open questions).
5. No Linux, uImage, ELF, squashfs or U-Boot anywhere. The OS is Windows CE. No bootloader image was found on the card. MINF says "BL102", so the bootloader probably lives in the unit's internal flash.

---

## 1. MBR / EBR chain (sector 0, 30949377, 31031298)

Sector 0 has **no boot code** (bytes 0–0x1B7 are all zero). Disk signature `redacted` (redacted).

| slot | type | start LBA | count | end | notes |
|---|---|---|---|---|---|
| MBR#1 | 0x0C | 888,833 | 29,036,544 | 29,925,376 | p1 FAT32 (maps) |
| MBR#2 | **00 (blank)** | – | – | – | **hidden p2 is listed only in sector 1** |
| MBR#3 | 0x05 ext | 30,949,377 | 704,511 | 31,653,887 | extended partition runs to the end of the card |
| EBR@30949377 | 0x0C | +1 → 30,949,378 | 81,920 | 31,031,297 | p5 (exFAT despite type 0x0C) |
| EBR@31031298 | 0x0C | +1 → 31,031,299 | 245,760 | 31,277,058 | p6 (exFAT despite type 0x0C) |

The CHS fields are not real geometry. The start-CHS bytes are `00 02 00` / `00 03 00` / `00 04 00`, which looks like a partition **index** (2, 3, 4) that Clarion's formatter writes. Every partition uses type 0x0C even when it holds exFAT. That is a Clarion convention: desktop Windows would have written type 0x07.

The tail 31,277,059–31,653,887 (~184 MB) inside the extended partition is unallocated and all 0xFF.

## 2. Sector 1: "CLARION ID" shadow partition table — HIGH confidence

```
0000: 43 4c 41 52 49 4f 4e 20 49 44 00 ...           "CLARION ID"
01c0: 02 00 0c 00 01 00 01 90 0d 00 00 10 bb 01 00 00   #1 type 0C start 888833   cnt 29036544  (=p1)
01d0: 02 00 0c 00 01 00 01 a0 c8 01 00 a0 0f 00 00 00   #2 type 0C start 29925377 cnt 1024000   (HIDDEN p2)
01e0: 02 00 05 00 00 00 01 40 d8 01 ff bf 0a 00 00 00   #3 type 05 start 30949377 cnt 704511    (=ext)
01fe: 55 aa
```
This is a second MBR-style table with the magic string "CLARION ID" in the boot-code area. It matches sector 0 except that **entry #2 (the hidden user-data partition) is present here and blanked in sector 0**.

Interpretation (a guess, but well supported): the head unit's partition/mount code (`mspart.dll`, `Cl_fatutil.dll`, `AppLaunch.dll` "CMountCtl MountPartitionMain") reads this table so it can mount the private partition. A PC that reads sector 0 only sees p1, p5 and p6. The block also works as a "this is a Clarion-prepared card" marker. No crypto/auth data is in sector 1 itself. The encrypted-looking data sits at 800768–800772 (see §5).

## 3. Leftover factory FAT32 (sectors 8192–16447) — HIGH confidence

- Boot sector at **8192**, backup at **8198** (`BPB_BkBootSec=6`), FSInfo at 8193 (`RRaA`/`rrAa`).
- BPB: OEM blank, 512 B/sector, 64 sectors/cluster (32 KiB), reserved 466, 2 FATs × 3,863 sectors, hidden sectors 8192, total 31,645,696 (8192 + 31,645,696 = the whole card), root cluster 2, serial redacted, label "NO NAME".
- FAT1 @ 8658 and FAT2 @ 12521 contain only `F8FFFF0F FFFFFF0F FFFFFF0F` (an empty FS). Data/root cluster 2 @ 16384 holds just one volume-label entry:
  `NCG2K2_16G` attr 0x08, write time 0xAA69 date 0x4379 = **2013-11-25 21:19:18**.
- This is the whole-card FAT32 written at card preparation. The 8192 alignment is SD-Association style. The label *NCG2K2_16G* is probably the Clarion/Nissan card-type name (guess: "Nissan Connect Gen2 K2, 16 GB"). Clarion later wrote its own layout over it. Partitioning never overwrote the region, so it survives. Nothing else can be recovered from this old volume because its FAT and root are empty.
- 16448–65535 is 0xFF (erased).

## 4. Firmware slot area (sectors 65536–790527) — HIGH confidence on structure

Each slot starts with a 512-byte header sector:
`+0x00 u32 image byte size`, `+0x14 u16 byte-sum + name`, `+0x30 "SUM4" + u32 word-sum`, `+0x50 Clarion part no.`, `+0x1FC "NKOK"` (a validity flag, "NK OK"). For the two bootable NK images the header holds only the size, and the name/part no. sit inside the image at +0x20/+0x50 (image +0x30 holds a u16 byte-sum). The checksum algorithms are in [05-checksums.md](05-checksums.md).

| header sector | name | part no. | bytes | contents |
|---|---|---|---|---|
| 65536 | `G314JLNI.066` | 470-5121-12 | 5,556,456 | WinCE XIP region (ROMHDR at VA 0x8BA5E4A4, base 0x8B8D0000). 17 modules: zlib, commdlg, regextdev, netui, redir, shlwapi, urlmon, wininet, ieframe, mlang, ceshell, explorer.exe, shcore, control.exe, ctlpnl, cplmain.cpl… Includes a PEM certificate at sector 75798. |
| 157696 | `G214JLNI.066` | 470-5120-12 | 30,737,408 | **[confirmed]** `MTLD` descriptor in the slot header at +0x70; carved payload starts one sector later with `MTCP`. Part A has 11 **raw LZ4** chunks (10 × 2 MiB + 0x7FE00 = 0x147FE00), with **SUM4 over compressed sector-padded chunks, not CRC32**. Part B: 0x1412400 raw bytes at **carved payload** +0x93E000. Combined ROM is 0x2892200 bytes, ECEC +0x40, ROMHDR +0x288F918, base VA 0x88840000, 287 modules/43 files including Navi.exe, EvTimerCC.dll and NaviSetCC.dll. **[likely]** The high-entropy region at payload +0xC00000…0x1C00000 largely holds CE-compressed sections (96.6042% covered by flagged section ranges), rather than one encrypted blob. This corrects the original unknown/LZSS/CRC32 description; [full evidence and tools](06-mtcp-lz4.md). |
| 667648 | `UP14XNNI.139` | 470-4651-16 | 26,091,608 | **Bootable WinCE NK image** (starts `FE 03 00 EA` = ARM branch; ECEC @0x40; ROMHDR VA 0x898E028C, base 0x88000000, RAM 0x8D300000–0x8FD00000). 213 modules, 26 files. Build ~2014-12-16…2015-02-06. Contains `UpdateMng.exe`, `PRGUpdate.exe`, `PowerMicomUpdate.exe`, `DabMicomUpdate.exe`, `DisplayUpdate.exe`, `VCANSubMiconUpdate.exe`, `MapUpdate.exe`, `UpdateNK.skn` → **updater / recovery OS** (guess: "UP" = update). |
| 749568 | `PM13XKNI.039` | 470-4650-14 | 19,382,876 | **Bootable WinCE NK image**, same base. 246 modules, 25 files, built 2015-01-26 to 2015-10-08. Contains `timezones.dll`, `notify.dll`, `SdCardLch.exe`, `ProductTest.exe`, `BT_MGR.dll`, `VSramSD.dll`, `navdrv.dll`, `CAN.dll`, `MagicGate.dll`… → **main OS**. |
| 790528 | `OIXXXVNI.004` ("BASS") | 470-5049-00 | 0x389EEC (in a 7249-sector slot) | `BASS` magic at +0 and +0x1FC, string `B000000000001`. Probably a sub-micom/DSP/display firmware ("OI004" in MINF). Not decoded. |

Unused slots: 217856–667647 (five 81,920-sector slots, 0xFF with two zero sectors at every 81,920 boundary) — reserve/A-B space for updates.

The ROM file lists (from my ROMHDR parser) are in `*.romhdr.txt`. Registry hives `boot.hv`, `default.hv`, `user.hv` exist in both NK images but are **CE-compressed** (comp < real size). **Update:** they are CE romimage LZX and are now decompressed and dumped; see [05](05-ce-rom-extract.md) (`HKLM\Time Zones\Default` = Pacific Standard Time, no DefaultTZID).

### Clock-relevant firmware strings
- UP14 (`navdrv.dll`, sector 694765, uncompressed in that image):
  `NavDrv >> GPS:SetTimeZoneFromSystem SetTimeZoneInformation ret = %d, Error = %d`, followed directly by `Tokyo Standard Time`, `Tokyo Daylight Time`; also `GPS:GpsInit SetTimeZoneFromSystem Failed !`.
  → GPS initialisation forces the system timezone to Tokyo. PM13 also has `navdrv.dll`, but its copy is compressed, so the string isn't visible. It is very likely the same code. **Update:** confirmed after LZX decompression; PM13 navdrv.dll has the same strings ([05](05-ce-rom-extract.md) §1).
- PM13 `timezones.dll` (sector ~754971) carries the full standard CE timezone list ((UTC-12) … (UTC+13) Samoa, incl. "(UTC+12:00) Auckland, Wellington"). The OS can technically handle other zones.
- The HMI (G214) does have timezone and summer-time setting screens. They may be hidden by the market/area code (`DIAG_AREA_JAPAN`, `MODEL AREA JAPAN`). This is a guess and needs RE of G214.
- `TIMER_VCM_CLOCK_SET` / `VCAN_EVTIMER_ACK_SET_CLOCK`: the nav pushes its clock to the Leaf VCM over CAN, presumably for the charge/climate timers. Per the Leaf manual (quoted on forums), the charge timer follows the nav clock, not the dash clock ([mynissanleaf thread](https://mynissanleaf.com/threads/answered-q-how-2-set-clock-on-dash-board-2013-sv-vs-s.14742/)).

## 5. Config / VSRAM area (sectors 790528–818431) — HIGH confidence on structure, MEDIUM on semantics

| sectors | magic | meaning |
|---|---|---|
| 800768, 800769 (identical) / 800771, 800772 (identical) | none, high entropy | encrypted/keyed blobs, ×2 copies (guess: device/auth keys — MagicGate? card binding?) |
| 800774, 800775 | `MPUP` … `?OUP` | update state flags (mostly 0xFF) |
| 800783 | `MINF` | **installed-component version list**: `BL102: OI004: G3066: PS001: UP139: G1066: G2066: PM039: S1066: S2066: PW160: TF005: FD001: BE018: DS007: DN503: AD921:` (BL = bootloader v102, PW = power micom v160, etc.; G1066 is listed but has no slot here, so it is probably in internal flash) |
| 800790 | `INITMPID` | `J420150401015000` + u32 word-sum (05 §2.5) (guess: initial map/program ID; contains 2015-04-01) |
| 802816 | `VSDH` @0x1F8 | "Virtual SRAM on SD" header (`VSramSD.dll`, log string `[VSRAM]CVSramMltBackup::RestoreAreaData`) |
| 806912–809935 | `SRST`…`SRED` | three SRAM areas, each stored as an **A/B pair** with a generation counter and trailing u32 word-sum (not a CRC; 05 §2) |

**Correction, 2026-10-24 [confirmed]:** the earlier "trailing CRC" label was
incorrect. VSramSD `FUN_eeddc57c` adds LE u32 words; the field at area end minus
16 is the sum of bytes `[0, size-16)` modulo 2^32. This matches all six saved
sys/nav/bt copies. The final four bytes are `SRED`. See [08 §11](08-nz-clock-implementation.md#11-fixed-saved-zone-experiment).

SRAM areas (`SRST` header: `53525354 0c000060 <gen u32> <copy# u32>`):

| area | A copy | B copy | size | gen A/B | content |
|---|---|---|---|---|---|
| "sys" | 806912–806969 | 806970–807027 | 29,696 | 0x5651 / 0x5650 | binary only, no strings |
| "nav" | 807028–807337 | 807338–807647 | 158,720 | 0x11FF5 / 0x11FF6 | "485-1972-00", "DATA VERSION 15/04/01/00", **clock stamps**, JP holiday table 2015–2034, position-like records (repeating `xx xx 54 35` u32s around +0x14C00) |
| "bt" | 807648–808791 | 808792–809935 | 585,728 | 0x91B83 / 0x91B84 | paired-device names (UTF-16, *PII, redacted*: five paired-phone names and the car's BT name), call/sync timestamps |

### Timestamps found (packed `u16 year, u8 mon, u8 day, u8 h, u8 m, u8 s, u8 flag`)
- nav +0x144 (last-write / current time): **A = 2026-10-23 06:30:58, B = 2026-10-23 06:31:28**
- nav +0x150 (same in both copies; probably power-on/session-start): **2026-10-23 06:15:35**
- nav +0x168…+0x6D7: dates only = Japanese public holidays 2015–2034 (01-01, 01-12 Coming-of-Age 2015, 02-11, 03-21, 04-29, 05-03…, 12-23 the pre-2019 Emperor's Birthday). The table is pre-Reiwa, so it shows the wrong holidays from 2019 on. This only matters for calendar display.
- bt +0x866B4/+0x866BC/+0x866C4: 2026-10-23 14:56:54, 03:42:37, 09:36:59 (guess: last-connect/sync time per phone, in local time).

### Cross-check that points to "unit local time = UTC+9 (JST)"
- The unit itself wrote file times on hidden p2 with **no UTC-offset field set**: voice-grammar files regenerated at boot are stamped **2026-10-23 15:18:46–48**.
- VSRAM says the session started at **06:15:35** and last saved at **06:31:28**.
- 15:18:46 − 9 h = 06:18:46, which is 3 minutes after boot and inside the session window. That fits exactly if VSRAM stores **UTC (GPS time)** and the filesystem uses **local time = UTC+9**.
- The BT stamp 14:56:54 (= 05:56 UTC under the same assumption) falls just before that session. That is also consistent.
- Confidence: medium-high. The alternative is that the VSRAM stamps are local and the files run 9 h fast, which still means a +9 h discrepancy. Either way the unit applies a +9 h offset to GPS/UTC.

## 6. Hidden p2 (sectors 29,925,377–30,949,376, 1,024,000 sectors) — HIGH confidence

exFAT: serial **redacted**, rev 1.00, 1 FAT, 32 KiB clusters, 15,996 clusters, 3 % used, volume label deleted.
I listed it with my own read-only walker. Listing: `work/raw-areas/hiddenp2_listing.txt`; extracted files (live and deleted-entry contents): `work/raw-areas/hiddenp2_files/`.

```
/SkinChange/002/substance.skn   20,025,376 B   C 2022-04-14 13:25:20 (UTC+11:00 offset → written by a PC)   ← UI skin (Clarion `SKINSK18NNNI.183`, already modified when found; see 11) — contains thousands of PNGs
/PRIVATE/TEL/PB_OBJ/{Mgr_Info.bin, 0_TelBook.bin, 1_TelBook.bin}  phonebooks (PII), latest 2026-10-20
/PRIVATE/CWS/{DJ,AP,DCME,CP,PIC}/…  CARWINGS data (CWS_CNF mod 2024-12-01, CWS_SYS mod 2025-03-22, DCME_TCUPIN)
/SPEECH/{VR,XX/TTG,JP/TTG}/…        voice-recognition grammars, regenerated each boot (2026-10-23 15:18:46)
/Content/CCU/db                       empty dir
```
- All of `PRIVATE`, `SPEECH` and `Content` were created **2024-06-09 10:16:00–10:19:48 unit-local (no TZ)**, which is 01:16 UTC if local = JST. The volume itself is older (SkinChange from 2022), so on 2024-06-09 the unit (re)initialised its user-data tree, for example after a factory reset or a card swap.
- 1,649 unallocated but non-empty clusters (~52 MB) exist. They are probably old phonebook/grammar versions and older skin data. **Not carved yet.**
- The magic scan of this region found only PNG/zlib (skin resources) and 3 JPEGs.

## 7. p5 / p6 — was something wiped in 2024?

| | p5 | p6 |
|---|---|---|
| exFAT serial | redacted | redacted |
| clusters (32 KiB) | 1,277 | 3,837 |
| FATs / bitmaps | **2 / 2 (TexFAT)** | **2 / 2 (TexFAT)** |
| root dir | 0xA1 TexFAT padding entries + `System Volume Information` | same |
| SVI times | 2024-06-09 12:34:16–20 **UTC+12:00** | same |
| allocated clusters | 8 (metadata + SVI) | 8 |
| other clusters | all 0xFF | all 0xFF |

- NumberOfFats=2 and the 0xA1 padding entries are valid only for TexFAT, which Windows CE uses ([MS exFAT spec](https://learn.microsoft.com/windows/win32/fileio/exfat-specification), [ntfs.com TexFAT padding](https://www.ntfs.com/exfat-textFAT-padding.htm)). Desktop Windows' format does not create TexFAT. So the **head unit (WinCE `exfat.dll`/`Cl_fatutil.dll`) most likely formatted p5/p6**. The type-0x0C MBR entries fit the same Clarion convention.
- `System Volume Information\WPSettings.dat` / `IndexerVolumeGuid` were then created by **desktop Windows 10/11** when the card was plugged into a PC whose clock was set to UTC+12 (e.g. NZST in June — a guess about location). That happened at 2024-06-09 00:34 UTC, about 40 minutes before the unit-local 10:16 creation of p2's user tree (if unit = JST).
- **Nothing can be recovered from p5/p6.** Every non-metadata sector reads 0xFF: the format erased/discarded it, and the SD controller returns 0xFF for discarded blocks. Their purpose is unknown (guess: update/probe/work areas).
- Answer to "was something wiped in 2024?": p5/p6 were (re)formatted on or before 2024-06-09 and are empty. The evidence points to the unit or Clarion tooling doing the format, not the PC, which only mounted them. On the same day the unit rebuilt PRIVATE/SPEECH/Content on hidden p2. That looks like a unit-driven re-initialisation (factory reset / card re-init) on 2024-06-09.

## 8. Signature scan (my own scanner, `magic_pre.txt`, `magic_gap_p5p6.txt`)
- Pre-area: ECEC ×9 (CE ROM headers inside the images), RIFF AVI/WAVE (UI sounds/animations), PNG 67, GIF 1, zlib streams that decompress (113, inside CE modules), 1 PEM cert (sector 75798), LZMA ×1 (false positive inside PNG data), JPEG hits mostly false.
- Gap/p5/p6: PNG 6,928 + zlib 6,709 (skin), JPEG 3.
- **No** ELF, uImage, gzip, xz, bzip2, squashfs, UBI, JFFS2, CAB, ZIP, SQLite. binwalk was not installed; I used the custom scanner.

## 9. Pre-area sector map (summary)
```
0            MBR (no boot code)
1            CLARION ID shadow table
2–8191       zero
8192–16447   factory FAT32 remnant (label NCG2K2_16G, 2013-11-25)
16448–65535  0xFF
65536        slot G314JLNI.066 (→76389)
76390–157695 zero
157696       slot G214JLNI.066 (→217730)
217856–667647 0xFF (5 empty slots @81920)
667648       slot UP14XNNI.139 (→718608)
718610–749567 0xFF
749568       slot PM13XKNI.039 (→787426)
790528       slot BASS OIXXXVNI.004 (→797776)
800768–800790 keys / MPUP / MINF / INITMPID
802816       VSDH
806912–809935 SRAM areas A/B (sys, nav, bt)
810240–812781 small records (not decoded)
814631, 816348 single records (816348 starts 0x7530=30000)
818432–888832 0xFF
```

## Open questions
1. **Owner to confirm:** what is the car's real local timezone, and what time does the head-unit clock show compared with real time? If it shows real time + (9 − local UTC offset) h, the JST hypothesis is confirmed. Also, roughly when was the car switched off on 2026-10-23 before the card was imaged (06:31 UTC = 15:31 JST = ? local)?
2. Does the HMI's `SET_CLOCK_TIMEZONE_SETTING_MENU` appear on screen, perhaps under Settings → Clock? Is it hidden by an area code? Where is that area code stored (VSRAM "sys" area? internal EEPROM? MINF?)
3. What do the decompressed `default.hv` / `user.hv` contain (DefaultTZID, `HKLM\Time Zones`, any Clarion `TimeOffset`/`AreaCode` keys)? This needs a CE ROM decompressor (CECompress LZX/XPRESS, e.g. itsme's `dumprom`/`eimgfs`).
4. Which SRAM-area offset holds the user's manual clock offset (if any)? To find it, image the card again after changing the clock by a known amount on the unit, then diff the VSRAM A/B areas.
5. **Resolved outer format [confirmed]:** G214 MTCP is raw LZ4 with SUM4 checks, producing a 287-module WinCE ROM. **[likely]** Its high-entropy raw region largely holds CE-compressed sections; the inner codec and PE reconstruction remain open. See [06-mtcp-lz4.md](06-mtcp-lz4.md), §§3–5.
6. The meaning of the encrypted blobs at 800768–800772, and whether the card is bound to the unit (VIN/serial) so that changes would break boot.
7. ~~Who wrote `SkinChange/002/substance.skn`?~~ A PC, not the unit (UTC+11 timestamp); the skin had been modified before this work. See [11](11-skin-pipeline.md).

## Suggested next steps
1. Get the clock observation from the owner (Q1). That is the cheapest way to confirm the JST finding.
2. Extract the `navdrv.dll`, `timezones.dll` and `.hv` files from the UP14/PM13 NK images with a CE ROM extractor (dumprom-style). Decompress `default.hv` and look for `Time Zones\DefaultTZID`, `TimeZoneInformation`, Clarion area/destination keys. Disassemble `SetTimeZoneFromSystem` in navdrv.dll (ARM/Thumb) to see whether the Tokyo TZI is a constant or read from the registry/VSRAM.
3. Differential test, if the owner is willing: before/after images (or just raw dumps of sectors 800768–818431) around a manual clock change, summer-time toggle, or timezone menu change. Diffing the VSRAM A/B areas will locate the clock-offset setting.
4. Carve the 1,649 unallocated non-empty clusters on hidden p2.
5. Use `tools/mtcp/mtcp.py` to recover G214, then reconstruct/decompress its CE module sections before tracing the CLOCK_TIMEZONE menu and area gating ([MTCP findings](06-mtcp-lz4.md), §4).
6. **Do not edit** VSRAM/slots on the card without first understanding the SUM4/NKOK/SRED checksums and keeping a verified backup image. Any modification has to happen on a *copy* written to a spare card, never on this image or the original.

## Artifacts (`~/nissan/work/raw-areas/`)
- `pre_s0-888832.bin` — raw copy of sectors 0–888832
- `slot065536_G314JLNI.066.bin`, `slot157696_G214JLNI.066_MTCP.bin`, `slot667648_UP14XNNI.139_nk.nb0.bin`, `slot749568_PM13XKNI.039_nk.nb0.bin`, `slot790528_BASS_OIXXXVNI.004.bin`, `settings_800768-818431.bin`
- `*.romhdr.txt` — ROMHDR module/file tables
- `sram_sysA_*.bin`, `sram_navA_*.bin`, `sram_btA_*.bin`
- `hiddenp2_listing.txt`, `hiddenp2_files/` (contains PII: phonebooks)
- `pre.strings.ascii.txt`, `pre.strings.utf16.txt`, `magic_pre.txt`, `magic_gap_p5p6.txt`
- Scripts (scratch, not on card): `mbr.py`, `runs.py`, `hdrs.py`, `romhdr.py`, `exfat.py`, `magic.py`, `u16.py` — copied to `~/nissan/work/raw-areas/scripts/`.
