# NZ clock implementation and deployment plan (#29)

2026-10-24. Follows [07](07-nz-clock-design.md). Claude Sonnet 5.5 implemented
the freestanding C calculation and host tests; Codex reviewed it, implemented
the ARM wrapper/ROM builder, and independently reran the checks. The Orca launch
receipt confirms effective model `claude-sonnet-5-5`.

**Current result (2026-10-25):** [12](12-hour-offset-ui.md) records the later
11-byte skin patch that calls the stock hour setter. The owner reports correct
head-unit time **[confirmed, owner report; no independent capture]**. This is a
manual seasonal workaround; automatic DST and dash/timer/persistence checks
remain open. The firmware candidates below are historical experiments whose
execution was not established; they are not the demonstrated correction.

## 1. Plan and current status

| Stage | Status | Evidence / remaining work |
|---|---|---|
| NZ arithmetic | Done, host tested **[confirmed]** | `clock.c`: 9 tests covering daily 2008–2099, transition seconds, invalid inputs, overflow and offsets against `Pacific/Auckland` |
| ARM integration | Offline candidate built **[confirmed, static]** | 708-byte payload; entry `0x40e2c360` branches to `0x40e9e1c4` |
| ROM reconstruction | Re-extracted **[confirmed]** | `ceromx.py --only OBJDLL.dll`: 287 modules / 43 files in inventory, 0 extraction errors; 6 integration tests pass |
| Slot packaging | Experimental v2 built **[confirmed]** | All known sums and complete decompression round trip pass; 30,708,224 bytes fits 30,801,920-byte allocation. Unknown fields +0x14/+0x78 remain stock; boot acceptance unverified |
| Card backup | Verified **[confirmed]** | 16,206,790,656 bytes, saved SHA256 `redacted`; owner Terminal 6 completed the read-only copy and read-back verification |
| Production-card write | Written and byte-verified **[confirmed]** | G214 at LBA 157696; 30,708,224 bytes written, fsync completed, reopened full-range comparison passed; head-unit boot tested with no clock change (§7) |
| First clock test | No correction observed **[confirmed, owner report]** | Both head-unit and dash clocks stayed on Japanese time; execution of the hook is unproven. See §7 |
| Fixed saved zone | Pre-test +13 byte-verified; display unchanged **[confirmed, audit / owner report]** | Post-test audit confirms both copies reverted to Japan/+9, type 61, generations 73724/73725, valid sums (§13); see §§11–13 |
| Fixed +13 probe | Installed, byte-verified; owner reports no change **[confirmed receipt / owner report]** | §8.1; no post-car read-back |
| Manual clock menu (antenna unplugged) | Static trace **[see §15]** | Owner lead; §15 |
| VCM timers | Hardware unverified | Vehicle local-time readers are identified in [07]; final propagation remains open |
| Windows CE timezone | Later step | This candidate computes NZ rules directly in the app; CE retains Tokyo |
| Reset-path / active-image analysis | Done, static; runtime unobserved **[confirmed / likely]** | Successful record restore preserves the zone; the -7 failure path itself defaults and persists Japan; the installed read-side hook tolerates +9 resets, so a store reset alone does not explain the failed display; conditional AppLaunch NOR/SD header-gate lead. See §14 |

**[likely, owner-reported, not independently tested]** On 2026-10-24 the owner
reported that audio still works when the SD fails, with maps unavailable. This
records the stated failure behaviour; it does not establish that arbitrary
firmware damage has the same outcome or prove recovery.

## 2. Behaviour and ABI

