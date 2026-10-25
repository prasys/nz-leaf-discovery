# NZ clock design review (refs [#22](https://github.com/prasys/nz-leaf-discovery/issues/22), [#19](https://github.com/prasys/nz-leaf-discovery/issues/19), [#21](https://github.com/prasys/nz-leaf-discovery/issues/21))

Review date: 2026-10-24. Scope: inspect Claude's findings and extracted modules,
identify the app-side Japan default, and assess using CE's NZ timezone/DST logic.
This is a design and static analysis result, not a tested firmware patch.
**Implementation update (2026-10-25):** [12](12-hour-offset-ui.md) records the
working manual hour-row skin patch [confirmed, owner report]. Automatic NZ DST
remains open in [#2](https://github.com/prasys/nz-leaf-discovery/issues/2).
[08](08-nz-clock-implementation.md) preserves the earlier app-side firmware
candidates and unsuccessful car tests; their execution remains unproven.
The CE bridge below remains a design proposal.
Original image and extracted modules were read-only. No car/card writes or
execution of extracted code occurred. No tools were installed.

## 1. Two independent Japan defaults

| Layer | Evidence | Result |
|---|---|---|
| CE | PM13 navdrv `FUN_eedf60e8`, documented in issue [#22](https://github.com/prasys/nz-leaf-discovery/issues/22); model area `0x10`, `Bias=-540`, Tokyo names, zero transition dates | Forces CE to UTC+9 **[confirmed, prior decompiler trace]** |
| App default | G214 OBJDLL `FUN_40e2c4d4`, called from `OBJ_Time_initialize` at `0x40e2d3d4` | Area `0x10` selects zone type `0x3d` and zone `0x317040` = 3,240,000 hundredths = +9 h **[confirmed, read in decompiler]** |
| GPS update | Navi.exe `FUN_003e86b8` | Constructs date/time from receiver data and writes GMT through `OBJ_Time_writeGMT`; no zone/DST/offset setter in this function **[confirmed, read in decompiler]** |
| Local conversion | OBJDLL `OBJ_Time_getLocalTime` `0x40e2c3b8`, `OBJ_Time_getTotalOffset` `0x40e2c360` | Adds zone + DST + user offset to GMT via `STD_Time_addBase` **[confirmed, read in decompiler]** |

The receiver input structure's complete semantics have not been recovered.
Other initialization/restore paths may alter the zone **[open]**.

The app Japan default does not come from the CE timezone. This corrects the
early explanation in [02](02-unit-and-clock.md): changing navdrv's bias alone
does not change the app's local-time expression **[confirmed]**.

The default initializer's +9 literal is shared with area `0x55` (zone type
`0x3e`), and `OBJ_Time_initialize` also has restore paths before its default
fallback. A literal replacement alone is not a proven persistent fix
**[confirmed code; likely persistence limitation]**.

## 2. Shared clock fields and the existing hour adjustment

| Field | Struct offset | Evidence |
|---|---|---|
| GMT + validity | `0x00..0x0b` | `OBJ_Time_writeGMT` `0x40e2c8c4` writes 12 bytes through `FUN_40e21cfc` |
| zone | `0x14` | `OBJ_Time_writeZone` `0x40e2cb60` |
| zone type | `0x18` | `OBJ_Time_writeZoneType` `0x40e2cc38` |
| DST | `0x1c` | `OBJ_Time_writeDst` `0x40e2cd30`; accepts 0 or 360000 |
| user offset | `0x20` | `OBJ_Time_writeOffset` `0x40e2cdf0` |

All entries **[confirmed, read in decompiler]**. The original [06](06-hmi-clock-and-hooks.md)
diagram reversed the last two labels; this review corrects it explicitly.
Partial GMT writes do not themselves overwrite these later fields.

NaviSetCC `FUN_4285ea98` computes `(ExpOffsetHour-12)*360000 +
(ExpOffsetMin-59)*6000`, omitting fields with the unset sentinel `0x80000000`
(later storage trace: [12 §1.4](12-hour-offset-ui.md#14-storage-confirmed)).
Its hour setter `FUN_4286cbec` accepts -12..+12 and stores
`h+12` **[confirmed, Claude's exported decompiler output reviewed]**. Thus stored
hour 15 is +3 h and 16 is +4 h. This is a feasible seasonal workaround on top of
the +9 zone, but a fixed value does not implement automatic NZ DST **[likely]**.

## 3. Reusing Windows CE for NZ time

**[confirmed, hive data]** PM13's `HKLM\Time Zones\New Zealand Standard Time\TZI`
contains:

```
30 fd ff ff 00 00 00 00 c4 ff ff ff
00 00 04 00 00 00 01 00 03 00 00 00 00 00 00 00
00 00 09 00 00 00 05 00 02 00 00 00 00 00 00 00
```

This is Bias -720, StandardBias 0, DaylightBias -60; first Sunday April 03:00
and last Sunday September 02:00. The zone ID is 2410 (0x96a). See [05 §4](05-ce-rom-extract.md).
The rule matches the [NZ Government's current DST description](https://www.govt.nz/browse/recreation-and-the-environment/daylight-saving/).

**[confirmed, PE export table]** PM13 coredll provides:

| API | Ordinal | RVA |
|---|---|---|
| SystemTimeToFileTime / FileTimeToSystemTime | 19 / 20 | `0x21128` / `0x2114c` |
| FileTimeToLocalFileTime | 21 | `0x21044` |
| GetLocalTime / GetSystemTime | 23 / 25 | `0x212dc` / `0x21170` |
| GetTimeZoneInformation / SetTimeZoneInformation | 27 / 28 | `0x21634` / `0x21920` |
| SetTimeZoneInformationByID | 2902 | `0x21dbc` |

`SystemTimeToTzSpecificLocalTime` is absent from this export list. Desktop Windows
examples using that API cannot be assumed to work here. Export presence does not
establish the calling convention/arguments of `SetTimeZoneInformationByID` or
prove that the installed DST service runs correctly **[open]**.

**[guess, proposed implementation]** For a consistent CE/app clock:

1. Change the active navdrv's Japan initialization to install the full NZ TZI
   instead of its Tokyo structure. Preserve GPS UTC as the system time.
2. Bridge CE's current NZ bias/DST state into the shared app clock. For example,
   with a verified `GetTimeZoneInformation` result, standard offset is
   `-(Bias+StandardBias)*6000` and additional daylight offset is
   `(StandardBias-DaylightBias)*6000` only in daylight mode. Validate the active
   zone and API return value before publishing it.
3. Use the app's existing notification/write path so its consumers see changes.
   Set the NZ base zone to 4,320,000 and DST to 0/360,000. Keep the user's minute
   adjustment separate; remove any earlier +3/+4 h workaround to avoid adding it
   twice. Ensure NaviSetCC's fixed DST toggle cannot overwrite the managed value.
4. Reconcile at startup, first valid GPS date, resume, and timezone/DST changes.
   Confirm which notifications are available on this CE build. A startup-only
   adjustment would miss a DST change while the unit remains running.

The exact app hook and CE service behaviour remain to be verified. Keep this
conversion in the shared clock path: converting GPS GMT to NZ local *before*
`OBJ_Time_writeGMT` would cause downstream consumers to apply the zone again.
Do not infer a complete patch from changing one default constant.

An alternative is to compute NZ rules directly in the app from its GMT date,
leaving CE's Tokyo clock separate. That avoids reliance on CE DST service state,
but duplicates the rules. The host model below defines the expected behaviour
for either implementation **[guess, design alternative]**.

## 4. Dash and timers: what is actually verified

**[confirmed, read in decompiler]** Vehicle.exe calls `OBJ_Time_readLocalTime`
from `FUN_00033098`, `FUN_00048558`, `FUN_00047e60` and `FUN_00059f00`. The first
packs date, hour, minute, second and weekday into an output structure.
EvTimerCC.dll itself has no matching import in the inspected image; its UI goes
through VehicleCCWrapper. The earlier shorthand “EvTimer reads local time”
should be understood as a vehicle/timer subsystem claim, not a direct DLL import.

**[likely]** Updating the shared clock reaches vehicle-related consumers. Existing
VCM clock-request strings are documented in [02 §4.3](02-unit-and-clock.md).
**[open]** The final CAN producer, instrument-cluster clock consumer, timer
acknowledgements and behaviour at DST transitions have not been verified. A
correct nav display alone does not prove that the dash/timers follow it.

## 5. Reproduction and expected behaviour

`tools/clock-analysis/ClockTrace.java` exports matching functions and their direct
callers from Ghidra without modifying the program. It also follows import thunks.
Use `-readOnly -noanalysis` with an existing project, e.g.:

```sh
<ghidra>/support/analyzeHeadless ~/nissan/work/ghidra objdll_g214 \
  -process OBJDLL.dll -readOnly -noanalysis \
  -scriptPath "$PWD/tools/clock-analysis" \
  -postScript ClockTrace.java '^FUN_40e2c4d4$'
```

Review exports are under `~/nissan/work/clock-analysis/`: `obj-default.log`,
`obj-time.log`, `navi.log` and `vehicle.log`. New Ghidra projects are under
`~/nissan/work/ghidra/clock_review_*`. Navi analysis reached its 180-second cap
with analysis incomplete; targeted exports completed. Decompiled
prototypes have inferred types, so confirm any patch site and ABI in assembly.

```sh
python3 -I tools/clock-analysis/nz_time_model.py --verify
python3 -I tools/clock-analysis/nz_time_model.py 2026-10-24T00:00:00Z
```

**[confirmed, host test]** 11,138 UTC instants across 2008–2037 (daily samples plus
seconds around every transition) matched the host's independent
`Pacific/Auckland` tzdata. This validates the reference arithmetic, not CE code
or a modified image. The rule is extrapolated; future law changes require review.

| UTC input | Expected NZ local time |
|---|---|
| 2026-04-04 13:59:59Z | 2026-04-05 02:59:59 +13 |
| 2026-04-04 14:00:00Z | 2026-04-05 02:00:00 +12 |
| 2026-09-26 13:59:59Z | 2026-09-27 01:59:59 +12 |
| 2026-09-26 14:00:00Z | 2026-09-27 03:00:00 +13 |

Before a human tests a candidate on a spare cloned card, resolve the active OS
image (PM13 versus UP14), settings restore/override paths, and reconstruction of
the actual ROM sections. The analysis PE files are not flash-ready images.
Known additive checksums in [06 §6](06-hmi-clock-and-hooks.md) do not establish
bootloader acceptance. At this review's original checkpoint no modified image
had been produced; see [08](08-nz-clock-implementation.md) for the later offline
candidate and its outstanding packaging/hardware checks.
