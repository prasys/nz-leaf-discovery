# HMI (G214) extraction, how the clock is computed, and a file hook

Tools (stdlib, `python3 -I`):

| tool | what |
|---|---|
| `tools/ce-extract/mtcp.py <G214 slot>` | Unpacks the MTCP container (LZ4 blocks) and appends the raw remainder → `G214JLNI.066.nb0` |
| `tools/ce-extract/ceromx.py G214JLNI.066.nb0 <out>` | Same extractor as [05](05-ce-rom-extract.md) |
| `tools/ce-extract/slotsum.py [image]` | Read-only check of the SUM4 slot sums and MTCP chunk sums |
| `tools/hmi-skin/typelib.py <dll> [regex]` | Lists COM dispinterfaces and DISPIDs from an embedded MSFT typelib |

## 1. G214 = MTCP(LZ4) + raw tail → one CE image [confirmed]

```
+0x00 "MTCP" u32 count=11 u32 0x200000
+0x20 11 x {u32 sectors, u32 raw, u32 comp, u32 check, 16 x 0}   e.g. {0x86B, 0x200000, 0x10D49F, 0xB79471C1}
+0x200 chunk 0 ...  each chunk = one raw LZ4 block
```
- Chunk 0 starts `FB 1A | 78 8C 05 40 …`: token 0xFB = 15+0x1A = 41 literals, then offset `01 00`, match 11+4. All 11 chunks decode to exactly their raw size (0x200000, last 0x7FE00), and `ECEC` lands at +0x40 of the output.
- The u32 `check` is the **32-bit word sum of the chunk's compressed bytes** (see §6) **[confirmed]**.
- The 0x1412400 bytes after the last chunk (+0x93E000) are the uncompressed rest of the same image. ROMHDR VA 0x8B0CF918 is at offset 0x288F918 of chunks+tail. The modules inside use the same LZX as [05](05-ce-rom-extract.md).
- Result: **287 modules, 43 files, 0 errors**, including OBJDLL.dll, Navi.exe, NaviSetCC.dll, EvTimerCC.dll, Vehicle.exe, MaintenanceCC.dll, ScreenStateCC.dll and `ReleaseMain.skn`.

## 2. Where the displayed time comes from [confirmed unless tagged]

```
GPS (UTC) ──Navi.exe OBJ_Time_writeGMT──► OBJ_Time.GMT
                                            │
local = GMT + zone(+0x14) + dst(+0x1C) + offset(+0x20)       OBJDLL OBJ_Time_getLocalTime / getTotalOffset (0x2C3B8 / 0x2C360)
                                            │  units: 1/100 s (360000 = 1 h)
OBJ_Time_readLocalTime ──► Navi, Vehicle(EvTimer → VCM over CAN), BT, Telema …
```
- The HMI does **not** use the CE timezone. navdrv.dll's forced `Tokyo Standard Time` (see [#22](https://github.com/prasys/nz-leaf-discovery/issues/22)) only affects the CE layer.
- **Correction (NZ review):** the original diagram interchanged the offset and DST field labels. `OBJ_Time_writeDst` (`0x40e2cd30`) passes offset `0x1c` to the partial-write helper; `OBJ_Time_writeOffset` (`0x40e2cdf0`) passes `0x20`. The sum is unchanged. The app's independent Japan default is in `FUN_40e2c4d4`; see [07](07-nz-clock-design.md) for the trace and a proposed CE/NZ integration.
- **User offset** (NaviSetCC `FUN_4285ea98`):
  `offset = (ExpOffsetHour − 12) · 360000 + (ExpOffsetMin − 59) · 6000` → `OBJ_Time_writeOffset`, omitting unset fields. **Correction (12 §1.4):** raw defaults are `0x80000000` (unset), initialized by `OBJ_ExpSet_initPrm` (`0x40e485fc`); 12/59 are NaviSetCC's local fallbacks, both representing zero. The setters support **±12 h and ±59 min**. The stock JP UI exposes only minutes; the later [hour-row patch](12-hour-offset-ui.md) exposes the hour setter.
