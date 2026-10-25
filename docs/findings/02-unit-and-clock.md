# unit-and-clock — head-unit identity and clock behaviour

Scope: (A) identify the head unit behind SD card `485-1972-00`; (B) how it sets its clock and what can be done about a JDM unit showing the wrong time outside Japan.
All work was read-only against `~/nissan/sdcard/nissan-sd-485-1972-00.img` and `~/nissan/sdcard/mnt/p1`. Carve outputs are in `~/nissan/work/unit-and-clock/`.
Confidence tags: **[confirmed]** = seen directly in bytes; **[likely]** = strong inference; **[guess]** = hypothesis.

**Correction from later disassembly:** the CE timezone forced by navdrv is only one clock layer. The app independently selects UTC+9 in OBJDLL `FUN_40e2c4d4` for model area `0x10`, then adds DST and the user offset in `OBJ_Time_getTotalOffset` (`0x40e2c360`). Changing the CE timezone alone is insufficient **[confirmed, read in decompiler]**. See [06](06-hmi-clock-and-hooks.md) and [07](07-nz-clock-design.md); the early causal explanation and candidate ranking below predate that trace.

**Superseded for the clock fix (2026-10-25):** [12](12-hour-offset-ui.md) exposes the firmware's existing ±12 h hour setter through an 11-byte skin edit, and the owner reports correct NZ time. That contradicts §0's "the hour cannot be fixed from the menu": the stock menu can't, but the setter exists. The §7 ranking is kept as history. Row 6's signature worry is weakened by [13](13-prior-art-leafsdtools.md) §3. The unit-family label "Carwings" in §0 may also be wrong: the ARM CPU and update-slot offset match the QY8XXX ("NissanConnect") family [likely] (13 §3).

## 0. Summary
- **Unit:** factory **Nissan LEAF (AZE0-era, JDM) "Carwings"/EV nav, built by Clarion**. Its map/system SD carries the Feb-2015 MAPPLE map. LEAF is **[confirmed]** two ways: the owner says so, and the firmware has EV-timer/VCM/CAN 5B3/5F9 modules (§3). Exact model code **[unresolved]**: dealer-option Clarion units of the same generation are MC315D-W/-A (QY-7641N/7645N), but the LEAF factory nav is a separate LEAF-specific unit. Check the unit's chassis sticker.
- **Clock:** time comes from GPS. The GPS driver hard-codes **"Tokyo Standard Time" (UTC+9)** (§4.1). The owner sees +9, which fits. The only user setting is **オフセット調整 ±1 min steps (−59…+59 min in Clarion MC manuals)**, so the hour cannot be fixed from the menu.
- **Hidden capability:** the UI framework has `SET_CLOCK_TIMEZONE_SETTING_MENU` and `SET_CLOCK_SUMMERTIME_SETTING_MENU` screens and a service-menu `SLF_CLOCK_SET` (Hours/Minutes). The NZ English conversion for ZE0/AZE0 Carwings units (Navi-Solutions) advertises "local time and date" and "time zones … for New Zealand and Australia".
- **Side effect:** the nav **pushes its time to the VCM**, and LEAF charge/climate timers run on that clock (§4.3). A JST nav clock means timers fire 3–4 h off in NZ.
- **Map DB:** `BHOLIDB` = Japanese public holidays 2015–2034. No TZ data anywhere on p1.

---

## 1. Card identity (local evidence)

