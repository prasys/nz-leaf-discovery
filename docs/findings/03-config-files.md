# config-files — small config/system files on p1 (FAT32 "485-1972-00")

Scope: root DAT files, CMP.LST, VER_INFO/DB_INFO.TXT, BICON001, DFRMR001, CWS/CERT, OPNG, IPOD_OPNG, REFER001 (headers only) / REFER002, System Volume Information, and FAT timestamps.
All work was read-only: files were read from the RO mount or with offset reads from the .img.
Outputs: `~/nissan/work/config-files/` (scripts in `scripts/`, CSVs, carved images).

Confidence: **H** = verified against independent ground truth, **M** = consistent structure but meaning partly inferred, **L** = guess.

---

## TL;DR (time/clock relevant first)

1. **The head unit writes FAT timestamps, and they look like a snapshot of its own clock.** `DBDIR/SPOOL/EDABORT1/2` were created on **2024-10-16 17:40:56** and modified 17:42:16/17:42:20. These are raw FAT local-time fields with no timezone. The same day appears as the last-access date on `OPNG/.../OIXXXVNI.004` (boot animation), 6 random `DFRMR` junction images, several `DBDIR` files and `BICON001.DAT`. That's a "car was driven" access pattern, not a PC browse. An earlier session left access date **2018-06-14** on `TFTBL002.DAT` and on the DBDIR/REFER/CDDB/BICON directories. (M; see §12.)
   - The analysing Mac is in NZDT. A JDM unit that shows JST (UTC+9) in NZ would be 3–4 h behind local time. If the owner can recall when the car was used on 2024-10-16, comparing that with 17:40 tells us what timezone/offset the unit's clock used. (L: hypothesis only.)
2. **`TFTBL002.DAT` is a 30-year day-type calendar (2003-01-01 → 2032-12-31)** for Japan, almost certainly for statistical traffic prediction. It encodes weekday/Fri/Sat/Sun-holiday/special-period. The holiday rules are frozen at about 2012: no Mountain Day 2016, no 2019 imperial holidays, 23 Dec still a holiday after 2019. It has no timezone/DST content. (H)
3. **No timezone/DST/clock setting exists in any file in this scope.** I searched for 540 / 0x21C / 32400 (BE/LE, 16/32-bit) and "JST/UTC/GMT/TIME/ZONE/DST/SUMMER" strings. Hits are sparse and occur at random-chance rates inside binary map/POI data; the ones I inspected were coincidences. (H for "not present as a clean field")
4. **AM/FM tables are Japan-only by construction.** FM covers 76.0–90.0 MHz in 0.1 MHz steps (141 channels). AM covers 531–1629 kHz in 9 kHz steps. Region is chosen by row (10 Japanese broadcast regions), presumably from GPS position. No region/band selector field and no checksum. (H)
5. **Integrity checks found:**
   - IPOD_OPNG: a byte-sum over the 0x3C-byte header only. The bitmap is not covered. (H)
   - OPNG "BASS": a 32-bit word-sum over the whole file. (H)
   - REFER001 `.cmp`: per-chunk zlib, which carries adler32. (H)
   - Everything else in scope has **no detectable checksum/CRC**. (M: absence of common algorithms ≠ absence of any check in firmware.)
6. **Provenance warning:** macOS wrote `.fseventsd` and `.Spotlight-V100` to the **physical card** on 2026-10-24 17:48–17:51 NZDT. That was before the image was taken (img mtime 18:03). The image therefore is not pristine: the root directory gained 2 entries, the volume-label access date changed, and the clusters were allocated. Original content is otherwise unaffected. Future mounts of the physical card should avoid this.

---

## 1. AMFRQ001.DAT / FMFRQ001.DAT — broadcast station name tables (H)

Size: AM 12,100 B, FM 11,492 B. Big-endian. No header magic, no trailer, no checksum. The last record ends exactly at EOF in both files.

