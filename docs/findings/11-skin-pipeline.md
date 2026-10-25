# Skin container format and the card writer `write_skin.py`

Source: `/SkinChange/002/substance.skn` (20,025,376 B, hidden p2, LBA 29925953), carved to `~/nissan/work/translation/substance.skn` (sha256 `ea5b5a34…6f4d`). Everything here reads the image or the carve with `open(..., "rb")`. The skin on this card was not stock when this work started: it had already been modified, which the baseline pins record. The clock fix that uses this writer is in [12](12-hour-offset-ui.md).

```sh
python3 -I tools/translation/skn_strings.py info        # sections, trailer, counts (read-only)
python3 -I tools/translation/test_write_skin.py         # writer fault injection, temp files only
```

## TL;DR

- The file has **three sections and a trailer**, and none of them uses byte-offset pointers. Section 1 is a chain of 78,668 size-prefixed records. Section 2 is 279 record indices. Section 3 holds 7,163 length-prefixed images. **[confirmed]** for the structure, **[likely]** that nothing refers to records by byte offset.
- Text lives in **typed tables** (record type `0x802`/`0x8802`) and text-element records. `skn_format.py` re-serialises them byte for byte. **[confirmed]**
- Screen logic is bytecode in code records (`0x402`/`0x8402`), decoded in [12](12-hour-offset-ui.md) §1.1.
- The trailer value `0x0F6596FD` matches no standard checksum. The unit loads same-size edited builds with it unchanged, so it is either not checked or does not cover the edited bytes **[confirmed for same-size builds]**.
- `write_skin.py` writes a reviewed same-size build to the card. It is a read-only preflight by default, and only the owner runs `--apply`.

## 1. Container format

### 1.1 Sections

| offset | tag | content |
|---|---|---|
| `0x000000` | `0x04020001` | head (0x40 B), then section-1 record chain to `0x51B9F0` |
| `0x51B9F0` | `0x04020002` | `u32 279, u32 0xACB1`, 279 × `u32`, then zero fill (16,813 B) |
| `0x520000` | `0x04020003` | `u32 0xDF9000`, then 7,163 × (`u32 len`, blob, pad 4) to `0x1318724`, zero fill |
| `0x1318FFC` | `0x04020004` | trailer: part no `470-6253-48`, `u32 0x0F6596FD`, `SKINSK18NNNI.183` |

```
0x000000  01 00 02 04 20 92 00 07 8e 33 01 00 19 8a 00 00 20 03 e0 01 87 00 00 80 00 e0 3e 00
          tag         ?           0x1338E     0x8A19      800  480    (screen size)
0x51B9F0  02 00 02 04 17 01 00 00 b1 ac 00 00 05 31 01 00 07 31 01 00 ...
0x520000  03 00 02 04 00 90 df 00 bc 15 00 00 89 50 4e 47 ...   (first blob: 0x15BC-byte PNG)
```

- Section 2's 279 values range from 41 to 78,103, all below the record count of 78,668. They are record **indices**, not offsets. **[likely]**
- The head has no field equal to the section-1 length or the section-2 offset. `0x1338E` (78,734) is close to the record count but doesn't match it. **[confirmed values; meaning unknown]**
- Section 3 (6,928 PNG + 235 zlib blobs) starts on a 64 KiB boundary after zero fill. **[guess: section alignment]**
- The trailer has the same shape as a firmware slot header (`u32` tag, Clarion part number, `u32`, `XXXXXXXX.NNN` name), but at the end of the file. Its value is not crc32, adler32, sum8, sum16 or sum32 over the body or the body with the field zeroed. **[confirmed for the algorithms tried]**

### 1.2 Section-1 records [confirmed]

`u32 (flags << 24 | size)`, `u32 type`, payload, where `size` includes the 8-byte header and is a multiple of 4. Walking from `0x40` gives exactly 78,668 records and lands on the section-2 tag at `0x51B9F0`.

```
0x40  08 00 00 00 01 40 00 00                  size 8, type 0x4001
0x58  1c 00 00 01 02 00 00 00 0c 00 00 00 "Screen" 00 00   size 0x1C, flags 1, type 2 (name)
```

