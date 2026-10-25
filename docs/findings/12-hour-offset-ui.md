# Hour offset in the normal Clock UI (refs [#1](https://github.com/prasys/nz-leaf-discovery/issues/1))

2026-10-25. **Start with §0** for the summary, assumptions and procedure. Static analysis, followed by a skin build, an owner-run write and an owner-reported car result (§7). No extracted code was executed. This extends the clock traces in [06](06-hmi-clock-and-hooks.md), [07](07-nz-clock-design.md) and [08](08-nz-clock-implementation.md). Ghidra projects: `~/nissan/work/ghidra/hour_offset_ui_{navisetcc,objdll,auirtdll}`. Exports: `~/nissan/work/hour-offset-ui/exports/`.

**Current result [confirmed, owner report; no independent capture]:** the Clock screen adjustment now changes hours and the head-unit clock shows correct NZ time. The 11-byte patch repurposes the minute row; its label still says “Minutes”, and minute fine-tuning is unavailable. +3 is NZST and +4 is NZDT on a JST base. Automatic seasonal switching, dash/timers and persistence remain follow-up work (§9). The exact selected value and running DLL bytes were not captured. The additional manual DST-toggle candidate in §8 is untested in the car.

## 0. Overview: what was done, what was assumed, how to repeat or undo it