Layout:
```
0x00  u32 BE[10]   row_base[r]  (in 16-bit WORDS from file start)
                   AM: 0x14,0x90,0x10c,...  (stride 0x7C = 124 cols)
                   FM: 0x14,0xA1,0x12E,...  (stride 0x8D = 141 cols)
row_base*2 ...     u16 BE cell[col]  = 0 (no station) or word offset RELATIVE TO row_base
cell target:       u16 n ; u16 rec_ptr[n]   (rec_ptr also word offset relative to row_base)
record:            u16 X   station/network id   (e.g. 1960=NHK1, 1961=NHK2, 1902=NHK-FM, 1832=TBS)
                   u16 Y   location id or 0xFFFF (same Y in AM and FM for the same city, e.g. 1963=Sapporo, 1981=Tokyo)
                   u16 power (AM: kW, matches real NHK values 100/500/300; FM: unit unclear)
                   u16 0xFFFF, u16 0xFFFF   (always)
                   u16 ?   (small number, roughly a name length; exact meaning unknown)
                   name: ISO-2022-JP (ESC $ B ... ESC ( B), NUL-padded to even length
                   u16 len ; reading: JIS X 0201 half-width katakana with bit 7 stripped
                         (i.e. byte|0x80 → cp932 kana), e.g. "4G42A902A;/N_[" = ｴﾇｴｲﾁｹｰｲﾁｻｯﾎﾟﾛ
```
- **Columns = frequency channel.**
  - AM: `f = 531 + 9*(col-1) kHz`. Cols 1..120 = 531..1602; cols 122, 123 = 1620/1629 kHz "交通情報" (highway advisory radio).
  - FM: `f = 76.0 + 0.1*col MHz`, cols 0..140 = **76.0..90.0 MHz**.
  - Verified: NHK1 Sapporo 567, TBS 954, Nippon Hoso 1242, NHK-FM Sapporo 85.2, J-WAVE 81.3, TOKYO FM 80.0, InterFM 76.1, bayfm 78.0, NACK5 79.5.
- **Rows = 10 broadcast regions** (from the station content): 0 Hokkaido, 1 Tohoku, 2 Kanto, 3 Chubu-wide (Koshinetsu+Hokuriku+Tokai), 4 Hokuriku, 5 Tokai, 6 Kinki, 7 Chugoku, 8 Shikoku, 9 Kyushu/Okinawa. Rows 3/4/5 overlapping is an observation; how the unit picks a row is unknown (L: GPS → prefecture → row).
- Purpose: display a station name for the tuned frequency in the current region. Frequencies are implied by column index and are not stored.
- **Region/band configurability:** none in the file. The band plan is fixed by table geometry. There is no 87.5–108 MHz area and no FM補完 (wide-FM 90.1–95.0) coverage, so the data predates that. Whether the tuner itself can be switched is a firmware question.
- Decoded tables: `~/nissan/work/config-files/AM_stations.csv` (448 cell entries / 190 records) and `FM_stations.csv` (770 / 146). Parser: `scripts/frq.py`.
- Modifiability: no checksum → names could be edited if offsets stay consistent (M; the firmware could still reject the file by size).

## 2. TFTBL002.DAT — traffic day-type calendar 2003–2032 (H)

Size 11,776 B = 4-byte header + 360 months × 32 B, then 252 zero bytes.
- Header `00 17 1E 03`. **Guess (L):**
  - `0x1E` = 30 years
  - `0x03` = start year 2003 (confirmed by fitting; see below)
  - `0x0017` = table version/id 23?
- Each month is 32 bytes = days 1..31 + padding. **Bytes are swapped in 16-bit pairs**: day1 is at byte 1, day2 at byte 0, and so on. Invalid days (Feb 29–31, the 31st of short months) and the padding are `0xFF`.
- Each day byte is `0xN1`. The high nibble N is the day type and the low nibble is always 1.
  - **1** = Mon–Thu
  - **2** = Friday
  - **3** = Saturday
  - **4** = Sunday / national holiday
  - **5** = special period (Golden Week, Obon, New Year 2–4, Silver Week)
