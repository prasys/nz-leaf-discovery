# Prior art: leafsdtools

2026-10-25. Source: <https://github.com/developerfromjokela/leafsdtools/>, cloned at commit `422c6538583854aa1d2fab046bf4f915670b0f7c` (2026-10-24) into `~/nissan/work/prior-art/leafsdtools/`. It was read as untrusted data. **Nothing in it was built or run**, including the prebuilt `LeafSDTools/ARMV4IRel/LeafSDTools.exe` and `SH4Rel/LeafSDTools.exe`, the `ci/*.py` scripts and the release image (not downloaded). The one check below is our own script, run with `python3 -I` against our read-only image.

## TL;DR

- leafsdtools is a **Windows CE program that runs on the head unit** in Software Update mode, launched from a modified update card. It backs up and writes the unit's **internal NAND** (`FMD1:`), reads and writes the PROD block and SYS_INF config (IMMO flag), and locks or unlocks the SD card with the unit's PIN. It does not touch skins, the clock, maps or the SD layout we work on. **[confirmed, source]**
- Its card builder `ci/make-card-image.py` replaces `PRGUpdate.exe` in an ARM NK image at **byte 0x14600000 = LBA 667648**, the same place as our `UP14XNNI.139` slot, and our UP14 contains `PRGUpdate.exe`, `commondll.dll` (`CApi_SetBootMode`) and `SYS_INF.dll` (`SYS_CNF_read/write`). So our unit very probably belongs to its **QY8XXX (ARM, "NissanConnect")** family, not QY7XXX (SH-4, "CarWings"). **[likely]**
- Its NK-image SUM4 rule (image +0x80 `SUM4`, u32 at +0x84) **verifies on our UP14 and PM13**. That closes a gap in [05](05-checksums.md) §1.2 and the "not yet verified" row in [06](06-hmi-clock-and-hooks.md) §6. **[confirmed]**
- It publicly ships rebuilt UP14-position images with only SUM4 and the +0x30 u16 recomputed (the +0x6C word left alone), and reports they boot. That suggests there is no signature over that slot on QY8 units. **[likely, their claim; untested here]**

## 1. What it does [confirmed, source]

| feature | how | file |
|---|---|---|
| Launch | its exe replaces `PRGUpdate.exe` in the update NK image on a dedicated card. QY8: insert the card, cycle ACC. Exit with `CApi_SetBootMode(0)` from `COMMONDLL.DLL` | `ci/make-card-image.py`, `ExitUpdateMode.cpp`, `README.md` |
| NAND backup / write | `DeviceIoControl` on `FMD1:`, read `0x1112000`, erase `0x111200C`, write `0x1112004`, 128 KiB blocks on QY8. "ALL OS" writes blocks 3…0x1FC | `ReadNAND.cpp`, `WriteNAND_QY8.cpp`, `Flash.cpp` |
| "SRAM" / "VFlash" user data | QY8: SRAM = `FMD1:` blocks 0x1FE–0x1FF, VFlash = block 0x1FD, dumped to `\SystemSD\sram_*.bin` / `vflash_*.bin` | `UserSRAM.cpp` |
| PROD info | `FMD1:` block 2 (QY8): `PROD` and `PROD2` copies 0x8000 apart, u16 byte-sum at +0x4310 of each; product ID +0x20, model +0x40, serial +0x50, SD PIN +0x60 / full 16 bytes at +0x100 | `Flash.cpp`, `ProdInf_QY8.cpp` |
| IMMO check | QY8: `SYS_INF.DLL` `SYS_CNF_read/write` code 0xF, set to 0 | `ProdInf_QY8.cpp` |
| SD lock / unlock | `DSK8:` ioctl `0x80032014` (lock) / `0x80032020` (unlock) with the 16-byte PIN. **Refused on QY8** ("SD Control is not supported on this device") | `SDPinControl.cpp`, `Flash.cpp` |

It is all on-unit and writes internal flash. That is far outside this repo's rules (we never write to the car, and never run third-party code on it). It is listed here for comparison only.

## 2. Overlap with our findings

### 2.1 SD layout [likely]

| leafsdtools constant | value | ours |
|---|---|---|
| `ARM_OFFSET` | 0x14600000 = LBA 667648 | `UP14XNNI.139` slot header at LBA 667648 ([01](01-card-layout-and-firmware.md) §3) |
| `PREAMBLE` | 0x200 | our slot header sector; the NK image starts at `hdr+1` |
| slot length check | `u32(slot,0) == img+0x32 == img+0x88` | UP14 header +0x00 = `0x018E2058` = image +0x32 = image +0x88 (check below) |
| `ARM_SLOT_SIZE` | 0x3C00000 (122,880 sectors) | 667648 + 122880 = 790528, our `BASS` slot. Their "slot" spans our UP14 **and** PM13 (749568) |
| `PHYSFIRST` | 0x88000000 | UP14/PM13 base 0x88000000 (01 §3) |
| QY7 SH-4 banks | 0x03E00000, 0x04800000 | nothing there on our card. Our G314 is at 0x2000000 |

Their release image is a separate update card (600 MB+), not a copy of a map card. We have not compared its sector 0/1 (`CLARION ID`), hidden p2 or VSRAM with ours, because that needs downloading a third-party image.

### 2.2 Checksums [confirmed]

Their ARM `checksum()`: sum of LE u32 words over the image, mod 2^32, skipping words at +0x30, +0x34, +0x38, +0x3C, +0x84, +0x88, +0x8C; stored at image +0x84 after the `SUM4` tag at +0x80. Then +0x30 u16 = byte-sum of the image minus its own two bytes. Re-implemented in a scratch script (not committed; not their code), against `$NISSAN_IMG`:

```
sector 667648 hdr size 0x18e2058 img+0x32 0x18e2058 img+0x88 0x18e2058 ECEC +0x80 SUM4
  sum4 calc EA9437AA stored +0x84 EA9437AA
  u16 calc 147F stored +0x30 147F
sector 749568 hdr size 0x127c25c img+0x32 0x127c25c img+0x88 0x127c25c ECEC +0x80 SUM4
  sum4 calc F22493E0 stored +0x84 F22493E0
  u16 calc 796E stored +0x30 796E
```

- The u16 at +0x30 is our 05 §1.2 result exactly.
- The **SUM4 at +0x80/+0x84 is new for 05**. 06 §6 described it from UP14 `PRGUpdate.exe` `Nk2FileSumCheck` with a narrower exclusion (bytes +0x30..0x35, +0x84..0x8B zeroed). That narrower rule also matches, because bytes +0x36..0x3F and +0x8C..0x8F are zero in both images. The two rules cannot be told apart on this card. Their SH-4 `sh4_checksum()` uses the narrower rule.
- Their PROD block uses a u16 byte-sum too. Every integrity field seen so far, theirs and ours, is an additive sum (05 TL;DR).
- They leave the NK +0x6C word (05 §1.2, `[unknown]`) unchanged when they rebuild the image. If their images boot as claimed, the unit does not check +0x6C against the content **[likely]**.

### 2.3 Skin format, trailer, clock [confirmed, absent]

No skin, `.skn`, trailer, clock or timezone code in the repo (`grep -i "skn\|skin\|clock\|timezone"` finds nothing outside the licence text). Nothing to compare with [11](11-skin-pipeline.md) or [12](12-hour-offset-ui.md).

### 2.4 Card binding

- QY7 units bind the card with an SD password lock (CMD42-style lock through `DSK8:`), keyed by a PIN in internal PROD flash. On QY8 the tool refuses SD lock control. **[confirmed, source]**
- Our card images and reads normally on a Mac, so it is not password-locked **[confirmed]**. That fits a QY8-family unit.
- The high-entropy blobs at LBA 800768–800772 ([#10](https://github.com/prasys/nz-leaf-discovery/issues/10)) and `MagicGate.dll` (present in our UP14 and PM13) are not mentioned by leafsdtools. Card binding on QY8 is still **[open]**.

### 2.5 Write tools

| | leafsdtools | ours |
|---|---|---|
| target | internal NAND, PROD, SYS_INF, SD lock | the SD card only, from a Mac |
| runs on | the head unit (update mode) | the owner's Mac; the unit is never driven |
| verification | block size check per write | pinned SHA256 of backup, payload and live baseline; exact range; rollback snapshot; fsync; full read-back; JSON receipt |
| who applies | the user at the car | the owner, in their own terminal |

## 3. What it confirms or contradicts

1. **Confirms** the NK SUM4 rule and the +0x30 u16 (§2.2). Update made in 05 §1.2 and 06 §6.
2. **Confirms** 06 §4: our G214 `MaintenanceCC` dumps `VSram_All.bin` from records 0x1FE/0x1FF and `VFlash_All.bin` from 0x1FD with ioctl `0x1112000`. leafsdtools uses the same ioctl and the same block numbers on `FMD1:` for QY8 "SRAM"/"VFlash". Two independent sources agree **[confirmed]**.
3. **Raises a question for 12 §1.4 / §4**: the unit's SRAM lives in internal NAND, and the SD VSRAM (`VSram_SD_All.bin`, `DSK1:` LBAs 0xC4000 = 802816 and 0xC5000 = 806912) is a separate area. Our ExpSet read-back uses the SD copy. Whether it is the primary store or a mirror of the internal SRAM is **[open]**. This matters for persistence ([#4](https://github.com/prasys/nz-leaf-discovery/issues/4)) and for trusting `expset_scan.py` read-backs.
4. **Weakens** the risk note in [02](02-unit-and-clock.md) §7 row 6 that a signature (`CWS/CERT/ca.der`) may block modified firmware: a modified UP14-position image apparently boots on QY8 **[likely]**. It says nothing about G214, whose load path has its own NOR/SD header gate (08 §14.2), and our G214 probe still shows no effect.
5. **Contradicts the "Carwings" label** in 02 §0 if our unit is QY8: leafsdtools calls QY7XXX "CarWings" (SH-4) and QY8XXX "NissanConnect" (ARM). Ours is ARM (05 §3) with the QY8 update-slot offset. The 01 guess that the old FAT label `NCG2K2_16G` means "Nissan Connect Gen2" fits. **[likely]**; the chassis sticker or the owner's Version Information screen would settle it.

## 4. Open questions and follow-ups

- Is the SD VSRAM the primary store for ExpSet, or a mirror of internal NAND SRAM? [#6](https://github.com/prasys/nz-leaf-discovery/issues/6).
- Confirm the unit family (QY8XXX?) from the sticker or a part number. [#7](https://github.com/prasys/nz-leaf-discovery/issues/7).
- The NK SUM4 exclusion width (+0x36..0x3F, +0x8C..0x8F) cannot be separated on this card; noted on [#11](https://github.com/prasys/nz-leaf-discovery/issues/11).
- Pinned restore writers (G214 snapshot, whole card): [#8](https://github.com/prasys/nz-leaf-discovery/issues/8).
- QY8 card binding ([#10](https://github.com/prasys/nz-leaf-discovery/issues/10)) gets no help from leafsdtools.
- leafsdtools could take an internal-NAND backup, which we do not have. Running it means executing third-party code on the car, which agents must not do or suggest; that is purely the owner's call.