| Item | Value | Where |
|---|---|---|
| FAT32 label | `485-1972-00` | p1 boot sector |
| `VER_INFO/DB_INFO.TXT` (CRLF, ASCII) | `GJPNX-10-101-100` / `0100` / `15-02` / `485197200-002` / `201500000` / `reserve02..10` | p1 |
| Map DB build stamps | `2015/03/11-22:04:30 … 22:05:51` (at offset 0xE4 of every `DBDIR/B*D`, `B*B` header) | p1 |
| `CMP.LST` | NUL-separated list of 96 paths under `\SystemSD\REFER001\` (coord/icadm×47/index/point×47 `.dat`) — the unit sees this card as **`\SystemSD`** | p1 |
| Sector 1 | ASCII `CLARION ID` then zeros | raw |
| Sector 16384 (byte 0x800000) | FAT dir entry, volume label `NCG2K2_16G`, attr 0x08, date 0x4379 = **2013-11-25**, time 0xAA69 = 21:19:18 | raw |

Reading of `DB_INFO.TXT` **[likely]**: `GJPNX` = Japan map product code, `15-02` = Feb-2015 map edition, `485197200-002` = Nissan/Clarion part `485-1972-00` rev 002, `201500000` = 2015 data year. `NCG2K2_16G` **[guess]**: "NCG2" platform (cf. `ddi_ncg.dll` in the firmware) + "K2" variant, 16 GB card.

## 2. Firmware images in the unpartitioned areas

The sectors outside the partitions hold Windows CE ROM images. Each starts with a little-endian length dword, a filename `XXXXXXXX.NNN`, a `SUM4` checksum tag, a Clarion part number `470-xxxx-xx`, then `NKOK`/`ECEC` (standard WinCE ROM signatures). ~~CPU is **Renesas SH-4A** **[likely]** (module names `*_sh4a.dll`, `*_spu2.dll`, `*_vpu5hd.dll`).~~ **Superseded by [05](05-ce-rom-extract.md) §3:** the CPU is an **ARM Cortex-A9** in a Renesas R-Car M1A (R8A7778) running Windows Embedded Compact 7 **[confirmed]**. The `_SH4A`/`_SPU2`/`_VPU5HD` DLLs are ARM DirectShow filters that offload to the SoC's SH-4A core and its media IP blocks.

| Start sector | Byte offset | Name | Part no. | Size (hdr dword) | Contents (module names seen) |
|---|---|---|---|---|---|
| 65536 | 0x2000000 | `G314JLNI.066` | 470-5121-12 | 0x54C8E8 (5.3 MiB) | WinCE browser/shell pack: iexplore, wininet, urlmon, mshtml, explorer, ctlpnl, **clock.cpl**, Software\Microsoft\Clock |
| 157696 | 0x4D00000 | `G214JLNI.066` | 470-5120-12 | 0x1D50400 (29.3 MiB) | **Main app image**: navi.exe, vehicle.exe, consult.exe, `evtimercc.dll`, `evcc.dll`, `evnoticecc.dll`, `hvaccc.dll`, `etcscc.dll`, `sipccjp.dll`, `digitaltv.exe`, `objdll.dll`, `apptimerdll.dll`, `comfortcc.dll`, `timezones.pdb`; mostly compressed (entropy 7–8) |
| 667648 | 0x14600000 | `UP14XNNI.139` | 470-4651-16 | 0x18E2058 (24.9 MiB) | OS + drivers: **navdrv.dll** (GPS), `carplay.exe`, `antitheft.exe`, updaters (`hdupdate`, `dabmicomupdate`, `fullsegupdate`) |
| 749568 | 0x16E00000 | `PM13XKNI.039` | 470-4650-14 | 0x127C25C (18.5 MiB) | OS + drivers (similar set to UP14, no CarPlay seen) |
| 790528 | 0x18200000 | `OIXXXVNI.004` (container tag `BASS`) | 470-5049-00 | — | unknown data container |
| 29965064 | 0x3927611FC | `SKINSK18NNNI.183` | 470-6253-48 | — | **Correction (#32):** not a separate image. This is the 36-byte trailer of hidden p2 `/SkinChange/002/substance.skn` (sectors 29925953–29965064). See [11](11-skin-pipeline.md). |

**Caveat [important]:** these images may not all belong to one unit generation. `UP14XNNI` includes `CarPlay.exe`, which a 2015 LEAF unit would not normally have. The skin also has strings for many models (GT-R style "ACCEL G / TOTAL TIME" meters, Facebook/Twitter widgets). The card may be a reused/refurbished SystemSD, or Clarion ships one image set for a whole family. Coordinate with the `raw-areas` notes.

## 3. Vehicle: this is a **Nissan LEAF** nav [confirmed modules, likely vehicle]

`G214JLNI` contains Shift-JIS debug-shell help text (≈0x5843000–0x584A800) for LEAF-only features:
- `evnavi` commands: battery remaining / catalog capacity (0–81760), SOC display, HVAC power use per 5 s, motor power.
- **EV timer** (`Evtimer`, `evtimercc.dll`): タイマー充電 (charge timer), タイマーエアコン (climate timer), CAN frames **5B3** / **5F9**, `remaining_time_200V_6kW`.
- Debug paths `C:/WINCE500/5F9TIMER1DATA.txt` (WinCE 5.0 build tree **[likely]**).

Skin strings confirm LEAF UI: "Charge Timers", "A/C-Heat Timers", "Time required to reach 100% charge — Approximately 7.5 hours / 15 hours", "Charging Station", "Energy Info."

## 4. How the clock works — firmware evidence

### 4.1 GPS → system clock, with the time zone hard-coded to Tokyo [confirmed strings, likely behaviour]
In `navdrv.dll` (inside `UP14XNNI`, ~0x1533D400–0x1533E600, UTF-16LE):
```
NavDrv >> GPS:SetTimeZoneFromSystem SetTimeZoneInformation ret = %d, Error = %d
Tokyo Standard Time
Tokyo Daylight Time
NavDrv >> GPS:SetTimeToSystem >> Invalid parameter(s)!
EVENT_NAV_TIMEDISPLAY_TRIGGER
GPS:SerchHeadPosNmea / SerchHeadPosUbx   (NMEA + u-blox UBX receiver)
```
hexdump @0x1533DB4C: `54 00 6f 00 6b 00 79 00 6f 00 20 00 53 00 74 00 …` ("Tokyo Standard Time\0Tokyo Daylight Time\0").
So the GPS driver fills a `TIME_ZONE_INFORMATION` with the Tokyo names and calls `SetTimeZoneInformation`, then sets system time from GPS (UTC). I could not find the bias constant (−540 min) as a plain literal. SH-4 code builds immediates in ways a byte search misses, so this needs disassembly.
The WinCE `timezones` table also holds `(UTC+12:00) Auckland, Wellington`, `(UTC+09:00) Osaka, Sapporo, Tokyo` etc. The OS *can* do NZ time; the nav driver just forces Tokyo. **[likely]**

This matches the owner's observation that the unit shows **UTC+9**. For NZ: JST is 3 h behind NZST (UTC+12) and **4 h behind NZDT** (UTC+13, in force on 2026-10-24).

### 4.2 Time service in the app: GMT + offset [confirmed names]
`objdll.dll` exports/uses `OBJ_Time_readGMT`, `OBJ_Time_readLocalTime`, `OBJ_Time_addEvCondOffset`, `OBJ_Time_addEvCondValid`, `OBJ_Time_getObjID`. A debug command reads `11:OBJからのオフセット時間変化` ("offset-time change from OBJ"). The app keeps GMT and an offset internally **[likely]**.

### 4.3 The nav pushes its time to the LEAF VCM [confirmed strings]
Shift-JIS message names in `G214JLNI`:
- `VCMの時刻修正要求` → `MSG_TYPE_VCAN_EVTIMER_REQ_SET_CLOCK` ("request VCM clock correction")
- `VCM時刻修正完了応答` → `MSG_TYPE_VCAN_EVTIMER_ACK_SET_CLOCK`
- `VCM時刻不正通知` → `MSG_TYPE_VCAN_TIME_DIFFERENT_WARNING`, flag `TimeDifferent_Flg`
- `現在時刻変更要求` → `MSG_EVTIMER_CC_CHG_CURCLOCK`
- debug: `9:時刻修正フラグ設定` (set clock-correction flag)

Skin dialogs: "The time of the timer unit and the navigation unit do not match." / "Please correct the time of the timer unit" / "Fixing clock" / "The clock has been fixed" / "Timer unit current time:" / "Modification time:" / "Correct time".
**Implication:** the LEAF charge/climate timers run on the VCM clock, which the nav corrects from its own (JST) time. A wrong nav time also makes the **charge timers fire at the wrong local time**. Any fix should be checked against the timers.

### 4.4 User-facing clock screens [confirmed IDs; options for JP build unknown]
Screen IDs in the skin (UTF-16LE, ~0x3916ABBB4–0x3916ABEEC): `SET_CLOCK_SETTING_MENU`, **`SET_CLOCK_TIMEZONE_SETTING_MENU`**, **`SET_CLOCK_SUMMERTIME_SETTING_MENU`**, next to `SET_LANGUAGE_SELECT_LANGUAGE_LIST`. Settings top-level strings include `Clock`; options include `24-hour Format`; home widgets `Digital Clock` / `Analog Clock`.
I found no plaintext time-zone option strings (no "Time Zone", "Summer Time", "Daylight" in the English table; no 時計/タイムゾーン/サマータイム in UTF-16/SJIS/UTF-8/EUC outside the WinCE OS strings). The Japanese string tables are probably compressed. Since these screen IDs sit beside the language selector, the skin framework is probably shared with export builds, and the JP build may hide the time-zone/summer-time screens **[guess]**.

### 4.5 Hidden service menu has a manual clock setter [confirmed IDs]
Self-diagnosis ("SLF_") tree: `SLF_SYSTEM_DIAGNOSTIC_DETAIL_MENU`, `SLF_CONFIRMATION_ADJUSTMENT_MENU` ("Confirmation/Adjustment"), with **`SLF_CLOCK_SET`** ("Clock Settings"), `SLF_DISPLAY_TOUCH_PANEL_CALIBRATION`, `SLF_VEHICLE_CAN_MONITOR`, `SLF_NAVIGATION_SENSOR_MONITOR`, `SLF_NAVIGATION_SPEED_CALIBRATION`, Config Reset, User Data Reset, Factory Reset. Strings next to "Clock Settings": ` Hours`, ` Minutes`, `Year/month`, `Sun`, `+/-`.
**Update (2026-10-25):** the backend is DiagnosisCC `SET_TIMEINFO`; it edits **UTC** and seeds the GPS receiver (UBX-AID-INI) through Navi SNSMGR rather than setting local time. See [08 §15](08-nz-clock-implementation.md#15-manual-clock-menu-with-the-gps-antenna-disconnected-static-trace) **[confirmed static]**.
Also `SK_SCT_CLOCK_SET_CLICK` and a hard-key transition `SK_HWK_MENU_CLICK` → `SLF_CLOCK_SET` (offset 0x391646C80–0x391646D6C). The entry key sequence is not in the strings. See §5.
Whether `SLF_CLOCK_SET` changes the displayed clock *persistently* or gets overwritten by GPS at the next fix is **unknown**.

## 5. Map DB time-related data

### `DBDIR/BHOLIDB` / `BHOLIDD` = Japanese public-holiday calendar 2015–2034 [confirmed]
- Container: Clarion paged DB, 4 KiB pages; file header magic `flhb`, page tags `flmb`, `ramb`, `racm`, `ratm`, `raim`, `sbmb`, `sgmb`; build stamp `2015/03/11-22:05:51` at 0xE4. (Same container as the other DBDIR files; format is the config-files/map topic.)
- Payload page at **0x28000** of `BHOLIDB` (tag `3c 03 09 00`), big-endian:
  - `u16 total=412`, `u16 nyears=20`, then 20× `{u16 year, u16 first_index, u16 count}` (2015…2034), then 412× `u16` records.
  - record = `month<<12 | day<<7 | type` (type in low 7 bits, multiples of 4: 4=元日, 8=成人の日, 12=建国記念日, 16=春分, 20/24/28=GW, 32=海の日, 36=敬老, 40=秋分, 44=体育, 48=文化, 52=勤労感謝, 56=天皇誕生日(12-23), 60=昭和の日/国民の休日, 64=振替休日/other).
  - 2015 decodes to: 01-01, 01-12, 02-11, 03-21, 04-29, 05-03..06, 07-20, 09-21..23, 10-12, 11-03, 11-23, 12-23. This matches Japan's actual 2015 holidays.
  - Pre-computed in 2015: keeps 12-23 Emperor's Birthday after 2019 and lacks 2019 enthronement days and the 2020/21 Olympic shifts.
- Full decode: `~/nissan/work/unit-and-clock/bholidb_decoded.txt`; decoder: scratch `bholid.py` (copy in work dir).
- **No time-zone/UTC-offset data.** The holiday table probably feeds traffic prediction (weekday vs holiday patterns) **[guess]**.
- Grep of all p1 files <12 MB for `JST|UTC|GMT|+0900|TimeZone`: only random hits inside compressed blobs (checked bytes).

## 6. Web research (full report with every URL: `~/nissan/work/unit-and-clock/web-research.md`)

**Identification**
- The Nissan "MM" dealer navs (MM114D/MM115D/MM514D/MM515D/MM316D) are **Panasonic**, and "MP" are **Pioneer**. The **Clarion** line is **MC** (MC312D…MC315D). Sources: [MM115D manual](https://nissan.co.jp/OPTIONAL-PARTS/NAVIOM/DOP/manual_mm115d-aw.pdf), [MP315D manual](https://www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/DOP/manual_mp315d-aw.pdf), [MC315D manual](https://www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/DOP/manual_mc315d-aw.pdf), [Clarion Nissan MC support](https://archive.clarion.com/jp/ja/user-support/update/navi-software/nissan/index.html).
- The MC315D manual (Apr-2015) says the shipped SD holds "MAPPLE … 2015年2月版", which matches `15-02`. Map + program both live on the "MAP DATA" SD, and retail SD cards don't work. Its manual print no. "280-9365-00" has the same `xxx-xxxx-00` format as the card label `485-1972-00` and firmware `470-xxxx-xx` **[guess: Clarion part-number scheme]**.
- No web hits for `GJPNX`, `NCG2K2_16G`, `G314JLNI`, `485-1972`.
- **LEAF:** Nissan hosts a LEAF-specific nav manual. Its clock page, "時計を設定する" ([nissan.co.jp](https://www.nissan.co.jp/OPTIONAL-PARTS/NAVIOM/LEAF/NAVI/CONTENTS/guid-56254db3-d15d-4225-8ccd-06e37f8daeac.html)), gives the path **メニュー → 設定 → その他設定 → 時計**. Options: 常時表示 ON/OFF, 24時間表示, **オフセット調整 −/+ in 1-min steps**. "表示されている時刻は、GPSシステムにより、ほぼ正確に表示されます。" No time-zone item. That page has no edition/model shown, so which LEAF generation it covers is **[unconfirmed]**.
- The US LEAF manual (2013 SV) says "The charging timer starts and stops charging based on the time displayed on the navigation system screen" ([mynissanleaf thread](https://mynissanleaf.com/threads/answered-q-how-2-set-clock-on-dash-board-2013-sv-vs-s.14742/)). The same thread has a 2014 JDM X-grade owner who reports that changing the settings didn't affect the clocks.

**Clock fixes seen in the community**
- **Navi-Solutions (NZ) "Nissan Leaf Japanese to English Carwings Conversion with NZ/AU maps"**: for "ZE0 and AZE0 Carwings systems", "Conversion is carried out via an SD card". Includes "Local time and date", NZ$199 ([product page](https://www.navi-solutions.com/products/nissan-leaf-japanese-to-english-carwings)). A 2019 article on the OEM Audio/Navi-Solutions conversion: "the time zones are now all available for New Zealand and Australia" ([EVs & Beyond, 2019-01-25](https://evsandbeyond.co.nz/?p=40859)).
- An NZ YouTube video titled "How to set the clock on JDM Nissan Leaf with Carwings" exists, but I couldn't read its content, so the steps are unverified.
- Non-Nissan analogue: a JDM Toyota Harrier in NZ has a nav clock "locked to GPS time with the time zone set for Japan" and no fix ([clublexus](https://www.clublexus.com/forums/rx-1st-gen-1999-2003/73501-harrier-clock.html)).
- **No published hidden-menu key combo** for Clarion-made Nissan navs was found (searched 隠しコマンド / 診断モード / サービスモード).
- Clarion's Nissan update service has ended ("地図・プログラム更新サービスは終了しました", [Clarion](https://archive.clarion.com/jp/ja/user-support/software/sd/smart-access-updater/nissan/index.html)).
- **GPS week rollover (Apr 2019):** no Clarion/Nissan notice found. Symptom test: if the time is exactly JST with the right date, it's the TZ, not rollover. A date ~19.6 years off would point to rollover.

## 7. Candidate approaches to fix the time (ranked lowest → highest risk)

| # | Approach | What it fixes | Risk | Basis |
|---|---|---|---|---|
| 1 | **Live with it / hide it**: nav 時計 常時表示 OFF, read the meter clock. Set LEAF charge/climate timers **3 h earlier (NZST) / 4 h earlier (NZDT)** than the wanted local time. | Display only; timers via mental offset | None | LEAF nav manual; §4.3 |
| 2 | **オフセット調整** ±59 min | Minute drift only, not hours | None | LEAF nav manual / MC315D p.19 |
| 3 | **Check the meter (cluster) clock** separately: on some LEAF trims it's independent of the nav | Gives a correct visible clock | None | mynissanleaf thread |
| 4 | **Explore the service menu `SLF_CLOCK_SET`** (Confirmation/Adjustment → Clock Settings, Hours/Minutes) | Possibly a manual hour set. GPS may overwrite it at the next fix **[unknown]** | Low–medium: the same menu has Config Reset / User Data Reset / Factory Reset. Entry key combo unknown. Back up the SD image first (done) | Firmware IDs §4.5 |
| 5 | **Commercial NZ conversion** (Navi-Solutions, OEM Audio / EVs Enhanced) for ZE0/AZE0 Carwings: SD-based English + NZ maps + local time/time zones | Hours, DST, language, NZ maps; probably timers too | Low–medium (vendor-supported, NZ$199; replaces/rewrites SD content, keep the original card/image) | navi-solutions.com, evsandbeyond.co.nz |
| 6 | **Firmware analysis → patch**: extract `navdrv.dll` (UP14XNNI) / `objdll.dll` / evtimer from the WinCE ROM images, disassemble (ARM, see 05 §3), change the forced "Tokyo Standard Time" TZ or enable the hidden TIMEZONE/SUMMERTIME screens, and rebuild the SUM4 checksum | Full fix in principle | **High**: checksums/signature (`CWS/CERT/ca.der`) may block it, and a bad image can brick the unit. Research only; never write to the original card | §2, §4 |
| 7 | **Replace the head unit** (NZ-spec/aftermarket) | Everything | Medium (cost; may lose LEAF EV screens/timer integration) | — |

Recommendation: do 1 + 3 now (free). If the owner wants a proper fix, 5 is the realistic one. Treat 4 as an experiment only after the entry sequence is known.

## 8. Open questions
1. Exact unit code (sticker: Nissan 25915-xxxxx / B8260-xxxxx, Clarion QY-xxxxNx). Is it the LEAF factory Carwings/EV nav, or a dealer MC315D with LEAF integration?
2. Which raw-area image set does *this* unit actually boot? `UP14XNNI` contains CarPlay, which is odd for a 2015 car (§2 caveat). Is the card reused?
3. Does `SLF_CLOCK_SET` persist against GPS? How is the service menu entered (Clarion/Nissan usually use a long-press combo on MENU/INFO/day-night + ignition)?
4. Are `SET_CLOCK_TIMEZONE_SETTING_MENU` / `SUMMERTIME` compiled into the JP app but unreachable, or only in the shared skin?
5. ~~Is the SKIN image at sector 29965064 live, or a remnant?~~ Answered: it is the trailer of the live p2 file `SkinChange/002/substance.skn` ([11](11-skin-pipeline.md) §1.1).
6. Owner check: does the nav show the correct date and exactly JST (NZ −3/−4 h)? That rules out GPS rollover.

## 9. Suggested next steps
1. Owner: photograph the unit sticker and the version screen (`情報 → バージョン情報`), and note nav time vs real NZ time and the date.
2. Write (or use an existing) WinCE ROM extractor (e.g. `dumprom`/`nbfdump`-style parsing of the `ECEC`/ROMHDR) on carved copies of `UP14XNNI`, `PM13XKNI` and `G214JLNI`. Pull `navdrv.dll`, `objdll.dll`, `evtimercc.dll` and `setcc.dll`, then load them in Ghidra (`ARM:LE:32:v7`, see 05 §3; extractor: `tools/ce-extract/`) to find the `SetTimeZoneInformation` call and the bias source.
3. Search the decompressed app for the hard-key sequence that opens `SLF_*` (the `SK_HWK_*` transition tables near 0x391646C80).
4. Ask Navi-Solutions what their LEAF conversion changes (firmware vs skin/config), and whether timers follow NZ time afterwards.
5. Coordinate with the `raw-areas` and `config-files` notes on the SUM4 header format and the `flhb` paged-DB container.

## Artifacts
- `~/nissan/work/unit-and-clock/raw_strings.txt` — ASCII+UTF-16LE strings of both unpartitioned areas with absolute byte offsets (339,706 lines)
- `jp_time_hits.txt`, `evtimer_strings.txt` — Shift-JIS clock/EV-timer strings
- `ui_clock_settings.txt`, `ui_clock_ctx*.txt` — skin string contexts
- `g314_region.bin` — carved copy of the G314JLNI image (5.3 MiB)
- `bholidb_decoded.txt`