**[confirmed, source/disassembly]** The wrapper calls the stock
`OBJ_Time_getTotalOffset` first, preserves errors, calls `nz_apply` on success,
then returns stock success 0 (the helper's internal “applied” result is 1).

The helper applies only to zone type `0x3d`, zone +9 h (`3240000`), validity 1,
and valid UTC dates in 2008–2099. It returns NZST/NZDT plus the existing signed
user offset, ignoring old fixed DST to avoid double application. Unsupported,
invalid, non-JP and overflowing cases retain the stock result. Only the output
scalar changes; settings and GMT remain intact. A previous +3/+4 h user-offset
workaround would need removal.

The wrapper preserves r4–r8 and LR. Its trampoline reproduces original bytes
`30 40 2d e9 01 40 a0 e1`, then branches to `0x40e2c368`. The original zone
validator/import call remains untouched. It aligns SP to eight bytes before
calling AAPCS C and restores SP afterwards: stock CE caller `0x40e2c3b8` has a
four-byte local. The linked ELF has no relocations, writable data, runtime
library dependencies or new CE imports **[confirmed, static inspection]**.

**[confirmed, read in decompiler]** Event evaluator `FUN_40e2c068` compares
`OBJ_Time_getTotalOffset` for offset conditions (param_2 == 2), and
`OBJ_Time_getLocalTime` for local conditions. These calculations therefore use
the hook too; actual consumer registrations/behaviour remain unverified.
Trace: `~/nissan/work/clock-analysis/clock-events.log`.

Host tests execute only newly written C. No extracted code was executed.
ARM execution and the actual CE ABI have not been tested.

## 3. Physical layout and correction to the cave assumption

**[confirmed, parser/listing]** OBJDLL o32 .text is at unpacked ROM `0x1411a08`:
vsize `0x9d1c3`, RVA `0x1000`, psize `0x9e000`, data VA `0x89067000`, runtime
VA `0x40e01000`, flags `0x68000020`. Its physical bytes start at `0x827000`.

**Correction:** original psize-vsize bytes are not empty padding. At ROM
`0x8c41c4` they begin `04 00 22 21 d0 26 01 00 00 00 ca 42 07 00 00 00 ...`,
including other module metadata. The initial builder refused to overwrite it.

Revision 1 appended the whole declared .text. It built/re-extracted but its
packed result exceeded the existing slot; the size guard refused it. That
candidate is retained for audit only and is superseded by v2.

**[confirmed, v2 report/tests]** Revision 2 splits off only the final virtual
page. The first .text section retains `0x9d000` bytes at its existing physical
location. A new o32 section maps a physical page at ROM `0x2893000` to the
unchanged runtime VA `0x40e9e000`; it contains the last original `0x1c3` bytes
and the payload at physical `0x28931c4`. A copied, five-entry o32 table is at
`0x2894000`. The entry branch stays at original ROM offset `0x852360`.

The builder updates the entry branch, e32 section count, TOC o32 pointer and
ROMHDR physlast: ten existing bytes change across four approved ranges. The
old o32 table and other module metadata remain intact. ROM size grows only
42,541,568 → 42,549,760 bytes (8 KiB); total virtual .text content is `0x9d488`
within the original virtual page capacity. Loader acceptance of the section
split remains untested. The reconstructed PE is an analysis artifact.

## 4. Toolchain and packaging gate

The successful build uses Apple Clang 17, target `armv7-none-eabi`, Cortex-A9,
ARM mode, soft float and freestanding C. No CE SDK/import libraries are needed
for this payload. Installed via `brew install lld`: LLD 23.1.4, with Homebrew
dependencies LLVM 23.1.4 and Z3 5.3.1 **[confirmed, build/install output]**.

G214 starts at card LBA 157696 (`0x4d00000`), payload one sector later. It is
MTLD/MTCP packed data, not this unpacked `.nb0` **[confirmed, [06](06-hmi-clock-and-hooks.md)]**.
Known MTCP chunk, MTLD part and outer SUM4 sums must be recomputed after packing.
`slot_audit.py` disproves the earlier whole-unpacked-image sum hypothesis:

| Field / hypothesis | Stored | Packed calculation | Unpacked calculation |
|---|---|---|---|
| slot +0x14 / sum8 | `0x6d06` | `0x3241` | `0xe4b1` |
| MTLD +0x08 (slot +0x78) / sum32 | `0x2806d839` | `0x1e072fbc` | `0xe675b639` |

Mismatches are **[confirmed]** in `~/nissan/work/nz-clock/slot-audit.json`.
The fields' meaning/enforcement remain **[open]**. The experimental packed v2
retains both exact stock values instead of assigning guessed replacements.
`pack_slot.py` verified an untouched source decode and complete candidate decode,
all 11 chunk sums, both MTLD part sums and outer SUM4. It uses the existing
liblz4 HC compressor. A successful write/read-back will not prove boot acceptance.

The optional later CE bridge requires identifying the active OS, installing NZ
TZI, checking DST service/notifications and preventing Tokyo restoration. It is
not included in this candidate.

## 5. Backup and deployment

The owner's later explicit instruction authorizes a production-card experiment
after backup, superseding the earlier spare-card preference for this experiment.
The saved original image remains read-only.

`backup_card.py` identifies a whole removable physical 16 GB card, requires
unmounted partitions, opens its raw device only in `rb` mode, writes a new
backup under `$NISSAN_ROOT/work/nz-clock/backups/`, and verifies saved SHA256 by
reading it back. Disk9 was unmounted before the owner started the backup with
administrator access. Recheck device identity before any future write: disk
numbers are transient.

Verified backup: `work/nz-clock/backups/20261024T073738Z/card-before-patch.img`,
now mode 0444. The full-card hash differs from the older original image, but the
G214 payload and header match the reviewed source exactly: payload SHA256
`3c90f444fc2a5ab5490ec07d4c8d011763d1bf7f6d2265bc80cfb6e20e41200b`, header
SHA256 `c74f77bccca7c601069cb16de877990931065c51bb5d0f8cda9a5c56bac22001`
**[confirmed, `physical-slot-audit.json`]**. No claim is made about the reason for
changes elsewhere on the card; no personal-data contents were inspected.

The owner requested this production-card experiment despite possible loss of
SD-based functions. The experimental write uses the verified backup and the
packed v2 above, with unresolved fields unchanged. This is a change from the
earlier plan to resolve both fields before any card test; it is not a claim
that their algorithms/enforcement have been solved.

`write_card.py` defaults to read-only preflight. Its `--apply` path pins the
backup/candidate hashes, requires an exact live baseline and unmounted identified
physical card, saves/flushes the original slot range, writes only the G214 range,
closes/reopens and reads back all old slot bytes (including untouched trailing
bytes). An I/O/read-back failure triggers verified rollback when possible. A
pre-write refusal never invokes rollback. Seven fault-injection tests exercise
these paths on ordinary temporary files, never devices. Production execution
completed successfully after the owner supplied administrator access in Terminal 6.

**[confirmed, write receipt and rollback SHA256]** Receipt
`work/nz-clock/writes/20261024T084550Z/write-report.json` records
`WRITTEN_AND_BYTE_VERIFIED_HARDWARE_BOOT_UNTESTED`: 30,708,224 bytes written at
byte offset 80,740,352 (LBA 157696), candidate SHA256
`b32441b1f42707348bfac2b273fcd983ff54488bf77e3886ac100bf25a07db70`,
fsync completed, followed by successful reopened-device comparison of the entire
30,737,920-byte old slot range, including the untouched trailing bytes. The
read-only rollback snapshot `writes/20261024T084550Z/G214-before-write.bin`
has SHA256 `8c9edf0086e71f94cabcd23b360e73c91bd0d950b8b84e5ae4822dc0e3aa98e3`.
The physical card was then safely ejected (`diskutil eject disk9`: success).
This receipt precedes the first owner test in §7; the two unresolved header
fields remain stock.

Hardware checks: nav and dash date/time before/after GPS fix and power cycles,
minute adjustment, VCM clock acknowledgement and charge/climate timer behaviour.
A correct nav display alone does not prove the dash/VCM clock is corrected.

## 6. Reproduce the offline candidate

```sh
python3 -I tools/nz-clock/test_clock.py
python3 -I tools/nz-clock/build.py --out "$HOME/nissan/work/nz-clock/candidate-v2"
python3 -I tools/nz-clock/test_build.py
python3 -I tools/ce-extract/ceromx.py \
  "$HOME/nissan/work/nz-clock/candidate-v2/G214-NZ-candidate.nb0" \
  "$HOME/nissan/work/nz-clock/candidate-v2/extracted" --only OBJDLL.dll
python3 -I tools/nz-clock/test_pack.py
python3 -I tools/nz-clock/test_writer.py
python3 -I tools/nz-clock/pack_slot.py --out "$HOME/nissan/work/nz-clock/packed-v2-reviewed"
```

Build output directory must be new; another build needs a fresh name. Wrong
input SHA256 is rejected. Hashes are in `binaries/MANIFEST.md`; compiler commands,
source hashes and changed ranges are in `candidate-v2/patch-report.json`.
All binaries and backup contents remain outside Git.

## 7. First owner test: both clocks unchanged

**[confirmed, owner report; no independent runtime capture]** After the patched
card was returned to the car, the owner reported the dash still showing about
5:59 pm, described as Japanese time, then confirmed the head-unit clock also
stayed on Japanese time. The owner states the head unit supplies the dash clock,
keeping them in sync. This is a failed clock-correction observation, not evidence
that the modified G214 image or ARM hook was loaded. The owner subsequently
confirmed loading from the SD card, an English UI, and an on/off reboot. Treat
the reboot as reported test evidence; do not assume the owner merely resumed
without restarting. English UI/card access does not identify the executed bytes
at OBJDLL `0x40e2c360`. Valid GPS reception has not been independently captured.
Timer behaviour was not reported. The card write/read-back evidence in §5 still
stands.

**2026-10-25 owner observation [confirmed, owner report]:** with the SD card
removed, the unit shows no time even with GPS connected. This supports a
dependency on SD-loaded navigation software for producing or publishing the
displayed clock **[likely]**, consistent with Navi.exe's GMT writer
`FUN_003e86b8` and OBJDLL's local conversion `0x40e2c3b8`/`0x40e2c360`
([07 §1](07-nz-clock-design.md)). It does not identify the exact mapped module
bytes. The internal-source possibility below and in §14.2 remains an unobserved
conditional loader lead, not an established explanation of this car's clock.

The next diagnosis must distinguish:

- **[guess]** The running app did not use the changed G214 module or selected
  another source. An ordinary resume-only explanation is not supported by the
  owner's reboot report. PM13 AppLaunch
  `FUN_ef48b860` logs `CLoadImage::LoadNkFromStorage` and selects loader methods
  through object virtual calls for modes `0x8b`/`0x8c`; this alone does not prove
  that the modified G214 at LBA 157696 was loaded. Trace:
  `work/clock-analysis/applaunch-load.log`.
- **[guess]** The hook ran but `nz_apply` retained stock output because the
  live zone/type/date did not satisfy its guards. The Japan initializer
  `FUN_40e2c4d4` establishes type `0x3d`/zone `3240000` only on its default path;
  `OBJ_Time_initialize` (`0x40e2d3d4`) also restores stored objects. The live
  values have not been captured. Static review confirms the validity check at
  object +8 matches stock `OBJ_Time_getLocalTime` (`0x40e2c3dc..0x40e2c3e4`).

**[confirmed, static]** NaviSetCC's zone-selection setter `FUN_4286cd80`
returns without `OBJ_Time_writeZoneType` for model areas below `0x20`, including
Japan `0x10`; that ordinary JP setter is not evidence that type `0x3d` was
cleared at runtime. Trace: `work/clock-analysis/naviset-zone-setters.log`.

**[confirmed, static]** STDDLL `STD_Time_setPrm` (`0x40f0bdec`),
`STD_Time_getPrm` (`0x40f0be98`) and `STD_TimeDate_setPrm` (`0x40f0c64c`)
confirm the helper's year/month/day/hour/minute/second byte offsets. Trace:
`work/clock-analysis/std-clock-layout.log`. No layout correction has been found.

Before another firmware change, obtain evidence of the active module and live
guard values. `audit_after_boot.py` performs a read-only comparison of the full
original G214 range (30,737,920 bytes at LBA 157696) against the pinned original
and the exact written v2 plus its untouched trailing bytes. It identifies the
whole physical card and requires unmounted partitions, opens only `rb`, and
compares two reopened reads. It reports exact v2, original, or other contents;
it does not modify or mount anything. macOS raw access may require administrator
access. Rediscover the current disk identifier before using `--device`.

Validation: the saved pre-patch full-card backup reports `ORIGINAL_G214_PRESENT`;
the known patched range reports `PATCH_V2_PRESERVED_EXACTLY`; a changed trailing
byte reports `OTHER_G214_CONTENTS`; an incomplete range is rejected. Only saved
files/in-memory bytes were used for these checks.

**[confirmed, post-test card read]** The owner authenticated the read-only audit
in Terminal 6. At 2026-10-24 09:08:45Z the full old G214 range still matched the
exact written v2 plus untouched trailing bytes: SHA256
`18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876`.
Two reopened reads matched. Receipt:
`work/nz-clock/audits/20261024T090845Z/audit-report.json`. The patch was not
restored to stock on the card during the test.

**[confirmed, persisted bytes; likely OBJ_Time mapping]** A sector-aligned
read-only audit at 09:11:39Z inspected only nav A/B headers and clock fields at
area +`0x144` (card `0x18a0e944` / `0x18a35544`). Generations advanced from
73717/73718 in the pre-patch backup to 73719/73720. Saved GMT values were
2026-10-24 08:56:26 / 08:57:26; both have validity 1, zone 3240000, type 61
(`0x3d`), DST 0 and user offset 0. These layouts match the known GMT, previous
time, zone/type/DST/offset and holiday-table adjacency (next field +`0x168`).
No other nav fields were exposed. Area integrity/active-copy selection was not checked;
these are saved snapshots, not a live RAM capture. The first attempt at this
small-field read failed with EINVAL; reading full aligned sectors corrected it.

Replaying both saved snapshots through the self-written host C helper returns
applied 1 and total 4680000 (+13 h) **[confirmed, host execution only]**.
Receipt: `work/nz-clock/audits/20261024T091139Z/audit-report.json`. This weakens
the guard-mismatch explanation; it does not prove runtime state or execution.

**[confirmed, static]** NaviGeneralCC clock/date getters at `0x425d4b64`,
`0x425d4bd4`, `0x425d4c44`, `0x425d4cc8` and `0x425d4d4c` use
`OBJ_Time_readLocalTime`, as do the Vehicle readers in [07]. Trace:
`work/clock-analysis/navigen-clock.log`. NaviGeneralCC analysis completed with
ARM CE exception-directory warnings; the relevant imports/functions decompiled.
The exact visible skin property binding remains unverified.

This audit establishes whether the patched G214 persisted through the test; it
cannot by itself establish that CE executed it. Do not infer a second dash patch
is needed from the two unchanged displays. The next hardware evidence needed is
a post-test read-only card audit, followed by the active hook/guard values if the
v2 bytes remain intact. Since they do, the next controlled test is §8.

## 8. Minimal fixed-NZDT diagnostic

This is a temporary test of the clock path, **not the automatic DST repair**.
`build_fixed_probe.py` starts from the pinned stock ROM and changes only two
instructions inside `OBJ_Time_getTotalOffset`:

| Runtime VA / ROM offset | Stock | Probe |
|---|---|---|
| `0x40e2c388` / `0x852388` | `14 20 95 e5` (`ldr r2,[r5,#0x14]`) | `40 29 06 e3` (`movw r2,#0x6940`) |
| `0x40e2c390` / `0x852390` | `00 20 84 e5` (redundant intermediate store) | `47 20 40 e3` (`movt r2,#0x47`) |

**[confirmed, disassembly]** The base becomes `0x476940` = 4,680,000
centiseconds = +13 h. Existing zone validation, error returns, register/stack
handling, fixed DST addition and user-offset addition remain intact. This
baseline applies to every valid zone, with no date/type applicability guard.
For the observed zero DST/user values it should move the display four hours
ahead of JST. It does not implement seasonal switching and must not be treated
as a permanent solution.

No branch, trampoline, payload, extra section, o32/TOC relocation, ROM growth
or CE timezone change is included. The ROM remains 42,541,568 bytes. The packed
probe is 30,700,032 bytes and fits the original allocation. Complete decoding
equals its pinned ROM; all known sums pass; the two unknown fields remain stock.
Re-extraction returned 287 modules / 43 files, 0 errors. LLVM disassembly confirms
both instructions and unchanged surrounding control flow. Six container tests
and seven writer fault-injection tests pass. Exact original/v2/probe range and
variant-hash checks pass using saved artifacts, with no extracted code executed.

The writer's explicit `--variant fixed-nzdt-probe` accepts only the pinned
probe and exact post-test v2 full range as its source. It saves that current v2
range for rollback, preserving the original full-card backup. The command waited
for owner administrator authentication in Terminal 6. When the owner clarified
that the SD card was in the car, the pending command was interrupted; sudo
returned to the shell without authentication. **No probe write occurred.** There
is no queued write, and any later deployment requires rediscovering and checking
the returned physical card. No second car test is claimed yet.

Interpretation: a +4-hour display change would show that this simpler path took
effect and point towards the v2 hook/section integration. No change would require
direct evidence of the active image or a different clock producer; it would not
by itself establish a GPS overwrite. Either result needs a further automatic-DST
implementation and nav/dash/timer checks.

### 8.1 Fixed +13 probe installed; owner reports no change (2026-10-25)

**[confirmed, write/read-back receipt]** After the owner returned the card and
explicitly requested installation, Terminal 6 ran the pinned
`--variant fixed-nzdt-probe` writer. The whole removable SD was freshly identified
as disk9, 16,206,790,656 bytes, and unmounted. Read-only preflight matched the
current v2 firmware range. At 00:21:53 UTC the installer wrote 30,700,032 bytes at
G214 LBA 157696 (byte offset 80,740,352), completed `fsync`, then closed/reopened
the device and verified the full 30,737,920-byte old range against the new slot
plus unchanged trailing bytes. Status: `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_BOOT_UNTESTED`.
Evidence: `work/nz-clock/writes/20261025T002153Z/write-report.json`.

Installed slot SHA256:
`a232889da7e317b5a1c749008dcd72a02131e478379994c75b0216c9ce07078d`.
The fresh, mode-0444 rollback file `G214-before-write.bin` beside the receipt
contains the previous v2 range, SHA256
`18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876`.
The owner requested cancellation of a new full-card backup and use of the
existing verified original backup (§5). The cancelled image is labelled
`backups/20261025T002056Z/card-before-patch.partial.img`, with an `INCOMPLETE.txt`
notice; it is not a valid backup. The original full backup remains unchanged.

The card was safely ejected after verification. This supersedes the earlier
uninstalled status in §8/§14.3; no new head-unit, dash or timer result has been
reported. This remains a fixed +13 baseline with existing DST/user adjustments
added, not an automatic seasonal fix.

**2026-10-25 car result [confirmed, owner report; no independent capture]:**
after the card went back in the car, the owner reported "still no change to it".
This is the third failed clock-change observation (v2 hook §7, saved zone
§§11–13, now the fixed +13 probe). The owner did not state boot/reboot timing,
GPS reception time, or which screens (head unit, dash, diagnostics) were
rechecked individually; none is assumed here. No post-car read-back of the
probe range exists, so persistence of the probe bytes after this test is
unverified (the v2 bytes did persist through §7). Per §14.3 a negative result
from this probe stays ambiguous: inactive module (e.g. the conditional loader
path §14.2, unobserved), invalid app UTC at `0x40e2c3dc`, or a display/time
source that does not go through `OBJ_Time_getTotalOffset`. §15 examines the
last possibility.

Related owner reports, recorded as stated: with SD present the diagnostics
GPS screen shows 3D and the correct GMT time of day (date and the app's live
UTC-validity byte were not observed); the owner reached diagnostics via
audio OFF → MAP×3 → audio PWR×2 → MAP×1 and saw Digital TV, Safe Driving
Message, Speaker Diagnosis and Program Update under Confirmation/Adjustment.
The owner also reports that **a hidden manual Set Clock menu appears when the
GPS antenna cable is physically disconnected** ("the physical wire if you
disconnect") — an owner lead, traced statically in §15. Nobody should
disconnect anything on the strength of this document.

## 9. Position display does not establish GPS lock

The owner reported displayed latitude/longitude **[redacted]** and asked whether
they were fallback values. No coordinates are recorded here.

**[confirmed, static]** `OBJ_CarPos_initPrm` (`0x40e33398`) calls
`STD_MeshPnt_initPrm` (`0x40f14ce8`: zero mesh, `0x7fff` components) and
`STD_PntData_initPrm` (`0x40f16748`: zero type, `0x7fffffff` components), then
`OBJ_CarPos_initialize` (`0x40e33918`) restores class 7's stored position through
`FUN_40e229d0`. These initializers do not supply a real geographic location.
Traces: `work/clock-analysis/carpos-default.log` and `position-primitives.log`.
Another navigation/receiver fallback path has not been excluded. A current or
saved last fix is **[likely]**, but a displayed coordinate alone does not identify
which source supplied it or establish satellite lock. Fix validity/used-satellite
status is needed. The clock timezone's separate +9 setting was read in §7;
position alone does not establish that the app selected an NZ timezone.

## 10. Setting-based fixed +13 alternative

**[confirmed, static]** The existing NaviSetCC hour setter `FUN_4286cbec`
(`SetExpOffsetHourSetting`, DISPID `0x6a`) accepts +4, stores
`ExpOffsetHour = 16`, and calls `FUN_4285ea98` to publish an offset of
1,440,000 centiseconds when the minute setting is zero. Keeping the stock
3,240,000 zone and DST 0 gives a total of 4,680,000 (+13 h). This setter has no
model-area gate; exposing it through the UI or a helper still needs integration.
Its ordinary setting/write path is preferable to assigning an arbitrary raw
value in the A/B store. Persistence on this car remains untested. Winter would
need +3 (stored 15); this is not automatic DST.

Directly setting a +13 base zone is also accepted by `STD_TimeZone_isValid`
(`0x40f0cec4`, explicit `0x476940` case; trace `zone-range.log`). The ordinary
`OBJ_Time_writeZone` (`0x40e2cb60`) resets the zone type to 0. A raw saved-store
edit would still require correct copy selection, integrity handling and testing
against startup overwrites; it is not established by knowing the scalar value.
At this checkpoint no settings-store edits had been made, and the pending
firmware probe was canceled when the owner said the card was in the car. The
owner later requested a patch with the card returned to the Mac; see §11.

## 11. Fixed saved-zone experiment

The owner explicitly requested patching the returned card. This experiment sets
the saved base zone directly to +13 with custom type 0, retaining zero DST/user
adjustment. It does not expose the hidden hour control. A direct +4 adjustment
on top of the earlier v2 hook could produce +17 if that hook subsequently ran;
custom +13 does not satisfy its Japan/+9 applicability guard. UTC/GPS data is
preserved. This is **fixed +13**, not automatic DST or a proven startup fix.

**[confirmed, decompiler and six independent saved copies]** VSramSD
`FUN_eeddbfd8` computes the integrity field at `size-16` before writing an area.
`FUN_eeddc57c` is a sum of LE u32 words over `[0,size-16)`, modulo 2^32.
This matches sys A/B, nav A/B and bt A/B in the verified pre-patch backup.
This explicitly corrects the earlier CRC description in [01] and README.
Trace: `work/clock-analysis/vsram-footer-check.log`. The `SRST` header holds
generation at +8 and copy ID at +12; `FUN_eeddc370` selects generations and
`FUN_eeddc4f8` constructs updated headers. `SRED` is the final four bytes.

`set_saved_zone.py` pins the known G214 v2 baseline, identifies an unmounted
whole physical card, validates both current nav copies, and requires the
reviewed clock state: valid date, Japan/+9, zero DST/user, record prefix 0.
It saves/flushes/read-verifies both complete current nav copies and the candidate
under `work/nz-clock/saved-zone-writes/`, mode 0444. No binary goes into Git.

| Field | Each nav-area offset | Edit |
|---|---|---|
| generation | `0x8` | A = previous maximum +1, B = previous maximum +2; refuse wrap |
| clock base zone | `0x158` | `40 70 31 00` (+9) → `40 69 47 00` (+13) |
| clock zone type | `0x15c` | `3d 00 00 00` → `00 00 00 00` (custom) |
| word sum | `0x26bf0` | recomputed from that complete copy's prefix |

The two copies start at LBAs 807028/807338 and each occupies 310 sectors.
Only LBAs **807028, 807337, 807338, 807647** are written (four 512-byte sectors).
All bytes outside the listed fields remain identical. The actual write
descriptor rechecks the complete baseline before the first write. fsync,
close/reopen and a full 317,440-byte pair comparison follow. Failure after a
write triggers restoration/read-verification of the four original sectors when
device identity is unchanged; pre-write refusal never rolls back.

**[confirmed, host tests]** Six tests on synthetic ordinary files cover checksum
and unsupported-state refusal, exact generation/zone/type changes, idempotence,
unchanged UTC/unrelated data, four-sector-only writes, baseline/identity refusal,
partial-write rollback, read-back failure and explicit rollback failure. A
read-only run on the verified original full-card backup also validates and
produces the expected plan. No extracted code was executed.

**[confirmed, write artifacts and subsequent full-pair raw-card audit]** The
saved-zone edit is now present on the card. Artifacts:
`work/nz-clock/saved-zone-writes/20261024T100911Z/`. The current copies have
generations 73722/73723, zone 4680000, custom type 0, zero DST/user offset, and
valid word sums. A subsequent invocation reported `ALREADY_FIXED_PLUS_13` and
read the complete 317,440-byte pair with SHA256
`redacted`, exactly
matching the saved candidate. Rebuilding that candidate from the saved before
pair also matches byte for byte. The original pair SHA256 is
`redacted`.
The card was safely ejected (`diskutil eject disk9`: success).

The initial `write-report.json` records `FAILED_ROLLBACK_UNVERIFIED`: a mounted
partition was detected **after** the four writes/fsync, preventing the old
verification/rollback identity callback from proceeding. The earlier chat claim
that this refusal occurred before any write was incorrect. That failure receipt
is preserved; `work/nz-clock/saved-zone-recovery-20261024T100911Z.json` records resolution by the subsequent
unmounted raw-card full-pair hash and successful structural/sum checks. The retry
performed no further write because both copies already had the intended state.

The tool now separates identity-only checks for read-only verification from the
unmounted-card checks required before any write/rollback. A remount after a
successful write therefore does not cause an unnecessary rollback attempt.
A new regression test simulates that exact sequence. All seven saved-zone tests
and seven existing firmware-writer tests pass after this fix.

The subsequent owner test is recorded in §12. A displayed +9 clock alone does
not prove the saved fields reverted; they could have been ignored or another
source could supply the display. Winter/automatic DST remains open. No successful
car result is claimed.

## 12. Saved-zone test unchanged; retained-DRAM restore path

**[confirmed, owner report]** The owner reports the clock stayed on Japanese
time throughout the boot with the saved-zone patch; there was no observed brief
NZ display followed by a return to Japan. This is another failed clock-correction
observation. The complete +13 nav-pair read-back in §11 was before this boot;
there is no post-test read-back yet. Do not claim the card has reverted without
reading it. GPS fix status is also not yet established.

**[confirmed, static]** `OBJ_Time_initialize` (`0x40e2d3d4`) clears the current
GMT/validity after retaining the previous timestamp. `OBJ_Time_getLocalTime`
(`0x40e2c3b8`, validity check at `0x40e2c3dc`) requires validity 1 and returns
an error otherwise. `OBJ_Time_writeGMT` (`0x40e2c8c4`) publishes the first
12 bytes, including validity 1, without writing the zone/type/DST/user fields.
Thus a valid UTC update can be needed for the app clock to update after startup;
GPS reception does not itself choose the local timezone. A stale/system-time UI
fallback while UTC is invalid remains **[guess]**; its exact binding is unproven.

**[confirmed, static]** PM13 VSramSD `FUN_eeddb0a4` (`RestoreBackupData`) has a
path logging `CheckCommitData : DRAM DATA OK` (literal at `0xeedd1698`, pointer
at `0xeeddb258`). For an area whose commit-memory check succeeds, it takes
generation/page information from the retained memory, backs that data up through
`FUN_eeddbc94`, and copies commit memory into the working memory. The SD-area
restore function `FUN_eeddb9f4` is in the other branch. A higher edited SD
generation therefore does not by itself prove that SD contents will replace
valid retained data on this path.

`CheckCommitData` at `0xeeddbd48` tests area type 2 before invoking the area
validator; LLVM ARM disassembly was used because Ghidra had not defined that
small function. `CheckAreaData` (`0xeeddbdb4`) checks `SRST`, `SRED`, format and
the word sum. `SramTable_GetAreaIDInfo_SD` (`0x40a8150c`) returns a table filled
at runtime using KernelIoControl `0x1013c34`, selector 3. The actual nav-area
type and branch taken on this unit have not been captured. Traces:
`vsram-restore-startup.log`, `vsram-dram-branch.log`, `vsram-area-types.log` under
`work/clock-analysis/`.

**[likely explanation, runtime unverified]** The saved edit may have changed an
SD backup that a valid retained clock supersedes. This can explain a correct
on-card edit with no display change, without a GPS timezone overwrite. Other
runtime initialization and display-source explanations remain open. No reset,
memory-clear operation or further card write has been attempted.

Next evidence: GPS fix/validity status and a read-only comparison of both nav
copies after this test. If the fields are Japan/+9 again, compare generations
and sums against §11; if custom +13 remains, the display did not establish use
of that saved state. A live setting change through the running app's existing
setter remains a candidate, but its invocation/integration is unproven.

## 13. Post-test card audit confirms both saved copies returned to Japan

**[confirmed, read-back, 2026-10-25]** The owner returned the card to the Mac.
It was identified as the removable physical 16,206,790,656-byte SD, then
unmounted. `set_saved_zone.py --device disk9` ran **without `--apply`**;
all card access was `rb`. Its G214 baseline check passed, confirming the
previously installed v2 range still hashes to
`18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876`.

Both complete nav areas (LBAs 807028–807337 and 807338–807647) passed the
SRST/SRED, layout and LE32 word-sum checks. At each area's relative offsets
`+0x158`/`+0x15c`, zone/type are now `3240000`/`61` (Japan/+9), with
zero DST and user offset. The generation words at `+0x08` are A=73724 and
B=73725, newer than the byte-verified pre-car +13 pair's 73722/73723.
The current pair SHA256 is
`redacted`.
Stored integrity words at area end-minus-16 are A=1877599678 and B=878321657.

This resolves the post-test storage uncertainty in §12: the saved +13 values
were replaced during the intervening car test, rather than merely remaining
unused on the card. **[likely, cause unproven]** Retained-memory backup in
§12 could explain this, but a running initializer/setter could also restore
Japan before persistence. The read-back does not establish which path ran,
nor whether the firmware hook executed. GPS fix status remains unknown.

Evidence is preserved outside Git at
`work/nz-clock/post-test-saved-zone-20261025/terminal6-readback.json` and
`audit-report.json`. The preflight output's `after` values are a calculated,
uninstalled candidate, not another write. No card bytes were written by this
audit and no reset or memory clear was performed. Repeating the same saved-zone
edit alone does not address the observed replacement; next work is to identify
and change the active clock-setting path.

## 14. Coordinator-reviewed synthesis: reset path, setter route, active image

2026-10-25. Three coordinator-reviewed GLM investigations under
`work/nz-clock/override-investigation/` (`reset-report.md`,
`active-setter-report.md`, `execution-report.md`) identify candidate reset
paths with static evidence only; the runtime branch is unobserved. No
card/device writes, no extracted-code execution, no hardware success claimed.

### 14.1 Reset writers and the direct question (static, assembly-confirmed)

| Question | Address evidence | Answer |
|---|---|---|
| Is +9 applied after a successful restore? | restore `FUN_40e229d0` @ 0x40e2d498; success branch `beq 0x40e2d4fc` | **No** — restored zone preserved; only GMT/validity cleared **[confirmed]** |
| What runs on restore failure −7? | `FUN_40e22ce8` @ 0x40e2d4b4; on fetch success, fall-through 0x40e2d4c0–0x40e2d4e8 | Japan defaults are written **into the stored copy** and committed (`FUN_40e22dd0(2)` @ 0x40e2d4e4) **[confirmed]** |
| Japan default constants | `FUN_40e2c4d4`: 0x40e2c570 `mov r2,#61`; 0x40e2c5ec zone 3,240,000 | area 0x10 → +9/type 0x3d **[confirmed]** |
| Live zone writers | `writeZoneType` 0x40e2cc38 → only NaviSetCC `FUN_4286cd80` (gated < 0x20); ungated DST toggle `FUN_4286ccc4`; offset `FUN_4285ea98`; `writeGMT` 0x40e2c8c4 → Navi.exe only | no live Japan-area zone writer outside OBJDLL in reviewed name imports **[confirmed static; not exhaustive]** |

Both the retained-DRAM backup (VSramSD `FUN_eeddb0a4`/`FUN_eeddbc94`;
generation info from commit memory via `FUN_eeddc45c`, increment
`FUN_eeddc4a4`, header writer `FUN_eeddc4f8`) and the −7 default-reset
produce +9/type 61 with generation bumps, so the §13 read-back cannot
identify which branch ran **[confirmed static; branch unproven]**. The
installed read-side hook at `OBJ_Time_getTotalOffset` (0x40e2c360) reads the
live record on every conversion, and the reset writers converge the record
to exactly the state its guard requires (type 61/+9) — so a store reset
alone does not explain the unchanged display; the prime unresolved question
is which image/module set actually executed **[confirmed reasoning]**.

### 14.2 Conditional loader lead (not a proven cause)

AppLaunch (PM13) selector-3 `FUN_ef48ed10` opens `FMD1:` and, when the
runtime flag `+0x3c == 1`, `DSK1:` at G214 LBA `0x26800` = 157696;
`FUN_ef48eb00` memcmps the two cached 512-byte headers (device +0x38; NKOK
+0x234, MTLD +0xa8); on mismatch it logs
`NK2 Header Not Match NorFlash & System SD`, re-points to FMD1 offset selector 0x56 (units unverified) and
logs `NK2 Load NorFlash Only` **[confirmed static; flag, actual FMD/SD
headers and runtime branch UNOBSERVED]**. The coordinator's audit
(`coordinator-header-audit.json`) shows candidate headers differing from
stock at u32 offsets 0x0/0x4/0x34/0x94/0x98/0x9c/0xb0 (v2 additionally
0xb4/0xb8/0xbc); no MTCP chunk table within those 512 bytes. A conditional rejection mechanism, **not** a
proven cause: no "must flash NOR" conclusion, no flashing/update-install
recommendation — future loader/updater analysis only.

### 14.3 Ranked next diagnostics (helper attach/init must be verified first)

1. **Loaded-module fingerprint**: executing OBJDLL entry bytes — stock
   `0xe92d4030`/`0xe1a04001` vs installed v2 branch `0xea01c797` — the
   decisive active-module discriminator.
2. **Synthetic conversion**: exported conversion with a fully valid
   synthetic Japan object (2026-10 UTC → +13 if v2 executed, +9 if stock);
   touches no real clock state; a helper-process result is **not**
   Navi-process proof.
3. **Live app UTC validity and consumer binding**: capture the shared
   object's GMT-validity byte and confirm which consumers bind the executed
   image. Polling is not established safe before per-process initialization;
   the global table-pointer dereference at 0x40e2c31c is from the setter
   report.

The fixed +13 probe (installed later; see §8.1): a future negative display
result would remain ambiguous even with the module loaded —
`OBJ_Time_getLocalTime` (0x40e2c3b8) gates every read on the GMT validity
byte (object +8, check 0x40e2c3dc–0x40e2c3e4) — so it cannot by itself
separate inactive module, invalid UTC, or another display source. *(Update
2026-10-25: the owner has since reported no change with this probe; see §8.1.
This paragraph's prediction stands — the result is ambiguous.)*

### 14.4 Patch guidance (no build/deploy here)

**Later implementation:** [12](12-hour-offset-ui.md) exposes the stock setter
through the skin and records the owner-reported working head-unit result.
That is the demonstrated manual workaround; the following firmware guidance
remains relevant to future automatic-DST work and avoiding double offsets.

The v2 guard does **not** require DST 0 or user offset 0 — it preserves the
user offset, ignores the old fixed DST, and changes only the conversion
output — so the saved +9 store is compatible with an active hook. **Do not**
combine a default patch (custom type 0, +13) with the unchanged Japan-only
v2 guard and claim automatic DST: the guard stops matching, giving
permanently fixed +13. The manual workaround alternative is the stock setter
with stored hour **15 (winter) / 16 (summer)**, minute 59 — not raw 3/4, and
not with v2. A complete future normalization design must handle the
successful-restore path **and** later field writes without double offsets,
and update DST across transitions; memory clears and battery disconnection
are **not** recommended.

### 14.5 Setter/dash-timer gaps (setter report)

The clock record lives in a named shared mapping (`OBJ_SHARED_MEMORY` +
`OBJ_SHARED_MEMORY_MUTEX`) **[likely; imports/strings only]**. NaviSetCC's
flat exports provide COM plumbing and the reviewed property route uses
`IDispatch::Invoke` (0x42878aa4), whose class registration is absent from
the hives; the native helper candidate (store
probe, `OBJ_Setting_writeExpOffsetHour`/`Min` 0x40e53abc/0x40e53adc, publish
via `OBJ_Time_writeOffset` 0x40e2cdf0) is availability-only evidence until
attach/init and multi-process write safety are proven. Vehicle.exe's EvTimer dispatcher `FUN_00042100` (case 10 → msg 0xc9,
`VCAN_EVTIMER_REQ_SET_CLOCK`) and local-time producer `FUN_00033098` (via
`OBJ_Time_readLocalTime`) are confirmed decompiles; the exact CAN
message/payload layout and event-evaluator poll cadence (`FUN_40e2c068`)
remain open.

### 14.6 GPS validity and hemisphere (tracked in issue #31)

The owner reports a **3D fix** and "N" beside latitude / "E" beside
longitude, so receiver no-fix is less likely — but the app's UTC-validity
byte after `OBJ_Time_writeGMT` is still unobserved. Hemisphere labelling is
tracked in issue #31: static tokens `GPS_LatitudeDirection`
(VA 0x425b8874, file 0x23674) and `GPS_LongitudeDirection`
(VA 0x425b8850, file 0x23650) exist in G214 `NaviGuideCC.dll`, but token
metadata is not getter/page-binding proof, and the parent's traces
(`gps-diagnostic-label.log`, `gps-diagnostic-render.log`,
`gps-guide-properties.log`) could not resolve the guide property lookup
(zero matching functions) — an explicit limitation. No coordinates or
personal data recorded. Tracked in
[issue #31](https://github.com/prasys/nissan-leaf-japanese-to-nz/issues/31),
which includes a separate bounded signs/status-only logging plan that is
not yet implemented.

## 15. Manual clock menu with the GPS antenna disconnected (static trace)

2026-10-25, Claude (Opus 5.5). Owner lead (§8.1): a hidden manual Set Clock
menu appears when the physical GPS antenna cable is disconnected. Static,
read-only trace of extracted G214 modules plus PM13/UP14 constant scans; no
card, car or device operations; nothing executed. Full report and logs:
`work/nz-clock/manual-clock-investigation/manual-clock-report.md`.

**Summary [confirmed static unless tagged].** The only absolute manual clock
setter in G214 is the service-menu `SLF_CLOCK_SET` backend in `DiagnosisCC.dll`
(02 §4.5). It edits the app's **GMT/UTC**, not local time, and on OK sends a
GPS "initial setting" command to Navi's sensor manager, which seeds the u-blox
receiver (UBX-CFG-RST + UBX-AID-INI). It writes no OBJ_Time zone/DST/offset,
no CE time and no manual-mode flag. The app GMT is then rewritten from receiver
output by the normal GPS writer. Antenna OPEN/SHORT is a separate signal that
sets the GPS "connect unit" state; it is a plausible menu-visibility gate, but
the skin binding is **unresolved [guess]**.

### 15.1 Gates — do not conflate

| Gate / source | Function / address | Effect | Confidence |
|---|---|---|---|
| Antenna status | Navi `FUN_003f0f18` → `FUN_003f1360` `DeviceIoControl(…, 0x80112008)`; same IOCTL in PM13 navdrv `0xeedf5618` / UP14 `0xeeff55a8` | 0 CONNECTED / 1 OPEN / 2 SHORT (strings VA `0x35404…0x35440`) | confirmed |
| Antenna → SNSMGR | `FUN_003e9fb0` (undefined in Ghidra; created in memory) | status byte `0x2ce7d7c` `|= 8` when not CONNECTED | confirmed |
| Antenna debounce | `FUN_003e8408` | >9 bad cycles → diag `0x16` OPEN / `0x17` SHORT, `SYS_setConnectUnit(0,2)`; >4 good → clear, `SYS_setConnectUnit(0,1)` | confirmed; code names likely |
| Receiver time valid | `FUN_003e86b8`, GPS struct `0x2ce7da0` bit1 (separate from antenna byte) | clear → `OBJ_Time_writeGMT`; set after valid → `OBJ_Time_invalidDate` | confirmed |
| Fix quality | `FUN_003e86b8` `(status & 0x70) < 0x40`, `+0x35` bit `0x10` | full date+time vs time-of-day-only GMT write (keeps old date) | confirmed code; semantics likely |
| App UTC validity | OBJDLL `0x40e2c3dc–0x40e2c3e4` | local read fails if GMT invalid | confirmed (§7) |
| Japan area | NaviSetCC `FUN_4286cd80`/`FUN_4285e108` | zone/summertime menus only (06 §2) | confirmed; unrelated |
| Skin visibility of "Clock Settings" | DiagnosisCC DISPID 0x19/0x1a (`FUN_4345dc70`/`FUN_4345dd14`) expose a unit table filled from `SYS_getConnectUnit`; clock functions `0x43465e60–0x43466e08` never call it | candidate gate | **guess; binding unresolved** |

Whether the receiver still reports a valid time with the antenna open is
receiver behaviour **[open]**.

### 15.2 Manual apply → reconnect → VCM

| Step | Address | Effect | Confidence |
|---|---|---|---|
| Open | `REQUEST_TIMEINFO` DISPID 0x3d `FUN_43466854` | `OBJ_Time_readGMT` → edit buffer in **UTC** (fallback 2013-01-01) | confirmed |
| Edit | DISPID 0x46/0x47 `FUN_43466b1c`/`FUN_43466c94`; limits `FUN_4346644c` (DISPID 0x5c) | month/day/hour/minute ±1; 2013-01…2089-12 | confirmed |
| OK | `SET_TIMEINFO` DISPID 0x3e `FUN_434660a0` | msg `{src 0xa6000001, dst 0x84000015, id 0x841000cd, {0x04c1, 0x01fe, YYMMDD, hhmmss}}` | confirmed |
| Route | SystemEXE name table VA `0x2c798` | `0x84000015` = `MSG_PROCESS_NAVI_SNSMGR` | confirmed |
| Handle | Navi event table VA `0x3457c` `{0x1fe → FUN_003e9058}` → `FUN_003efb74` | UBX-CFG-RST `0x0604` {00 01 02 00} then UBX-AID-INI `0x0b01` (48 B, flags 2 = time valid), `tow = (sec + 15) * 1000` at `0x3efbcc–0x3efbd8` (fixed 15 s leap offset; 18 s today) | confirmed asm; UBX meanings per public u-blox spec |
| Same as | Navi debug-shell `{"clw", 0x3e82ac, "GPS初期設定"}` @ `0x7372bc` | diagnostic menu reuses developer "GPS initial setting" | confirmed |
| GMT | `FUN_003e9fb0` → `FUN_003e86b8` → `OBJ_Time_writeGMT` (Navi is the only importer) | receiver output becomes app GMT; consistent with "no SD → no time" | confirmed static |
| Reconnect | same writer each cycle | no reclaim code: once satellites are tracked the receiver's time follows GPS and GMT is overwritten; manual value is not stored or converted | confirmed code; receiver behaviour likely |
| VCM | `OBJ_Time_getLocalTime` → Vehicle `FUN_00033098` → `FUN_00042100` case 10 `VCAN_EVTIMER_REQ_SET_CLOCK` | dash/timers follow the derived local time | confirmed decompile (§14.5); CAN payload open |

### 15.3 Consequences

**Later result:** the additive hour setter was exposed through the skin in
[12](12-hour-offset-ui.md), and the owner reports correct head-unit time.
The total-offset firmware hook below remains a candidate for future work;
its loaded bytes are still unproven.

- Not an NZ fix. Typing NZ time into this UTC field shows NZ + 9 h. Showing NZ
  time needs a false UTC (NZ − 9 h), which only lasts while the receiver has no
  satellite time, i.e. with no antenna and no positioning. Do not recommend it.
- **No new explanation for the unchanged fixed +13 probe.** The manual path
  feeds the same OBJ_Time GMT and `OBJ_Time_readLocalTime` consumers; there is
  no second local-time producer in G214. A displayed head-unit time implies
  the `getLocalTime` validity gate passed, weakening "invalid app UTC" for that
  display **[likely]**. The §14.3 explanations remain; the loader branch is
  still unobserved.
- Candidate change point stays OBJDLL `OBJ_Time_getTotalOffset` `0x40e2c360`
  (keep GPS/SNSMGR/GMT untouched; never convert before `writeGMT`, 07 §3).
  Expected: GPS position and true UTC retained, local = UTC + NZ offset, the
  manual seed shifting display identically. Blocked on proving which bytes run.

### 15.4 Bounded next verification (read-only, owner-run where noted)

1. Owner-run `tools/nz-clock/audit_after_boot.py` on the returned card: confirms whether the
   fixed +13 bytes (`a232889d…`) persisted through the car test. Pass =
   `FIXED_NZDT_PROBE_PRESERVED_EXACTLY_NO_AUTOMATIC_DST`; any other state ends
   the probe interpretation.
2. Static: decode the skin records that reference DiagnosisCC DISPIDs
   0x19/0x1a/0x3d near `SK_SCT_CLOCK_SET_CLICK` (record `0x2211d8`) to resolve
   the visibility condition. A screen description from the owner (menu path,
   fields shown) distinguishes `SLF_CLOCK_SET` from a meter/VCM clock adjust;
   no disconnection or new action is needed for that.
3. Then the loaded-module fingerprint (§14.3 #1) remains the decisive test.
