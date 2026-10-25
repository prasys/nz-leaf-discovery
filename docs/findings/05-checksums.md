# Checksums: firmware slots and the VSRAM store

Image: `nissan-sd-485-1972-00.img` (sha256 `redacted`, see `binaries/MANIFEST.md`). All work was read-only (`open(..., "rb")`).
Tools: `tools/checksums/slot_sum.py` (slots) and `tools/checksums/vsram.py` (settings/VSRAM). Both verify every field below and can print the value a modified block would need. Neither writes anything.

```sh
python3 -I tools/checksums/slot_sum.py [--img PATH] [--recompute]
python3 -I tools/checksums/vsram.py   [--src PATH] [--base SECTOR] [--recompute]
```

## TL;DR

Every integrity field we found on the card is a **plain additive sum**, never a CRC:

- `sum32(b)`: sum of little-endian u32 words, mod 2^32
- `sum8(b)`: sum of bytes; stored as u16, so mod 2^16

| where | field | algorithm | verified on | confidence |
|---|---|---|---|---|
| slot header +0x30 `SUM4` | u32 at +0x34 | `sum32(payload)` | G314, G214 | **[confirmed]** |
| slot header +0x14 | u16 | `sum8(payload) & 0xFFFF` | G314 | **[confirmed]** (G314); G214 mismatch, see §1.3 |
| NK image +0x30 (UP14, PM13) | u16 | `sum8(image with +0x30..0x31 zeroed) & 0xFFFF` | UP14, PM13 | **[confirmed]** |
| NK image +0x80 `SUM4` (UP14, PM13) | u32 at +0x84 | `sum32(image)` with the words at +0x30…0x3C and +0x84…0x8C left out; length at +0x88 | UP14 `EA9437AA`, PM13 `F22493E0` | **[confirmed]**, from leafsdtools ([13](13-prior-art-leafsdtools.md) §2.2) |
| G214 MTLD part entry +0x0C | u32 | `sum32(part)` | 2/2 parts | **[confirmed]** |
| G214 MTCP chunk entry +0x0C | u32 | `sum32(chunk padded to whole sectors)` | 11/11 chunks | **[confirmed]** |
| BASS file +0x04 | u32 | `sum32(file[0x08:size])` (already in 03 §10) | slot 790528 | **[confirmed]** |
| VSDH sector +0x1FC | u32 | `sum32(sector[0:0x1FC])` | 1/1 | **[confirmed]** |
| SRST…SRED copy, end−0x10 | u32 | `sum32(copy[0:end−0x10])`, SRST header included | 6/6 copies | **[confirmed]** |
| MINF sector +0x04 | u32 | `sum32(sector with +0x04 zeroed)` | 1/1 | **[confirmed]** |
| INITMPID sector +0x20 | u32 | `sum32(sector[0:0x20])` | 1/1 | **[confirmed]** |

Still open: G214 header +0x14 u16 (`0x6D06`), G214 MTLD +0x08 u32 (`0x2806D839`) and the NK image +0x6C u32. The first two are probably sums over the *decompressed* G214 image, which needs the MTCP decoder ([06-mtcp-lz4](06-mtcp-lz4.md)).

**Update after the MTCP work [confirmed]:** the outer MTCP compression is now resolved as
raw LZ4, with all 11 padded-chunk sums verified; see [06-mtcp-lz4.md](06-mtcp-lz4.md),
§§2–4, for the descriptor/chunk offsets and recovered WinCE image. The checksum
hypotheses below are retained as historical hypotheses, not confirmed results;
the remaining header fields are still unresolved.

**This contradicts two earlier statements:** finding 01 §4 said the MTCP chunks carry a "CRC32 per chunk", and 01 §5 / the README called the SRED trailer a "CRC". Both are sum32. 01 and the README are updated to match.

---

## 1. Firmware slots ([#11](https://github.com/prasys/nz-leaf-discovery/issues/11))