- How the year was fixed: month lengths matched leap years only for start years ≡ 3 mod 4, and the weekday↔type histogram fits only 2003. Spot checks: 2015-05-03..05 = 5, 2015-09-21..23 = 4, 2011-03-21 (Mon, equinox) = 4.
- Rules frozen at about 2012:
  - 2016-08-11 (Mountain Day) = 1, not a holiday
  - 2019-04-30/05-01 = 1
  - 2019-12-23 = 4 (old Emperor's birthday)
  - 2020-02-24 = 1
  - 2020 Olympic moves are absent
- FAT mtime 2012-03-26 matches that.
- **Time relevance:** this is the only date-keyed table found. It uses local calendar dates with no timezone. After 2032-12-31 there is no data. An unknown day type could matter for traffic prediction but probably not for the clock.
- No checksum (brute-force of sum8/16/32, word sums, xor, CRC16/32, adler at the header/trailer found nothing).

## 3. ICNSC001.DAT — POI brand selection list (M)

1,724 B, big-endian, **Shift-JIS** strings.
- Header `12AB 0007 0007 0055 0006 005C 0301 0190 000F ...`. 0x12AB is not a common checksum of the body (L: id/magic).
- 6 categories: ガソリンスタンド / ファーストフード / コンビニエンスストア / ファミリーレストラン / 金融機関 / 駐車場.
- Brand entries: `u16 brand_code` (e.g. 0x019A エッソ石油, 0x0351 セブンイレブン), `u16 sjis_len` (0xFFFF for the "その他…" catch-all), `u8 width?`, `u8 01`, then the name.
- Brand codes overlap the BICON icon set (§5). Purpose: brand filter for POI icons on the map. Nothing time-related.

## 4. CMP.LST — list of transparently-compressed files (H)

3,071 B. NUL-separated ASCII paths with no trailing NUL: `\SystemSD\REFER001\coord001.dat`, `icadm001..047`, `index001`, `point001..047` (96 entries).
- Tells the unit's file layer that `<name>.dat` is stored as `<name>.dat.cmp` + `.dat.ind`.
- **`\SystemSD\` is the unit's mount point for this card** (Windows CE-style naming; L: WinCE/T-Kernel VFS).

## 5. BICON001/BICON001.DAT — brand icons (H)

73,316 B.
- Common Zenrin header (§8), then from 0x1308 **91 embedded PNGs, 30×30**, back-to-back up to EOF−1.
- Carved to `~/nissan/work/config-files/bicon/`.
- DATA VERSION 15/04/01/01. No checksum found outside the PNG CRCs.

## 6. DFRMR001/DFRMR0xx.DAT — junction illustrations (H)

19 files. Each is a **plain PNG** (RGBA, 441×360 / 353×360 / 353×178 / 353×182) with only IHDR/IDAT/IEND chunks and no tEXt/tIME. They are highway-branch "deformed" junction pictures (DFRMR ≈ "deformer"). Copied as .png to `work/config-files/dfrmr/`. The PNG chunk CRCs are their only integrity check.

## 7. CWS/CERT/ca.der — CARWINGS root CA (H)

X.509 v3, self-signed, serial 0, RSA-1024, sha1WithRSA.
- Subject = Issuer: `C=JP, ST=TOKYO, L=GINZA, O=NISSAN MOTOR CO LTD, OU=CARWINGS PROJECT, CN=NISSAN CARWINGS`.
- Valid **1972-05-17 → 2037-05-17**. CA:TRUE. Netscape comment "We did it!". SKI 68:06:E8:1F:...:7F:37.
- Used for CARWINGS telematics TLS (Nissan's JP connected service).
- Time relevance: the wide validity window means a wrong RTC wouldn't break validation of this CA itself.

## 8. Common Clarion/Zenrin data header (BICON001, REFER001/ICODE002, REFER002/*, decompressed REFER001/*)

UTF-16 strings padded with 0xFFFF, in 0x40-byte slots:

| off | REFER002 / BICON (BE) | REFER001 decompressed (LE!) |
|---|---|---|
| 0x000 | "CLARION" | "X" |
| 0x040 | "ZENRIN" | "ZENRIN" |
| 0x080 | "CLA-NAVI05-01" | "…NAVI01-01" |
| 0x0A0 | "FORMAT VERSION X08-02-00" | "FORMAT VERSION H08-00-00" |
| 0x0E0 | "DATA VERSION yy/mm/dd/01" | same style |
| 0x160 | 0x14 + "V05.00.00" | 0x16 + "V04.00.00" |
| 0x182 | `1001 0B90 0550 1C20 2580 01` | `2001 0B90 0550 04B0 0E10 01` |

- 0x182 guess (L): 0x0B90/0x0550 = 2960/1360 and 0x1C20/0x2580 = 7200/9600. These fit a Japan bounding box in arc-minutes (49.3°N/22.7°N, 120°E/160°E).
- Data versions:
  - BICON 15/04/01
  - ICODE002 15/03/12
  - REFER002 15/04/07
  - REFER001 15/04/01

## 9. REFER001 (*.dat.cmp + *.dat.ind) and REFER002 (H for container, L for content)

- `.ind` is LE: `u32 raw_size, u32 cmp_size, u32 n_chunks, u32 chunk_size(=0x10000), u32 chunk_off[n]`.
- `.cmp` is the concatenation of independent zlib streams (78 9C), one per 64 KiB raw chunk.
- Decompressor: `scripts/cmp.py`. Samples are in `work/config-files/refer001_decomp/`.
- REFER001 point001 is 162 MB raw.
- **REFER001 is little-endian (UTF-16LE header), REFER002 is big-endian** and uncompressed, with a newer data version (04/07 vs 04/01). `coord001.dat` is the same size in both (4,864 B). After a 16-bit word swap only 48 bytes differ, all in the header.
- Interpretation (L): REFER002 is a delta/updated "reference point" set (47 prefecture files, point001..047 = 47 prefectures). Content was not decoded further because it is out of scope.

## 10. OPNG/MKR_OPNG/02/OIXXXVNI.004 — maker opening animation ("BASS" container) (H for header/checksum, M for payload)

3,710,700 B, little-endian.
```
0x00 "BASS"
0x04 u32 checksum = sum of all LE u32 words from 0x08 to EOF (mod 2^32)  -> 0x429F165B  (VERIFIED)
0x08 "000000000001"   (ascii)
0x14 u32 total file size (0x389EEC)
0x18 u16 0x10 (16 bpp), u16 2
0x1C "OIXXXVNI.004"  0x28 "470-5049-00 " (Clarion part/drawing no.?)
0x40 u32 85 (frames?), u32 4, ...,  0x58: u32 4, u32 50 (frame delay? ms/10?), u32 0x104, u16 x=274,y=119,w=202,h=205 ...
payload: RLE of RGB565 (colours 0x0000/0x0841/0x1082 dark greys);
   tokens look like (u16 count<<5, u16 rgb565) with occasional lone 0x0001 words — NOT fully decoded.
```
- **A byte-identical copy lives in the unpartitioned area**: sector 790528 holds a 1-sector header `"BASS" u32 0x1C50 (=7248 sectors) … "BASS"@+0x1FC`, and sectors 790529..797776 hold the file (sha1 28460b2020b0e573eceeb86c6d2ae7816e537256 matches).
- So the unit stages the opening image into its hidden system area. Other agents looking at sectors 1..888832 should note this.
- No other p1 config file (AM/FM/TFTBL/ICNSC/CMP.LST/cert/DB_INFO/IPOD/ZENRIN header) appears in the hidden areas.

## 11. IPOD_OPNG/NN/OPXXXXyy.00n — iPod logo bitmaps (H)

9 files × 12,904 B = 0x40 header + Windows BMP (166×76, 8bpp).
```
0x00..0x0F zeros
0x10 filename "OPXXXXyy.00n"
0x20 "NN\0\0" "nnn\0" "nnn\0" (dir id, index, count)
0x3C u32 LE = byte-sum of bytes 0x00..0x3B   (VERIFIED on all 9) — header-only checksum
0x40 BMP
```
- **The BMP payload is not covered by the checksum**, so the image can be changed without touching the header (M: firmware may still check size/dims).
- yy codes are maker brands: XX generic, CL, NI (NISSAN, verified visually), HC, DH, SB, MT (L: Clarion/Nissan/…/Subaru/Mitsubishi).
- PNG conversions are in `work/config-files/ipod_opng/`.

## 12. FAT timestamps, System Volume Information, and other artefacts

Raw FAT directory entries were parsed straight from the image (`scripts/fatdir.py`), with no host timezone conversion. macOS `stat` shows some of them shifted by 1 h because of DST conversion. The raw values below are authoritative.

| entry | created | modified | last access |
|---|---|---|---|
| AMFRQ001/FMFRQ001 | 2015-04-21 11:28:31 | 2015-02-03 21:04 | 2015-04-21 |
| TFTBL002.DAT | 2015-04-21 11:28:31 | 2012-03-26 12:39:40 | **2018-06-14** |
| BICON001, CDDB, DBDIR, REFER001, REFER002 (dirs) | 2015-04-21 | 2015-04-21 | **2018-06-14** |
| VER_INFO/DB_INFO.TXT | 2015-08-24 11:38:33 | 2015-08-24 11:32:22 | 2024-06-09 |
| System Volume Information/ (+WPSettings.dat, IndexerVolumeGuid) | **2024-06-09 12:34:15–16** | 2024-06-09 12:34:16–18 | files: **2024-10-16** |
| DBDIR/SPOOL/EDABORT1 | **2024-10-16 17:40:56.09** | **2024-10-16 17:42:16** | 2024-10-16 |
| DBDIR/SPOOL/EDABORT2 | **2024-10-16 17:40:56.68** | **2024-10-16 17:42:20** | 2024-10-16 |
| OPNG/.../OIXXXVNI.004, BICON001.DAT, 6× DFRMR, DBDIR/B3DSYMB, BPCLB, BPOIT45D, ZZGEOAB | — | — | 2024-10-16 |
| .fseventsd, .Spotlight-V100 (macOS, today) | 2026-10-24 17:48:18–19 | — | 2026-10-24 |

- Card mastered 2015-04-21 (base) with VER_INFO/SPEECH added 2015-08-24.
- `System Volume Information`:
  - `IndexerVolumeGuid` = `redacted` (UTF-16LE).
  - `WPSettings.dat` = `0C000000 E126C3BD 003CF3D3` (undocumented format; not decoded).
  - Created by Windows on **2024-06-09 12:34** (Windows local time). That is the same day p5/p6 were reformatted (from the partition-level brief).
- **EDABORT1/2** are 56-byte files with magic `"EDDBABORT  \0"` and the string "dbhmcs6. 342Ehm0005". Windows doesn't create them; they are a nav-DB abort/spool record from the head unit. No plausible Unix/FAT timestamp found inside. Their FAT create/modify times therefore come from **the head unit's RTC, in whatever local time the unit uses** (M).
  - The 2024-10-16 access set (opening animation, random junction images, 3D symbols, POI) matches a head-unit boot/drive.
  - The access to the SVI files the same day could be the unit enumerating files, or a separate Windows mount that day (L).
- The 2018-06-14 access set (TFTBL + nav data dirs) looks like an earlier head-unit session (L).
- Cross-check suggestion: if the owner knows when the car was driven on 2024-10-16 (local NZ time?), comparing that with 17:40:56 shows the unit's offset. NZDT = UTC+13 and JST = UTC+9, so a JST unit would read 4 h behind NZDT.
- Volume: boot-sector label "NO NAME", volume-ID `redacted`, root label entry `485-1972-00`. 64 KiB clusters, 2 FATs.

## 13. VER_INFO/DB_INFO.TXT (H for content, L for field meaning)

ASCII, CRLF, 156 B:
```
GJPNX-10-101-100   product/DB code (G=?, JPN=Japan, X=? , 10-101-100 version)
0100               DB format/edition?
15-02              data edition 2015 #2 (?)
485197200-002      Nissan part no. 48519-72000? / 485-1972-00 rev 002
201500000          model year/edition 2015
reserve02..reserve10
```
No checksum. Last accessed 2024-06-09, the Windows session day.

---

## Checksum / modifiability summary

| file | integrity mechanism | edit feasibility (guess) |
|---|---|---|
| AMFRQ/FMFRQ | none found | editable if offsets stay consistent |
| TFTBL002 | none found | editable (fixed layout) |
| ICNSC001 | none found (0x12AB unexplained) | probably editable |
| CMP.LST, DB_INFO.TXT | none | editable; DB_INFO may be checked against unit for updates |
| BICON001 | PNG CRCs only | editable |
| DFRMR | PNG CRCs only | editable |
| IPOD_OPNG | u32 byte-sum of header (0x00..0x3B) at 0x3C | payload freely editable |
| OPNG BASS | u32 LE word-sum from 0x08 at 0x04 + staged copy in hidden area (sector 790528) | needs checksum recompute; unit may use the hidden copy |
| REFER001 .cmp | zlib adler32 per chunk + .ind sizes | re-compress + rebuild .ind |
| ca.der | X.509 self-signature | replacing CA breaks CARWINGS TLS |

Firmware-side checks (e.g. a size/hash list in the hidden area) cannot be ruled out from these files alone. The hidden-area slot and VSRAM checksums use the same additive sums (u32 word-sum / byte-sum); see [05-checksums.md](05-checksums.md). The staged BASS copy verifies with the same algorithm.

## Open questions
1. Is the 2024-10-16 17:40 FAT time the unit's RTC in JST, UTC, or a user-set local time? This needs the owner's recollection of that day, or a controlled experiment (L).
2. How does the unit pick the AM/FM region row? GPS prefecture lookup, or a stored setting?
3. TFTBL002 header word 0x0017. BASS payload RLE details (lone `0x0001` tokens). ICNSC header 0x12AB. The u16 before station names.
4. What does EDDBABORT encode (fields 0x8787/0x878F, 0x696ED7DC/0x697057DC)? Is it written on every DB abort with the RTC time?
5. Why do the SVI files show access 2024-10-16? Does the unit open every file, or was there a separate Windows mount?
6. Does the hidden-area BASS staging header (sector 790528) belong to a larger table of staged resources (firmware/config) near it?

## Suggested next steps
- **Clock work:** look for the unit's own time/timezone settings in the hidden area (sectors 1..888832, e.g. near sector 790528) and in firmware. Search there for 540/32400, "JST", and GPS week/leap-second constants (GPS-UTC = 16–18 s → 0x10/0x11/0x12 near week numbers). Also look for date-written logs like EDABORT.
- Ask the owner what time the clock shows vs real time (exact offset in hours/minutes). A whole-hour offset of 3–4 h suggests JST-vs-NZ. A ~19.6-year or 1024-week jump would point to the **GPS week-number rollover** (common on 2000s–2010s JDM navs after April 2019). The 2018-06-14 and 2024-10-16 dates look sane, which argues against a rollover-induced wrong *date* (L).
- If a controlled test is possible: boot the unit with a **copy** of this card (never the original), note the displayed time, and read back the EDABORT/FAT timestamps. That calibrates the RTC → FAT mapping.
- Avoid re-mounting the physical card on macOS without `-o rdonly,noatime` (Spotlight/fseventsd already wrote to it once).