This section is the short version for a newcomer. The rest of the file holds the evidence. It supersedes the firmware-patch route in [08](08-nz-clock-implementation.md) and the CE-bridge proposal in [07](07-nz-clock-design.md) as the way the clock is fixed today. Neither of those was deleted; they are history and groundwork for [#2](https://github.com/prasys/nz-leaf-discovery/issues/2).

### 0.1 What changed and what did not

- **Changed:** 11 bytes in hidden p2 `/SkinChange/002/substance.skn` (LBA 29925953). The Clock screen's minute row now calls NaviSetCC `Get/SetExpOffsetHourSetting` (DISPID 0x69/0x6A) instead of the minute pair (0x6B/0x6C), its button limits go from ±59 to ±12, and two event sinks swap so the label refreshes on the hour event. Offsets are in §2. **[confirmed, `cmp` of build vs source]**
- **Baseline:** the skin on this card was not stock when this work started. It had already been modified, which the baseline pins in `write_skin.py` and `hour_row_plan.py` record, and the hour-row edit sits on top of it.
- **Not changed:** no firmware. G214, UP14 and PM13 are not touched by this fix, and neither are the VSRAM store or the trailer of the skin. The value is stored by the unit's own setter when the owner presses + or −.
- **Still on the card from earlier work:** the fixed +13 G214 probe from 08 §8.1. It is believed dormant (a +13 base plus +3/+4 would overshoot NZ time) **[likely]**. Retiring it is [#5](https://github.com/prasys/nz-leaf-discovery/issues/5).

### 0.2 Assumptions

Each of these is something the fix relies on. Do not change one without saying so in a PR.

| assumption | confidence | evidence |
|---|---|---|
| The unit's base clock is JST (GMT + 9 h from the app's Japan default) | **[confirmed]** static + owner | OBJDLL `FUN_40e2c4d4` (07 §1); Time record reads +9 h zone (§1.4); owner saw JST before the fix |
| +3 = NZST (UTC+12), +4 = NZDT (UTC+13) on that base | **[confirmed]** arithmetic; **[likely]** in the car | the owner reports correct NZ time but did not record which value was selected (§7) |
| The hour value goes through `OBJ_Time_writeOffset` into `getTotalOffset`, which feeds the displayed clock | **[likely, strong]** | static trace §1.3; owner-reported working clock |
| The stored minute offset still adds, and it is 0 here | **[confirmed]** card read | ExpSet min word `0x3B` (= 0) in both copies (§1.4) |
| GPS updates write only GMT and leave the user offset alone, so reconnecting the antenna does not undo +3/+4 | **[likely, static]**; untested | `OBJ_Time_writeGMT` touches 0x00–0x0B only (§4, §4.1). The owner's manual Set Clock revert (§4.1) is a different mechanism |
| The offset persists across power cycles | **[likely, static]**; untested | successful restore keeps the Time record and ExpSet (§4). Nothing re-applies ExpOffsetHour at boot, so a Time-only reset would show +3 in the UI while running JST (§4). [#4](https://github.com/prasys/nz-leaf-discovery/issues/4) |
| The SD VSRAM copy is where the setting persists | **[guess]** | §1.4 reads the SD copy. The unit also keeps an internal-NAND SRAM (`FMD1:` blocks 0x1FE/0x1FF), see 06 §4 and [13](13-prior-art-leafsdtools.md) §3.3. Which one is restored first is open ([#6](https://github.com/prasys/nz-leaf-discovery/issues/6)) |
| The skin trailer value `0x0F6596FD` is not checked, or does not cover these bytes | **[confirmed]** for in-place builds | the unit accepted build `6a54198a` and the hour-row build with the trailer unchanged (§7) |
| The card's skin as found (already modified, `ea5b5a34…`) is the baseline | **[confirmed]** | the 11 baseline bytes are identical in `ea5b5a34…` and in build `6a54198a…` (§2) |
| The fixed +13 G214 probe does not run | **[likely]** | the clock does not overshoot (§7). The running G214 bytes were never fingerprinted (08 §14.3) |
| The unit loads this file from that exFAT location and size | **[confirmed]** | the writer checks the live exFAT entry, and the car shows the change |

### 0.3 Verified by the owner vs static only

| claim | status |
|---|---|
| The row changes hours and the head-unit clock shows correct NZ time | **owner report**, 2026-10-25, no photo or capture (§7) |
| Write landed byte-exact on the card | **receipt**: `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`, full read-back (§7) |
| Button range ±12, label refresh on the hour event | static decode; not separately observed |
| Survives GPS reconnect, power cycles, overnight | static only ([#4](https://github.com/prasys/nz-leaf-discovery/issues/4)) |
| Dash clock and charge/climate timers follow | static only ([#4](https://github.com/prasys/nz-leaf-discovery/issues/4)); Vehicle.exe reads local time incl. offset (§4) |
| Stored ExpSet hour word is 15 or 16 | not read back yet (§5 step 5) |

### 0.4 Known limitations

- The row label still reads "N Minutes" ([#3](https://github.com/prasys/nz-leaf-discovery/issues/3)). The suffix string is shared with two other labels (§2).
- Minute fine-tuning is gone while the row drives hours.
- No automatic DST. The owner moves +3 ↔ +4 by hand in late September and early April ([#2](https://github.com/prasys/nz-leaf-discovery/issues/2)). The v2 manual DST toggle (§8) is built and pinned but **untested and not written**.
- Car validation is still open ([#4](https://github.com/prasys/nz-leaf-discovery/issues/4)).

### 0.5 Repeat or roll back (owner runs `--apply`)

Use a card whose live `substance.skn` is one of the pinned builds in `tools/translation/write_skin.py` `BUILDS` (or the baseline skin `ea5b5a34…`). Agents prepare these commands; only the owner runs the `sudo`/`--apply` ones.

1. **Back up the whole card** with `tools/nz-clock/backup_card.py` (read-only on the device; writes a new directory under `~/nissan/work/nz-clock/backups/`). Pin its SHA256 by setting `NISSAN_BACKUP_SHA256` before running the writer ([BACKUPS.md](../BACKUPS.md) §2). Backup hashes are card-specific and not committed. The owner's backup is `20261024T073738Z/card-before-patch.img`.
2. **Build** (no card access):
   ```sh
   python3 -I tools/hour-offset-ui/hour_row_plan.py ~/nissan/work/translation/build/substance.skn   # checks the 11 baseline bytes
   python3 -I tools/hour-offset-ui/build_hour_row.py \
     --skin ~/nissan/work/translation/build/substance.skn --out ~/nissan/work/hour-offset-ui/build-v1
   ```
   Expect build SHA256 `ec1138c812d5bc111ad30d2e8937b0657be1f8092f832cefb67a83916bfa192b`, 20,025,376 bytes. A different hash means a different source; do not pin it without review.
3. **Preflight** (read-only; disk numbers change, so rediscover with `diskutil list` and check the card is in the Mac's reader, not the car):
   ```sh
   sudo python3 -I tools/translation/write_skin.py --device diskN \
     --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
     --build ~/nissan/work/hour-offset-ui/build-v1/substance.skn --work-root ~/nissan/work
   ```
   It must print `READ_ONLY_PREFLIGHT_PASSED`.
4. **Apply:** the owner reruns the same command with `--apply` in their own terminal. Expect `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`. The receipt goes to `~/nissan/work/translation/writes/<UTC>/write-report.json`, next to a rollback snapshot `substance-before-write.bin`. The 2026-10-25 receipt is `20261025T011928Z`.
5. **In the car:** Settings → Clock → offset row to +3 (NZST) or +4 (NZDT). Then run the [#4](https://github.com/prasys/nz-leaf-discovery/issues/4) checks.
6. **Roll back:** run steps 3–4 with `--build` set to the previous build, for example build `6a54198a` `~/nissan/work/translation/build/substance.skn` (`6a54198a…`), or the stock carve `~/nissan/work/translation/substance.skn` (`ea5b5a34…`) to return to the skin as found. Set the row back to 0 first if you want the stored offset cleared, because the skin rollback does not touch the stored hour. A whole-card restore from the 2026-10-24 backup would also undo the G214 probe and the translation; that is a separate owner decision ([#5](https://github.com/prasys/nz-leaf-discovery/issues/5)).

### 0.6 What didn't work, and why the fix moved to the skin

Before the hour row, three lower-level routes were tried, plus one analysed and not built. Details are in [08](08-nz-clock-implementation.md) and §3 here.

| attempt | what was tried and written | what the car showed | likely reason | impact now |
|---|---|---|---|---|
| **NZ-clock payload in G214** (v2) | a 708-byte ARM hook at OBJDLL `getTotalOffset` (`0x40e2c360`) that applies NZ rules. The G214 slot was rebuilt and written at LBA 157696, 30,708,224 bytes, byte-verified (08 §2–§5) | both clocks stayed on JST **[confirmed, owner report]** (08 §7) | the patched module never ran **[likely]**. A NOR/SD header compare in PM13 AppLaunch can fall back to the internal-flash copy (08 §14.2, unobserved). Invalid app UTC is the other open reading (08 §14.3) | superseded by the probe below. Snapshot `nz-clock/writes/20261024T084550Z/G214-before-write.bin` holds stock G214 |
| **Fixed +13 probe in G214** | a minimal diagnostic: `getTotalOffset` returns a fixed +13 h. Written 2026-10-25, 30,700,032 bytes, byte-verified, slot SHA256 `a232889d…` (08 §8.1) | "still no change" **[confirmed, owner report]** | as above. A dormant module is consistent with the hour row now giving correct time without overshoot **[likely]** (§7) | **still on the card, dormant ([#5](https://github.com/prasys/nz-leaf-discovery/issues/5))**. Snapshot `nz-clock/writes/20261025T002153Z/G214-before-write.bin` holds the v2 range. Stock G214 is in the 20261024 snapshot and the full backup; no pinned restore writer yet ([#8](https://github.com/prasys/nz-leaf-discovery/issues/8)) |
| **Slot repacking** (the packaging behind both rows above) | split OBJDLL `.text` into a new o32 section, re-compressed MTCP with liblz4 HC, recomputed every known sum (chunk, MTLD part, SUM4). Two header fields (+0x14, MTLD +0x08) left stock because their algorithm is unknown (08 §3–§4) | as above | either the loader rejects the repacked slot (unknown fields, header gate), or it never loads this copy **[guess]**. Write and read-back succeeded, so the card bytes are right **[confirmed]** | no extra state beyond the G214 rows. G214 +0x14 and MTLD +0x08 stay open ([#11](https://github.com/prasys/nz-leaf-discovery/issues/11)) |
| **Saved zone set to +13** in VSRAM | both nav copies edited to zone +13, type 0, with sums and generations recomputed. Byte-verified before the drive (08 §11) | no change; the post-drive audit found both copies **rewritten to Japan/+9** with newer generations **[confirmed, read-back]** (08 §12–§13) | the unit re-defaults and re-saves the zone (the −7 reset path or a restore from another store) **[likely]** | nothing left behind; the unit overwrote it. Lesson: use the live setter, never raw store bytes |
| **Widen the minute range** to ±180/±240 | analysis only, nothing built or written (§3) | — | the NaviSetCC setter rejects \|m\| > 59 and the getter maps larger stored values to 0, so it needs a G214 patch, and G214 patches don't take effect | none |

**Why this led to the skin fix.** Every firmware-level change was written and verified on the card but never showed in the car, and no run could show whether patched G214 code was executing. The skin, by contrast, visibly loads from the card: earlier skin edits appeared in the car. The firmware already had a ±12 h setter that the skin never called (§1.3). Pointing the skin at it needs no firmware change, uses the unit's own validation and storage, and avoids the unknown header fields. **[confirmed, owner report]** that it works.

**Risk and cleanup.** The dormant +13 probe would add to the hour row if it ever ran (+3/+4 on top of +13 overshoots NZ time), for example after a change in how G214 is loaded. Retiring it is [#5](https://github.com/prasys/nz-leaf-discovery/issues/5). Every write left a receipt and a mode-0444 rollback snapshot under `~/nissan/work/nz-clock/writes/` or `translation/writes/`, and the full backup `20261024T073738Z` predates all of them ([BACKUPS.md](../BACKUPS.md) §5–§6).

## TL;DR

- **The stock firmware already has a working signed-hour path that the skin never calls.** The Clock screen's offset row reads `GetExpOffsetMinSetting` (DISPID 0x6B), writes `SetExpOffsetMinSetting` (0x6C) and limits the value to −59…+59. Across all 10,215 decoded script records, nothing references NaviSetCC 0x69/0x6A (hour) or 0x6D–0x70 (DST, zone). **[confirmed, static]**
- The hour members have the same COM shape as the minute members: PROPERTYGET/PROPERTYPUT with one `LONG`. The row is repointed at the hour setter with **11 same-length byte edits in `substance.skn`**, with no additional firmware change. Minute fine-tuning is lost, and the row label still reads " Minutes". **[confirmed static decode; owner reports working head-unit clock, §7]**
- Widening the minute range to +180/+240 is **not** a skin-only change. NaviSetCC's setter rejects anything outside −59…+59, and its getter maps stored values above 118 to 0. Fixing that needs a G214 (NaviSetCC) patch, and whether patched G214 code runs at all is still unproven (08 §7, §8.1, §14.2). **[confirmed]**
- The traced GPS update writes only GMT and its validity flag, never the user offset. The offset survives a successful restore at power-up. Nothing re-applies the saved hour setting at boot. **[confirmed static]** Reconnect and power-cycle persistence remain untested.
- **Owner observation (2026-10-25):** with the GPS antenna unplugged the hour can be set by hand, and reconnecting it returns the clock to Japanese time. That manual Set Clock is an absolute time seed, and GPS overwrites it. It is a different mechanism from the additive ExpOffsetHour correction (§4.1). The observation does not show what happens to ExpOffsetHour when GPS reconnects. That has to be tested.

## 1. Current minute path: UI → COM → storage → publish

### 1.1 Skin script VM (auirtdll.dll) [confirmed, decompiler]

The skin's screens and logic run as bytecode in G214 `auirtdll.dll`. It was decoded from:

| function | role |
|---|---|
| `FUN_411eab34` | statement interpreter. u16 words on 2-byte boundaries. `w<0x8000` is a block of w bytes. `0x8003` expression, `0x8004/5/6/7` if/else/elseif/end, `0x8008` assignment (target, value), `0x8009` while. Raises "Invalid Script" `0x2034012` (error table at `0x411b2200`). |
| `FUN_411e7340` | length of one expression. A `0x60–0x7f` header carries the length, otherwise the expression is a single token. |
| `FUN_411e6f98` | tokenizer, with big-endian operands. `0x00–0x29` ints, `0x2a` string, `0x2c/2d` false/true, `0x2e`+u32 or `0x80–0xff`+u8 object, **`0x30–0x39` DISPID**, `0x41–0x5b` operators, `0x5d` @arg, **`0x5e flags argc` / `0x5f` = Invoke** (kind 0x106). |
| `FUN_411e8d94` | stack evaluator. A call is `object, DISPID, args…, 0x5e/0x5f`, which becomes `IDispatch::Invoke(dispid, …)`. Assignment targets are evaluated as PROPERTYPUT (mode 4). |

Code records (`0x402`/`0x8402`) start with `[name if flags&1][u32 if flags&2] u32 n, n×u32 sender ids, u32 0, u32 event` (event −1 means none), followed by one statement. `tools/hour-offset-ui/skn_script.py` implements this grammar and decodes **10,215 of 10,215** code records.

Object IDs: the NaviSetCC component is **0x89**, the `0x4205` reference at record 137 that points at the CLSID `{370F6D3F-…}` record 138. The CLSID is in NaviSetCC.dll at file offset 0x41f8. Further down the file the IDs drift away from the record index: +32 around the string tables, +66 on the Clock screen. The general rule is **[open]**. Each mapping used here is anchored by several consistent cross-references, for example the variables `0x111CB…CE` → records 70025–70028, of types `0x2001`/`0x2c2001`.

### 1.2 The Clock settings screen (records 70029–70044, file 0x466C58–0x4673E0) [confirmed, decoded]

```
70029 init:   obj111D0( Navi.#65 )   ; time-indication toggle
              obj111D1( Navi.#67 )   ; 24-hour toggle
              var111CB := Navi.#6B   ; GetExpOffsetMinSetting
              obj111D2( var111CB )   ; refresh offset label
70032 label(v): label111E6.Caption := v + " Minutes"   (constant 0x8943 = table 0x180F30 row 772)
              v <= -59 -> minus disabled ; 59 <= v -> plus disabled ; -58..58 both enabled
70035/70036 plus  (sender 0x111E8, events 3 and 0xA):  var += 1 ; Navi.#6C := var
70037/70038 minus (sender 0x111E7, events 3 and 0xA):  var -= 1 ; Navi.#6C := var
70033/70034 toggles: Navi.#66 / Navi.#68 := 0|1
```

The label is not updated directly by the button handlers. NaviSetCC raises event 0x21 (`NOTIFY_CHG_EXP_OFFSET_MIN_SETTING`), and the sink in record 255 (`senders=[0x89] event=0x21`, file 0x54A0) calls `obj111D2(arg)`. The hour event 0x20 sink in record 256 (0x54D8) only does a generic `Refresh`. **[confirmed]**

Reproduce: `python3 -I tools/hour-offset-ui/skn_script.py --dump 255-256,70029-70044` and `--object 0x89`.

### 1.3 NaviSetCC (DISPIDs → code) [confirmed, typelib + vtable + decompiler]

Dual vtable at `0x42856b58`. Slot `7+i` is typelib member i, and the typelib vtable offsets agree.

| DISPID | member | invkind | function | semantics |
|---|---|---|---|---|
| 0x69 | GetExpOffsetHourSetting | PROPGET | `FUN_4285dfc4` | stored−12; stored outside 0…24 or unset gives 0 |
| 0x6A | SetExpOffsetHourSetting | PROPPUT | `FUN_4286cbec` | accepts −12…+12, `OBJ_Setting_writeExpOffsetHour(h+12)`, then `FUN_4285ea98`; fires event 0x20 with h (or with 0 if rejected) |
| 0x6B | GetExpOffsetMinSetting | PROPGET | `FUN_4285e030` | stored−59; stored outside 0…118 gives 0 |
| 0x6C | SetExpOffsetMinSetting | PROPPUT | `FUN_4286cc58` | accepts −59…+59 (`m+0x3b < 0x77`), writes m+59, then `FUN_4285ea98`; event 0x21 |

`FUN_4285ea98` publishes `(hour−12)·360000 + (min−59)·6000` through `OBJ_Time_writeOffset` (`0x40e2cdf0`, field +0x20). It has only two callers, the two setters. In the 287 G214 modules, NaviSetCC is the only importer by name of `OBJ_Time_writeOffset` and the `ExpOffset*` and `writeDst` accessors.

### 1.4 Storage [confirmed]

- **Correction to 06 §2:** `OBJ_ExpSet_initPrm` (`0x40e485fc`) initialises OffsetHour and OffsetMin to **0x80000000 (unset)**, not 12/59. 12/59 are only NaviSetCC's local fallbacks. `FUN_4285ea98` leaves unset fields out of the sum.
- `OBJ_ExpSet_write` (`0x40e48be8`) stores words [5]/[6]/[7] (hour/min/AutoDst) as full u32 with **no range check**. `OBJ_Time_writeOffset` does not check its range either.
- The Setting class (5) record is saved through `FUN_40e50374` and restored through `FUN_40e50564` (copies ExpSet's 0x20 bytes verbatim). On the card it sits at **LBA 808677 +0x1A0 (copy A) / 809821 +0x1A0 (copy B)**, 1029 sectors into the SRST areas at 807648 and 808792 (labelled "bt" in the manifest). In the original image, the carve and the 2026-10-24 backup, both copies read: hour `0x80000000` (never set), min `0x3B` (= 0, so the minute setter has run at least once), AutoDst 3001 (off). The Time records (nav LBA 807028/807338, +0x144) read +9 h / type 61 / DST 0 / user offset 0. Tool: `tools/hour-offset-ui/expset_scan.py`.

## 2. Hour-control candidates and the smallest change

**Candidates found [confirmed]:** none. No hour row exists, hidden or not. The Clock screen's second control group (`0x111E9…`, records 70057/70058) is the **hidden manual Set Clock tap sequence** (records 70039–70044): tap one zone four times and another twice within a timer (`0x111DA`, `#0x709/#0x70A`), and it raises `SK_SCT_CLOCK_SET_CLICK`. That sequence itself has no GPS condition, so the antenna gate must be somewhere else (ScreenStateCC is **[likely]**). This is the other Claude's area and is not pursued here. The generic Hour/Minutes picker in records 615/616 belongs to the phone block and does not bind NaviSetCC.

**Smallest credible change: skin-only, minute row → hour row.** Every edit is the same length and in place. `tools/hour-offset-ui/hour_row_plan.py` checks the baseline bytes and decodes the edited copy in memory without writing anything. The baseline is identical in the skin as found (`ea5b5a34…`) and in the in-place build `6a54198a…` that was on the card.

| file offset | before → after | record | effect |
|---|---|---|---|
| 0x466C9B | 6B → 69 | 70029 | init reads GetExpOffsetHourSetting |
| 0x467024, 0x46707A | 6C → 6A | 70035/6 | plus writes SetExpOffsetHourSetting |
| 0x4670D0, 0x467126 | 6C → 6A | 70037/8 | minus writes SetExpOffsetHourSetting |
| 0x466E86, 0x466EAA | 3B → 0C | 70032 | limits ±59 → ±12 (tokens `20 3b` → `20 0c`) |
| 0x466ECE, 0x466ED6 | 3A → 0B | 70032 | ±58 → ±11 |
| 0x0054B4 | 21 → 20 | 255 | label-refresh sink listens to the hour event |
| 0x0054EC | 20 → 21 | 256 | generic-refresh sink takes the now-unused minute event |

Before: one press = ±1 min, range ±59, label "N Minutes". After: one press = ±1 h through the stock hour setter, range ±12, the label shows the hour value with the unchanged " Minutes" suffix, and the stored minute still adds (0 in the inspected baseline). +3 = NZST and +4 = NZDT on the JST base; the owner switches by hand twice a year. **[confirmed static; owner reports hours change and correct head-unit time, §7]** The full button range and event binding were not independently captured in the car.

The suffix stays for now. Constant 0x8943 → table 0x180F30 row 772 is also used by two other label controls (file 0x34B5DD and 0x405DD9), so changing that string would change other screens. Pointing record 70032 at an existing " Hours" constant needs the ID→record rule (open).

Why not add a second row so both minutes and hours remain: that means new control and handler records plus layout, so the file has to be repacked and the ID allocation understood. That is a real VM project and not bounded.

## 3. Expanded minute range (+180/+240)

| layer | limit | change needed |
|---|---|---|
| skin record 70032 | ±59 button enable | same-length tokens (11-bit ints reach 1023) |
| NaviSetCC setter `FUN_4286cc58` | `m+59 < 119` | **firmware**: widen the compare |
| NaviSetCC getter `FUN_4285e030` | stored > 118 → returns 0 | **firmware**: otherwise the row shows 0 and the next press resets the real offset |
| `FUN_4285ea98`, OBJDLL ExpSet/Time | none | — |

So this needs both a skin edit and a G214 NaviSetCC patch. It inherits the unresolved question of whether patched G214 code runs (08 §14.2), and it takes 180–240 presses (or holding the repeat) every season. **Not recommended** while a skin-only hour row exists. **[confirmed for the limits; feasibility gated on the loader question]**

## 4. Persistence, GPS and the dash

- **GPS:** Navi.exe `FUN_003e86b8` → `OBJ_Time_writeGMT` writes only bytes 0x00–0x0B. The offset at +0x20 is kept. Both go through the same versioned shared-object writer `FUN_40e21cfc`. **[confirmed static, 07/08]**
- **Power cycle:** `OBJ_Time_initialize` (`0x40e2d3d4`) keeps the whole 0x5C8-byte record, offset included, after a successful restore. The −7 path runs `OBJ_Time_initPrm` (offset 0) plus the Japan default. The Setting record is restored separately (`OBJ_Setting_initialize` `0x40e52fd8`, version tag 6). **Nothing re-applies ExpOffsetHour to the Time record at boot.** If only the Time record resets, the UI shows +3 while the clock runs JST, and pressing −/+ re-applies it. **[confirmed static]** The 08 §13 replacement of a raw-edited zone is a reason to use the live setter and never edit raw store bytes.
- **Dash and timers:** Vehicle.exe and NaviGeneralCC read `OBJ_Time_readLocalTime`, which includes the offset **[confirmed static, 07/08]**. What triggers a VCM clock push after an offset change is **[open]**. The skin has an existing timer-unit clock repair action (`POP_EV_INF_TUNITERROR_CLOCK_*`, `…TIME_REPAIR_CLICK`) worth using in a test.

### 4.1 Manual Set Clock vs ExpOffsetHour (owner observation, 2026-10-25)

**[confirmed, owner report; no independent capture]** With the physical GPS antenna cable disconnected, the clock hours can be set by hand. As soon as the cable is plugged back in, the clock returns to Japanese time.

- This manual Set Clock (`SLF_CLOCK_SET`, reached by the tap sequence in §2) is an **absolute seed**: it sets the clock value. ExpOffsetHour is an **additive correction** applied in `getTotalOffset`. They are separate.
- The revert matches GPS GMT replacing the manual value. The GMT writer leaves +0x20 alone **[confirmed static]**, so the observation **does not show** that the hour setter's value would be overwritten. It also doesn't identify the module that's running or the exact writer. **[likely interpretation]**
- So an ExpOffsetHour of +3/+4 is expected to survive GPS reconnection **[likely, static]**. This must be **validated in the car** (§5).

## 5. Original implementation plan and remaining owner checks

1. **Normalise the baseline first.** The fixed +13 G214 probe is still on the card (08 §8.1) and its execution is unproven. Running both would double-adjust if the probe ever does run. The owner decides whether to restore stock G214 from the verified rollback before testing. Either way, record the clock before any change.
2. Build the 11-byte skin edit from the live build `6a54198a…` with the in-place pipeline, after a reviewed `hour_row_plan.py` run. Then write it with the pinned preflight/`--apply` writer pattern (`write_skin.py`, the owner runs `--apply`). Subsequently completed; receipt in §7.
3. In the car, with the antenna **connected** and a 3D fix: Clock screen → +3 (winter) or +4 (summer). Expect the head-unit clock to move by exactly that many hours. The owner reports the hours change and correct time (§7), but did not record the exact value or GPS state. This supports the traced offset path; it does not fingerprint the running DLL or storage source.
4. Persistence: unplug and replug the antenna (the owner already does this for the manual menu), drive or wait for GPS updates, power-cycle twice. Check the head unit, the dash, and the charge/climate timers (timer-unit repair prompt).
5. Read back with `expset_scan.py` on a fresh read-only image or audit: ExpSet hour word 15/16 in both copies, Time user offset 1,080,000/1,440,000.

## 6. Unknowns

- The object-ID → record rule (offset +0/+32/+66) **[open]**. It's needed for a correct " Hours" label.
- Whether sink headers bind `(sender, event)` exactly as inferred **[likely]**.
- What triggers the VCM/dash clock update after an offset change **[open]**. The behaviour across the −7 reset path and through retained DRAM **[open]**.
- Whether a minute-row PROPERTYPUT reaches NaviSetCC on this unit: stored min 59 says the minute setter ran at least once **[likely, from the skin]**.

## Tools (stdlib, `python3 -I`)

| tool | what |
|---|---|
| `tools/hour-offset-ui/skn_script.py` | skin bytecode decoder: `--object/--dispid` member references, `--dump` records |
| `tools/hour-offset-ui/hour_row_plan.py [skin]` | checks the 11 baseline bytes and decodes the edited copy in memory; writes nothing |
| `tools/hour-offset-ui/expset_scan.py [image/carve]` | prints only the ExpSet hour/min/DST words and the Time zone/DST/offset |
| `tools/hour-offset-ui/test_hour_offset_ui.py` | 14 tests: synthetic grammar, plus real-skin/hour-row/DST-toggle checks when the carve is present |
| `tools/hour-offset-ui/build_hour_row.py` | pinned input, baseline/decode checks; creates a new output directory under `NISSAN_ROOT/work`, with a mode-0444 skin and JSON report; never accesses a card |
| `tools/hour-offset-ui/test_build_hour_row.py` | 4 tests for output boundaries, symlink escape refusal and source preservation |

## 7. Build v1 and card write (owner runs `--apply`)

The owner chose to patch the skin first and leave the G214 probe as it is (§5 step 1 skipped). Built from the live build `6a54198a` skin:

```sh
python3 -I tools/hour-offset-ui/build_hour_row.py \
  --skin ~/nissan/work/translation/build/substance.skn --out ~/nissan/work/hour-offset-ui/build-v1
```

Source `6a54198a…`. Build `ec1138c812d5bc111ad30d2e8937b0657be1f8092f832cefb67a83916bfa192b`, 20,025,376 bytes (mode 0444). `cmp` shows exactly the 11 bytes in §2. The build is pinned in `tools/translation/write_skin.py` `BUILDS`. `write_skin.check_build` passes, and `test_write_skin.py` passes 17/17. Card in the Mac, whole-disk id rediscovered:

```sh
# read-only preflight (must print READ_ONLY_PREFLIGHT_PASSED, live = build `6a54198a`)
sudo python3 -I tools/translation/write_skin.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/hour-offset-ui/build-v1/substance.skn --work-root ~/nissan/work
# apply: the same command plus --apply
# rollback to build `6a54198a`: --build ~/nissan/work/translation/build/substance.skn (live must be this build)
```

Car check: Settings → Clock → offset row +3 (NZST) / +4 (NZDT). Then the antenna reconnect and power cycles from §5 steps 3–5. If a fixed +13 base and an additional +3/+4 correction were both active, the clock would overshoot NZ time. Recording the exact selected value would help assess that hypothesis; it would not establish a loaded-module fingerprint.

**Written 2026-10-25 [confirmed, receipt].** The preflight passed (`READ_ONLY_PREFLIGHT_PASSED`, live = build `6a54198a`). The owner unmounted disk9 (Built In SDXC Reader, 16,206,790,656 bytes) and pressed Enter on `--apply` in Terminal 2. Result: `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`, 20,025,856 bytes at LBA 29925953, fsync completed, followed by a full read-back comparison. Receipt: `work/translation/writes/20261025T011928Z/write-report.json`. The rollback snapshot `substance-before-write.bin` has SHA256 `0ea38a25…` and equals the build `6a54198a` span written earlier. This receipt predates the subsequent car result below.

**Car result 2026-10-25 [confirmed, owner report; no independent capture]:** "its working, the hours are updated and now its correct". The Clock screen row now changes hours, and the head-unit clock shows correct NZ time. Implications:
- The stock NaviSetCC hour setter → `FUN_4285ea98` → `OBJ_Time_writeOffset` → `getTotalOffset` path is live in the displayed clock **[likely, strong]**.
- An inactive fixed +13 G214 probe (08 §8.1) remains **[likely]**: a +13 base plus a +3/+4 correction would overshoot NZ time. However, the exact selected value was not reported, so this result alone does not resolve the loaded-image question in 08 §14.3.
- Not yet reported: the dash clock, charge/climate timers, persistence through antenna reconnection and power cycles (§5 steps 4–5), the exact value selected, and a read-back.

## 8. Summer Time menu and experimental manual DST toggle (v2)

**[confirmed, static build only; untested in the car]** This candidate is separate
from the owner-tested v1 hour row. It exposes a manual +1 h switch; it does not
calculate NZ DST transition dates. No deployment of this candidate is recorded.

**The hidden Summer Time menu is not worth unhiding [likely, strong].**

- The settings dispatcher (record 47522) routes `SET_CLOCK_TIMEZONE_SETTING_MENU` to page 7 and `SET_CLOCK_SUMMERTIME_SETTING_MENU` to page 8 (the same page index as `SET_LANGUAGE_SELECT_UNIT_MENU`).
- The page table it indexes (object 0x110EA → record 69800, type 0x8802; columns DialogTransparent, SurfaceTrans, FadeEffect, Action, ActiveForm, ID) has only rows 0–5. The skin has no form for either screen.
- In the stock/v1 skin, NaviSetCC sinks for AutoDst (0x22, record 257) and zone (0x23, record 258) are empty, and the skin calls none of 0x6D–0x70.
- The traced native setter applies no date rule **[confirmed]**. `FUN_4286ccc4` writes AutoDst 1 (on) or 2 (off) and `OBJ_Time_writeDst(360000 | 0)`. `OBJ_Time_writeDst` accepts only those two values. `OBJ_Time_getTotalOffset` is zone + DST + user offset.
- So the menu would only ever be a manual +1 h switch.

**v2: repurpose the Clock screen's first toggle next to the hour row.** It currently controls time indication (`0x65`/`0x66`, 0/1, event 0x1E; the header clock reads it in records 279/280/37011). `Get/SetExpAutoDstSetting` has the same 0/1 shape; the setter `FUN_4286ccc4` notifies event 0x22 through `FUN_42864e54`. Five same-length bytes, applied on top of v1 (`hour_row_plan.py --change dst`):

| file offset | before → after | record | effect |
|---|---|---|---|
| 0x466C79 | 65 → 6D | 70029 | toggle state from GetExpAutoDstSetting |
| 0x466F50, 0x466F60 | 66 → 6E | 70033 | toggle writes SetExpAutoDstSetting(0/1) |
| 0x005444 | 1E → 22 | 253 | toggle display follows the AutoDst event |
| 0x005518 | 22 → 1E | 257 | the empty sink takes the unused event |

Proposed use on a JST base: leave the hour row at **+3** all year and turn the toggle on in summer (+3 + 1 = +4 = NZDT). This remains unverified. Side effects:

- The time-indication setting can no longer be changed, so the header clock stays as it is now.
- The toggle keeps its old label.
- Saved AutoDst in the inspected baseline is 3001, which reads as off.

Build `f255f869…` (`work/hour-offset-ui/build-v2-dst/`, from v1 `ec1138c8`). `cmp` against v1 shows exactly the 5 bytes. It is pinned in `write_skin.py`. Tests: 14 hour-offset tests and 17 writer tests pass. Untested in the car.

The auto-DST groundwork for [#2](https://github.com/prasys/nz-leaf-discovery/issues/2): NaviGeneralCC (object 0x8F) exposes `getHeadertime{Hour,Minutes,AMPM,DayofWeek,Year,Month,Day}` (DISPIDs 2/3/6/7/0xC/0xD/0xE). Its hour- and minute-tick events have always-on sinks (records 279/280). A script added there could set the toggle by the NZ rule, but that would grow a record and need `--repack`.

## 9. Follow-up work

- [#2: Automatic NZ DST](https://github.com/prasys/nz-leaf-discovery/issues/2): calculate seasonal changes and apply the working offset path without double adjustment. The stock AutoDst toggle only adds a fixed hour.
- [#3: Correct the label](https://github.com/prasys/nz-leaf-discovery/issues/3): replace this row's “Minutes” suffix without altering other minute labels.
- [#4: Car validation](https://github.com/prasys/nz-leaf-discovery/issues/4): dash, charge/climate timers, GPS reconnect, power cycles and overnight persistence.
- [#5: Retire the dormant fixed +13 probe](https://github.com/prasys/nz-leaf-discovery/issues/5): optional owner-run normalization with byte-verified rollback; avoid a future double correction.

Issue [#1](https://github.com/prasys/nz-leaf-discovery/issues/1) remains the umbrella for the clock work. The manual head-unit workaround is demonstrated by owner report; automatic DST and end-to-end vehicle validation are incomplete.