Slot header sectors: 65536, 157696, 667648, 749568, 790528. The payload starts at the next sector (`hdr+1`), and its length is the u32 at hdr+0x00. The carved `slot*.bin` files start at `hdr+1`, except BASS, whose carve includes the header sector.

### 1.1 Header layout (G314 / G214 style)

```
sector 65536:
0000: e8c8 5400 0000 0000 0000 0000 0000 0000   +00 u32 size 0x0054C8E8
0010: 0000 0000 bc5c 4733 3134 4a4c 4e49 2e30   +14 u16 0x5CBC  +16 name "G314JLNI.066"
0030: 5355 4d34 1e7a f527 0000 0000 0000 0000   +30 "SUM4" +34 u32 0x27F57A1E
0050: 3437 302d 3531 3231 2d31 3200 0000 0000   +50 part no "470-5121-12"
01f0: 0000 0000 0000 0000 0000 0000 4e4b 4f4b   +1FC "NKOK"
```

| off | type | meaning |
|---|---|---|
| 0x00 | u32 | payload bytes |
| 0x04 | u32 | G214: payload sectors (0xEA82 × 512 = 0x1D50400). G314: 0 (its size is not sector-aligned) **[likely]** |
| 0x14 | u16 | `sum8(payload)` **[confirmed for G314]** |
| 0x16 | char[] | file name |
| 0x30 | "SUM4" | tag |
| 0x34 | u32 | `sum32(payload)` **[confirmed]** |
| 0x50 | char[] | Clarion part number |
| 0x70 | MTLD | G214 only, §1.4 |
| 0x1FC | "NKOK" | validity flag |

Results (`slot_sum.py`):

```
65536 G314JLNI.066 470-5121-12 size=0x54c8e8 NKOK=True
    +0x30 SUM4 sum32 27F57A1E/27F57A1E OK
    +0x14 u16  sum8  5CBC/5CBC OK
157696 G214JLNI.066 470-5120-12 size=0x1d50400 NKOK=True
    +0x30 SUM4 sum32 1E072FBC/1E072FBC OK
    +0x14 u16  sum8  6D06/3241 BAD (raw payload; see doc)
```

Also tried and ruled out: CRC32 (zlib) and u16 word-sums (LE; BE on G214). Only the two sums above match.

### 1.2 NK images (UP14 @667648, PM13 @749568)

Their header sector holds only `+0x00 size` and `+0x1FC NKOK`. The checksum sits inside the image, in a Clarion block ahead of the CE `ECEC` signature:

```
UP14 image:
0020: 5550 3134 584e 4e49 2e31 3339 0000 0000   +20 name "UP14XNNI.139"
0030: 7f14 5820 8e01 0000 ...                   +30 u16 0x147F  +32 u32 size 0x018E2058
0040: 4543 4543 8c02 8e89 8c02 8e01 ...         +40 "ECEC" (CE ROM signature)
0050: 3437 302d 3436 3531 2d31 3600 ...         +50 part no
0060: ... 7065 0d77                              +6C u32 0x770D6570 (unknown)
```

- `+0x30 u16 = sum8(image) & 0xFFFF`, with the two bytes of the field counted as zero: UP14 `0x147F`, PM13 `0x796E`. **[confirmed]** Without the zeroing the sums are 0x1512 / 0x7A55, so the field is excluded from its own sum.
- `+0x32 u32` = image size, equal to the header's +0x00. **[confirmed]**
- **Correction:** the NK images also carry a `SUM4` record at image +0x80: u32 sum at +0x84, length at +0x88. `+0x84 = sum32` of the image with the words at +0x30…0x3C and +0x84…0x8C left out. UP14 `0xEA9437AA`, PM13 `0xF22493E0`, both stored = calculated **[confirmed]**. The earlier text said the +0x30 u16 was the only checksum. The rule comes from leafsdtools' card builder and from UP14 `PRGUpdate.exe` `Nk2FileSumCheck` (06 §6); see [13](13-prior-art-leafsdtools.md) §2.2.
- `+0x6C u32` (UP14 0x770D6570, PM13 0x77756860) is **not** a sum32, a byte-sum, or a reflected or non-reflected CRC32 of the image (from offsets 0/0x40/0x80/0x1000, with the field and +0x30 zeroed or kept), and it doesn't equal any prefix or suffix sum32. **[unknown]** The two values share their top byte 0x77, so it may be a build or version value rather than a check.