The commonest types are `0x402` (8,717), `0x206`, `0x107`, `0x101` and `0x802` (3,107). Code records start `[name if flags&1][u32 if flags&2] u32 n, n×u32 sender ids, u32 0, u32 event`, then one statement ([12](12-hour-offset-ui.md) §1.1).

To test whether anything points at records by byte offset, aligned `u32` values equal to a record offset above 0x10000 were counted: 2,412 hits, against 4,963 for offset+4. A real pointer table would push the first count well above the baseline. **[likely: no offset pointers]**

### 1.3 Typed tables (type `0x802`, and `0x8802` with bit 15 set) [confirmed]

```
u32 size, u32 0x802, u32 0, u16 ndims, u16 has_header, u16 dims[ndims],
[has_header: column name strings + u16 type],  u8 elem_type, u8 flag, align 4,
prod(dims) elements
```

| elem type | element |
|---|---|
| 1 | `u32` |
| 8 | string: `u32 nbytes`, UTF-16LE, `u16 0`, align 4 (an empty cell is 8 bytes) |
| `0x0C` | variant: `u16 vtype`, align 4, value (0 = none, 1 = `u32`, 8 = string); record padded to 4 |
| 0, 3 | tagged bytes (not decoded) |

Text-element records (types `0x2A2001`, `0x2A2004`, `0x2AA001`, `0x2AA004`) each hold one string that fills the record exactly. `skn_format.Table` and `skn_format.StringRecord` parse both and re-serialise them byte-exact. The hour-row page table (type `0x8802`) in [12](12-hour-offset-ui.md) §8 uses the same layout.

## 2. Writing the card: `write_skin.py`

It writes **only** LBA 29925953 + 39,113 sectors (20,025,856 B). The last 480 bytes past the end of the file are read live and written back unchanged. The whole procedure, with backups and rollback, is in [BACKUPS.md](../BACKUPS.md).

**Pins** (in the code; change them only in a reviewed commit):

- `BASELINE_SHA` `ea5b5a34…6f4d`: the card's skin as found, identical in the 2026-10-24 image and the verified backup `work/nz-clock/backups/20261024T073738Z` (backup sha256 `redacted`) **[confirmed]**.
- `BACKUP_SHAS`: accepted `backup_card.py` receipts.
- `BUILDS`: reviewed build sha256s. The hour row is `ec1138c8…192b`, built on `6a54198a…` ([12](12-hour-offset-ui.md) §0.5).

**Preflight checks:**

- the device is the whole removable physical 16 GB SD and unmounted (`backup_card.identify`);
- the backup is pinned, read-only and holds the baseline skin;
- the build is the same size, keeps the trailer, has a walkable record chain, and its sha256 is pinned;
- the live exFAT entry `/SkinChange/002/substance.skn` is still at byte 15,322,087,936, 20,025,376 B and contiguous **[confirmed against the image]**;
- the live file bytes equal the baseline or a pinned build, and are not already the target.

**Apply:**

1. Save a rollback snapshot (`substance-before-write.bin`) and fsync it.
2. Re-check the device identity and the live range.
3. Write, then fsync.
4. Reopen the device and compare the whole range.
5. On any failure after writing, restore the snapshot and verify it.
6. Leave a JSON receipt in `$NISSAN_ROOT/work/translation/writes/<UTC stamp>/write-report.json`.

All live reads go through `sector_reader`, because `/dev/rdiskN` only accepts whole-sector, sector-aligned reads. If the write is interrupted (Ctrl-C), the tool still restores the snapshot and verifies it. The rollback snapshot is the sector-rounded range (20,025,856 B), so `--build` won't take it directly; its first 20,025,376 bytes are the file.

`test_write_skin.py` has 17 fault-injection tests on temporary files: partial write, read-back mismatch, failed rollback, identity change, changed baseline, unaligned or resized range, unpinned or wrong-size build, changed trailer, moved file, unknown live skin, already-applied build, restore, and more.

## 3. Open questions

1. Head fields `0x07009220`, `0x1338E` and `0x8A19`, and section 2's `0xACB1`: counts that a record-moving rebuild would need to keep consistent?
2. Does the unit load a build whose records move (size changes)? Only same-size builds have been tested on hardware.
3. The trailer algorithm, if it is one.
4. The 136 type-0/type-3 tables and the 168 header tables are not decoded.