- **Hour setter has no area check:** `SetExpOffsetHourSetting` (NaviSetCC `FUN_4286cbec`, DISPID 0x6A) accepts −12…+12, writes `ExpOffsetHour = h+12` and re-applies the offset.
- **DST** (`FUN_4286ccc4`): AutoDst on → `OBJ_Time_writeDst(360000)`. This is a fixed +1 h toggle, not a rule-based switch.
- **Zone list is gated by model area** (`FUN_4286cd80`, `FUN_4285e108`): area < 0x20 gets no zones (JP is 0x10, see [#22](https://github.com/prasys/nz-leaf-discovery/issues/22)). 0x20/0x21 and 0x70 get 9, 0x30/0x40 get 76, 0x62 gets 7. `ScreenStateCC` references `MODEL_AREA_JAPAN` next to `SET_CLOCK_TIMEZONE/SUMMERTIME_SETTING_MENU` **[likely the menu gate]**.
- **Setting storage [confirmed, later trace]:** `OBJ_Setting` → `ExpSet` block (32 bytes at Setting+0x40). Words [0] language, [5] ExpOffsetHour, [6] ExpOffsetMin, [7] AutoDst. The earlier search assumed a raw hour default of 12 and missed the unset sentinel. The record is at LBA **808677 / 809821 +0x1A0**, inside SRST areas 807648 / 808792. `FUN_40e50564` restores its 0x20 bytes verbatim; see [12 §1.4](12-hour-offset-ui.md#14-storage-confirmed) and `expset_scan.py`.

NaviSetCC DISPIDs (`typelib.py`): 0x69/0x6A Get/Set ExpOffsetHour, 0x6B/0x6C ExpOffsetMin, 0x6D/0x6E ExpAutoDst, 0x6F/0x70 TimeZone.

## 3. Skin (UI) notes
- The active skin is `SkinChange/002/substance.skn` on hidden p2 (sector 29965064 is inside p2). It is a tagged record stream `[u16 len][u16 kind][u32 type][payload]` from 0x40 to 0x51B9F0 (78,668 records), then image resources (zlib = raw pixels).
- Screens and logic are compiled bytecode (type 0x8402 records) with screen names as literals. COM is called by DISPID: no NaviSetCC member name, not even `ExpLanguage`, appears in the skin. **Later result [confirmed]:** [12](12-hour-offset-ui.md) decodes all 10,215 code records and repurposes the minute row for hours; the owner reports the corrected head-unit clock.
- commondll also loads `\USB Disk\SkinChange\00N\Substance.skn` (skin change from USB).

## 4. Existing file hooks found
| file | read by | effect |
|---|---|---|
| `\USB Disk\RunProgram.s`, `\USB Disk2\RunProgram.s`, `\SystemSD\RunProgram.s`, `\UserSD\RunProgram.s` | G214 MaintenanceCC.dll `FUN_42c30300`/`FUN_42c2fb18` | Reads ≤512 bytes **ASCII**, `mbstowcs`, splits at the first space → `CreateProcessW(prog, args)` [confirmed] |
| `\USB Disk\EnableDbgShell.sh`, `\USB Disk2\EnableDbgShell.sh`, `\SystemSD\EnableDbgShell.sh`, `\UserSD\EnableDbgShell.sh` | MaintenanceCC (same table); PM13 AppLaunch.dll `FUN_ef4883d4` at boot (if model code ok and boot mode 2/7) | `CreateFileW("DSD1:")` + `DeviceIoControl(…, 0x80012020)`, probably enables the serial debug shell [likely] |
| `\SystemSD\UpDateVsramErase.key`, `\SystemSD\UpDateStop.key` | UP14 PRGUpdate / UpdateMng | updater control flags |
| `\USB Disk\CL_MAP_STATELOGOUT.KEY`, `CL_MENU_STATELOGSW.KEY` | MaintenanceCC | logging switches |

- **Trigger:** the RunProgram/EnableDbgShell check runs inside `MaintenanceCtl` method DISPID 11 = `SramFlush` (typelib-confirmed name; vtable 0x42C21DE0 slot 17 → `FUN_42c304f0`, and `FUN_42c304f0` is the only static caller of `FUN_42c30300` found in the module — observed xref, not a proven-exclusive reachability claim). The UI binding is unknown: which screen button, if any, calls DISPID 0x0b is unproven (skin COM calls are by DISPID, and the skin carries no SramFlush/SRAM/RunProgram names). It is not known to run at boot.
- **SramFlush call order (2026-10-25 trace of MaintenanceCC, maint_g214 project):** param==0 → no-op `FUN_42c32138`; then `FUN_42c31eb4`/`FUN_42c34c88`/`FUN_42c34b78` enqueue `{0x20000, param, 0, 0}` into a 30-entry ring + `EventModify(SET)`; **then** `FUN_42c30300` (the hook scan) runs. The actual store work is asynchronous in the `CMaintenanceMng` worker thread (proc `0x42c32c18`), so it is not serialized against anything `RunProgram.s` launches. Worker wait-result 3 → dequeue → dispatch on `cmd & 0xffff0000`; `0x20000` → `CSramCtl` `FUN_42c34228` → `FUN_42c34110(param)`: **param==0 → dump branch** (three steps of `CreateDirectoryW(base)` + `CreateFileW(GENERIC_WRITE, CREATE_ALWAYS)` writing dump files `%s\VSram_All.bin` (128 KB records #0x1fe/#0x1ff via `DeviceIoControl 0x1112000`), `%s\VFlash_All.bin` (#0x1fd), and `%s\VSram_SD_All.bin` (`CSramCtl::WriteSdData`: `DSK1:` + `DeviceIoControl 0x75c08`, LBAs 0xc4000 ×1 + 0xc5000 ×0x26ff ≈ 4.9 MB — inside the settings/VSRAM band 800768–818431)). leafsdtools uses the same ioctl and block numbers for QY8 "SRAM"/"VFlash" ([13](13-prior-art-leafsdtools.md) §3); **param==2 → `ErrorLogFlush()`**; other params → no traced action. The dumps' runtime destination (`%s` base) is unresolved; whether the settings store itself is modified is unproven. Full detail: `~/nissan/work/nz-clock/menu-investigation/menu-report.md` [confirmed at decompile level; dispatch link likely].
- The same interface (typelib, 57 members) also exposes `SramClr` (0x0c), `OmlFlush` (0x0d), `CopySramFile` (0x0e), `ClearFlashMemory` (0x32), `GetVersionInfo` (0x36) and `SystemReset` (0x38); their individual effects were not traced here — treat `SramClr`/`ClearFlashMemory`/`SystemReset` as state-changing by name, and do not use any of these menu-invokable methods as a launcher. `GetVersionInfo` is a read-only getter (reads `REGISTRY` values `Module`/`Module_Raw`). No Program/Update member in the parsed typelib; the Program Update menu handler is unknown (skin tokens only, below).
- Coredll ordinals verified: 168 CreateFileW, 170 ReadFile, 172 GetFileSize, 1068 strlen, 76 mbstowcs, 493 CreateProcessW, 179 DeviceIoControl, plus 4/5 Enter/LeaveCriticalSection, 160 CreateDirectoryW, 492 CreateThread, 494 EventModify, 496 Sleep, 498 WaitForMultipleObjects, 553 CloseHandle, 545 NKDbgPrintfW, 719 sprintf.

## 5. Proposed approach (for a human to test; nothing written to a card or car)

**Superseded (2026-10-25):** the NZ-time helper in step 2 was never built. The working route is the skin-only hour row in [12](12-hour-offset-ui.md), which calls `SetExpOffsetHourSetting` from the stock Clock screen. Step 2's DST rule is still relevant to [#2](https://github.com/prasys/nz-leaf-discovery/issues/2).
1. **Read Version Information only.** Enter the documented service menu (below) and record the Version Information screen. This is a read-only getter view (registry/module metadata). *(2026-10-25: the earlier proposed probe — press SRAM flush with `RunProgram.s` = `\Windows\explorer.exe` on a USB stick — is withdrawn: the traced flush handler creates dump files on the unit, the dumps' destination is unresolved, and no screen→method binding is proven, so this is not a "writes nothing" test.)*
2. **NZ-time helper (to write):** a tiny ARM CE exe. It would call OBJDLL exports `OBJ_Setting_getObjID` + `OBJ_Setting_writeExpOffsetHour(15)` (JST+3 = NZST) and `OBJ_Time_getObjID` + `OBJ_Time_writeOffset`. It would also compute NZ DST from `OBJ_Time_readGMT` (last Sun Sep 02:00 → 1st Sun Apr 03:00) and use +4 h in summer. This assumes OBJDLL's shared object store is reachable from another process **[guess, to verify]**. The vehicle/timer path likely follows this clock: the verified consumer is **Vehicle.exe**, not EvTimerCC.dll itself (see [07](07-nz-clock-design.md)); the final CAN/VCM and dash effects remain untested.
3. If the hook only runs from the service menu, rerun the helper twice a year or after a reset. A boot-time hook would need `EnableDbgShell.sh`/AppLaunch, or a skin change.

**Menu context (2026-10-25).** Nissan bulletin NTB15-001E pp7–8 (<https://static.nhtsa.gov/odi/tsbs/2021/MC-10190166-0001.pdf>; audio OFF → MAP3 → audio PWR ×2 → MAP1) documents access to a Confirmation/Adjustment menu with Version Information; the owner reached it and its submenus. This is the documented access path — the exact JDM-firmware screen→method binding (any button calling DISPID 0x0b) remains unproven; skin COM calls are by DISPID and the skin has no SramFlush/SRAM/RunProgram names. Program Update skin tokens (parent evidence, coordinator-menu-evidence.json): label at skin file offset 0x182f24, `SK_SCT_SOFTWARE_UPDATE_CLICK` at 0x22370c, `SK_SCT_POP_PRG_PROGRAM_UPDATE_OK_CLICK` at 0x27cb2c, `…_CANCEL_CLICK` at 0x27cbac — label/event tokens only; the action handler is unknown. Owner's Version Information reading: **TCU software redacted, ITM software 066, ITM configuration part number redacted** [confirmed, owner report]. ITM "066" is consistent with the extracted G214JLNI.**066** image family [likely]; these strings are registry/module metadata readouts, so they do **not** fingerprint patched DLL bytes. Safe observation only: record the Version Information screen; never use SRAM flush/clear/initialize/erase/config-reset/Program Update items as "harmless launchers" or probes. Known unknowns: dump-file base path (`CSramCtl` vtable slot-0 getter), exact driver-side effect of `DeviceIoControl 0x75c08`/`0x111200c`, the Program Update handler, and the wait-handle registration that fixes which wait index reaches the command dequeue.

## 6. Slot integrity values (issue [#11](https://github.com/prasys/nz-leaf-discovery/issues/11)) [confirmed]

Source: UP14 `PRGUpdate.exe`: `chkSumDat32` (`FUN_0001d1c0`), `NkFileSumCheck` (`FUN_0001f838`), `Nk2FileSumCheck` (`FUN_0001f654`). Verified on the card image with `tools/ce-extract/slotsum.py`.

| value | algorithm | verified |
|---|---|---|
| **SUM4** (slot header +0x30 `"SUM4"`, +0x34 sum) | sum of LE u32 words over the `size` bytes after the 512-byte header (size = header +0x00, zero-padded to 4), mod 2^32 | G314 (sector 65536) stored = calc = 0x27F57A1E; G214 (157696) stored = calc = 0x1E072FBC |
| **MTCP chunk check** (+0x2C + 32·k) | the same word sum over that chunk's compressed bytes | all 11 G214 chunks match (e.g. chunk 0 0xB79471C1) |
| NK2 variant (UP14/PM13) | `Nk2FileSumCheck`: `"SUM4"` at image +0x80 with sum at +0x84 and size at +0x88; summed over the image with bytes +0x30..0x35 and +0x84..0x8B zeroed | **verified**: UP14 `EA9437AA`, PM13 `F22493E0`. leafsdtools' wider exclusion (+0x30..0x3F, +0x84..0x8F) gives the same result, since those extra bytes are zero ([13](13-prior-art-leafsdtools.md) §2.2) |

- Slots 667648 (UP14) and 749568 (PM13) have no SUM4 in their header sector. Their `SUM4` record is inside the image at +0x80 (`… 53 55 4D 34 aa 37 94 ea 58 20 8e 01` for UP14).
- These sums only protect against corruption. They are not signatures. Whether the bootloader (BL102, internal flash) checks anything else, for example the keyed blobs at sector 800768 ([#10](https://github.com/prasys/nz-leaf-discovery/issues/10)), is **[open]**.