### 1.3 G214 header +0x14 (open)

The stored value is `0x6D06`, but `sum8(payload)` is `0x3241`. Sums over part A (0xD8E9) and part B (0x5958) don't match either. The MTLD table says the parts load as one image: part 0 (`MTCP`) unpacks to 0x147FE00 bytes at load offset 0, and part 1 (raw) loads at 0x147FE00 (§1.4). So the most plausible reading is that +0x14 is `sum8` of that **unpacked** 0x2892200-byte image, the same algorithm as G314 applied after decompression. **[guess]** To test it, reverse MTCP ([06-mtcp-lz4](06-mtcp-lz4.md)) and check that `sum8(unpacked part A) ≡ 0x6D06 − 0x5958 = 0x13AE (mod 2^16)`. Meanwhile SUM4 over the stored bytes still verifies, so a tool can check G214 integrity.

### 1.4 G214 MTLD / MTCP tables

MTLD sits in the slot header at +0x70. It has a 0x10-byte head (magic, count, unknown u32, 0) followed by 0x20-byte part entries starting at +0x90:

```
0070: 4d544c44 02000000 39d80628 00000000   "MTLD" count=2 +08=0x2806D839 (unknown)
0090: 00000000 f0490000 00e09300 6a0ae6b9   part0 start_sec=0 n_sec=0x49F0 bytes=0x93E000 sum32=0xB9E60A6A
00a0: 4d544350 00000000 00000000 00000000         tag "MTCP" load_off=0
00b0: f0490000 92a00000 00244101 52252164   part1 start_sec=0x49F0 n_sec=0xA092 bytes=0x1412400 sum32=0x64212552
00c0: 00000000 00fe4701 00000000 00000000         tag "" (raw) load_off=0x147FE00
```

| entry off | type | meaning | conf. |
|---|---|---|---|
| +0x00 | u32 | start sector within payload | **[confirmed]** (part 1 = 0x49F0 × 512 = 0x93E000) |
| +0x04 | u32 | sector count | **[confirmed]** |
| +0x08 | u32 | bytes | **[confirmed]** |
| +0x0C | u32 | `sum32(part)` | **[confirmed]** |
| +0x10 | char[4] | `MTCP` = compressed, empty = raw | **[likely]** |
| +0x14 | u32 | load offset in the unpacked image (0x147FE00 = MTCP unpacked total) | **[likely]** |

The two part sums add up to SUM4 (0xB9E60A6A + 0x64212552 = 0x1E072FBC mod 2^32), as they must. MTLD +0x08 (0x2806D839) is not the sum32 of the MTLD table, the MTCP header, the chunk sums or the payload. It is probably `sum32` of the unpacked image. **[guess]**; test it against the unpacked image ([06-mtcp-lz4](06-mtcp-lz4.md)).

The MTCP header is the first sector of part 0: `"MTCP" u32 count=11 u32 chunk=0x200000`, then 0x20-byte entries from +0x20: `u32 n_sec, u32 unpacked_bytes, u32 packed_bytes, u32 sum32`. The chunk data starts at +0x200, and each chunk is padded to `n_sec` sectors. The checksum is `sum32` over the **padded** `n_sec × 512` bytes, not over `packed_bytes`: 11/11 match only when the padding is included (e.g. chunk 0: stored 0xB79471C1, padded 0xB79471C1, unpadded 0xB6B17190). **[confirmed]**

### 1.5 BASS (790528)

Header sector: `"BASS" u32 0x1C50` (sectors of file data) … `"BASS"` at +0x1FC, with no checksum of its own. The file in sectors 790529… is the p1 `OPNG/MKR_OPNG/02/OIXXXVNI.004` container from 03 §10, and its `+0x04 = sum32(file[0x08:0x389EEC])` = 0x429F165B verifies here too. **[confirmed]**

### 1.6 What a slot patch would need (for a human, on a spare clone only)

For G314: change the payload, then rewrite hdr+0x34 (`sum32`) and hdr+0x14 (`sum8`). For UP14/PM13: rewrite image+0x30 (`sum8` with the field zeroed); whether +0x6C is checked is unknown. `slot_sum.py --recompute` prints these values. G214 cannot be safely patched until §1.3/§1.4 are solved, and it's not known whether the bootloader checks anything beyond these sums (signature, `NKOK`).

---

## 2. VSRAM store

All sectors below are absolute image sectors. In `settings_800768-818431.bin`, sector `s` is at byte `(s − 800768) × 512`.

### 2.1 VSDH (802816)

```
0000: ff ff 00 00 ff ff ff ff ...  (rest 0xFF)
01f0: ff ff ff ff ff ff ff ff 56 53 44 48 d8 52 45 48   +1F8 "VSDH" +1FC u32 0x484552D8
```
`+0x1FC = sum32(sector[0:0x1FC])`, so the magic is included. **[confirmed]** Sectors 802817–806911 are all blank (0xFF/0x00). The meaning of `+0x00 = FFFF0000` is unknown.

### 2.2 SRST…SRED copies (806912–809935)

Each area is stored as two copies, and each copy is a run of whole sectors from an `SRST` sector to an `SRED` sector:

```
+0x00        "SRST"
+0x04  u32   0x6000000C   (same in all 6; flags/version?)  [unknown]
+0x08  u32   generation
+0x0C  u32   copy number: 1 = A, 2 = B
+0x10 …      payload (area-specific)
end-0x10 u32 sum32(copy[0 : end-0x10])    ← includes the SRST header
end-0x0C     8 × 00
end-0x04     "SRED"
```

| area | sectors | bytes | copy | gen | trailer (stored = computed) |
|---|---|---|---|---|---|
| sys | 806912–806969 | 0x7400 | A | 0x5651 | 0xF8F0B044 |
| sys | 806970–807027 | 0x7400 | B | 0x5650 | 0xF8F0B044 |
| nav | 807028–807337 | 0x26C00 | A | 0x11FF5 | 0x7FD26BE2 |
| nav | 807338–807647 | 0x26C00 | B | 0x11FF6 | 0x16B506EF |
| bt | 807648–808791 | 0x8F000 | A | 0x91B83 | 0xC47FA8AF |
| bt | 808792–809935 | 0x8F000 | B | 0x91B84 | 0xA606E0FA |

6/6 match. **[confirmed]** Ruled out: CRC-32 (zlib, with and without final xor), CRC-32/BZIP2, CRC-32/MPEG-2, non-reflected CRC-32 with init 0, CRC-32C and byte-sums, with spans starting at 0/4/8/0xC/0x10/0x20/0x200 and ending at end−0x10/−0xC/−4/end. Only `sum32` from offset 0 to end−0x10 matches all six.

A useful check: the two sys copies have identical payloads and different headers (gen 0x5651/copy 1 vs gen 0x5650/copy 2). Both header word-sums are 0x5652, so the trailers are equal. That's consistent with the header being inside the sum.

### 2.3 A/B generation scheme

- In every pair the generations differ by exactly 1. **[confirmed]**
- **A always holds the odd generation and B the even one** on this card (sys A 0x5651, nav A 0x11FF5, bt A 0x91B83). So the generation is a per-area save counter, and each save goes to the *other* copy with `gen+1`. **[likely]** (3/3 pairs; a second image after one more save would confirm it, see [#21](https://github.com/prasys/nz-leaf-discovery/issues/21)).
- Current copy (highest generation): sys **A**, nav **B**, bt **B**. The loader presumably takes the highest-generation copy whose sum verifies and falls back to the other one (`[VSRAM]CVSramMltBackup::RestoreAreaData` in `VSramSD.dll`). **[guess]**, not disassembled yet.
- The generations are very different per area (sys ≈ 22k saves, nav ≈ 74k, bt ≈ 597k), so each area saves on its own schedule.

### 2.4 Payload structure (offsets only; nav/bt contents are personal data and are not reproduced)

Within each copy, offsets are from `SRST`. Shown are the non-blank extents (non-0x00/0xFF, merged across gaps of ≤256 bytes) and the A≠B extents (gaps ≤64):

- **sys** (0x7400): only the header, one u32 at **+0x3B4C** (`0x449D0793`, same in A and B) and the trailer. Everything else is zero. A and B differ only in +0x08..+0x0C (gen/copy). So the "sys" area currently carries a single value. **[confirmed]**
- **nav** (0x26C00): data at +0x000–0x8CB (header block; finding 01 places the timestamps at +0x144/+0x150 and the JP holiday table at +0x168–0x6D7), small records at +0x3274–0x5527, a large table at +0x7134–0xE93F, another at +0xED94–0x17A9C, and +0x1AA4F–0x21AC3 (position-like records, *redacted*). A≠B in 14 places, including +0x08–0x57 (header + first record), +0xF8–0x14A (current-time stamps), +0x3274–0x32DE and +0xB98C–0xB9E9.
- **bt** (0x8F000): sparse header records at +0x0–0x197F, then large tables (+0x34428–0x45F52, +0x59E24–0x77C48, whose first runs start every ~0x9B8 bytes, so fixed-size records **[likely]**, +0x80B5C–0x841EB, +0x86620–0x8B39F). Contents are *redacted* (paired-phone names, history). A≠B in only 4 places (+0x08 gen, +0x1494–0x14A8, +0x197C, trailer).

Record-level decoding of nav/bt is out of scope here. Differential imaging ([#21](https://github.com/prasys/nz-leaf-discovery/issues/21)) is the efficient way to name fields.

### 2.5 Other records in the settings range

- **MINF (800783)**: `+0x04 u32 = sum32(sector with +0x04 zeroed)` = 0x1DC3E0C0. **[confirmed]**
- **INITMPID (800790)**: `"INITMPID        J420150401015000"` then `+0x20 u32 = sum32(sector[0:0x20])` = 0x9E95A9B6. **[confirmed]** (01 §5 called this a "CRC".)
- MPUP (800774/800775): no checksum field visible (mostly 0xFF).

### 2.6 What a VSRAM patch would need (spare clone only)

1. Take the current (highest-gen) copy of the area.
2. Change the payload.
3. Set +0x08 = gen+1, set +0x0C to the other copy's number, and recompute the trailer with `sum32(copy[:-0x10])`.
4. Write it over the *older* copy, leaving the current one intact as a fallback.

`vsram.fixed_copy()` builds such a buffer in memory, and `vsram.py --recompute` prints the resulting trailer for an unchanged payload. Unknowns that still make this risky: whether VSDH or anything else (e.g. the keyed blobs at 800768–800772, [#10](https://github.com/prasys/nz-leaf-discovery/issues/10)) covers the areas, and whether the unit keeps a RAM/flash copy that overrides the card at boot.

## Open questions

1. G214 hdr+0x14 and MTLD+0x08: sums of the unpacked image? Needs MTCP ([06-mtcp-lz4](06-mtcp-lz4.md)).
2. NK image +0x6C: what is it, and does the bootloader check it?
3. Does the loader verify SUM4/sum8 at all, and does it check anything stronger (signature)? Needs the bootloader, which is not on the card, or `UpdateMng.exe`/`PRGUpdate.exe` from UP14.
4. VSRAM: confirm the odd/even ↔ A/B rule with a second image ([#21](https://github.com/prasys/nz-leaf-discovery/issues/21)), and disassemble `VSramSD.dll` `RestoreAreaData` for the selection and fallback logic.
5. Meaning of the SRST `0x6000000C` word and the VSDH `+0x00` word.
