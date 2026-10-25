# Backups, writing and rollback

One guide for everything that touches a physical card. Read it before you write anything. It is based on one 16 GB card (`485-1972-00`) from one car; sizes and offsets are pinned to that card and the tools refuse anything else.

**Who runs what.** Agents and helpers may prepare commands and builds. Only the card's owner runs the commands marked *owner*: they need `sudo`, raw device access, or they write. That is a hard rule in [AGENTS.md](../AGENTS.md).

## 1. Image the card read-only with `image_card.py` (owner)

Do this once, before anything else, and before macOS mounts the card (Finder writes `.Spotlight-V100`/`.fseventsd` to any volume it mounts). `tools/nz-clock/image_card.py` writes `$NISSAN_IMG` (default `~/nissan/sdcard/nissan-sd-485-1972-00.img`, or `--out`) only if it doesn't exist. It opens the device `O_RDONLY`, never mounts, unmounts or overwrites, and records the SHA256. It takes the size from you (`--expect-bytes`), so it also works for other cards.

```sh
diskutil list                                   # find the card, e.g. disk9; note its size in bytes
diskutil unmountDisk /dev/disk9                 # owner step: the tool refuses mounted partitions
# 1. preflight (read-only, no sudo): must print READ_ONLY_PREFLIGHT_PASSED and the exact command
python3 -I tools/nz-clock/image_card.py --device disk9 --expect-bytes 16206790656
# 2. owner: run the printed command (same arguments plus --out and --image)
sudo python3 -I tools/nz-clock/image_card.py --device disk9 --expect-bytes 16206790656 --out ~/nissan/sdcard/nissan-sd-485-1972-00.img --image
```

It copies to a temp file next to the target, fsyncs, re-reads and hashes it, links it into place, writes `<image-name>.report.json` next to it (UTC time, device identity, bytes, SHA256), and sets both files to 0444. Status lines: `READ_ONLY_PREFLIGHT_PASSED`, `IMAGED_AND_VERIFIED`, `REFUSED`, `IMAGING_FAILED`. Exit 0 ok, 1 refused or failed, 2 usage.

Preflight also proves the target directory can take the image: it tries a hard link on tiny probe files, and if the file system has none (exFAT) it tries macOS `renamex_np` with `RENAME_EXCL`. If neither works it refuses, before any copy. Pick `--out` on APFS/HFS+ in that case.

**If the image already exists** the tool only verifies it (size, SHA256 against `<image-name>.report.json`, mode 0444, both files), prints `IMAGE_VERIFIED` and exits without touching `diskutil` or any device. Exit 3 means verification failed. Several images can share a directory, each with its own report. An old shared `image-report.json` is still read, but only if its `image` field names that file.

**Image made by hand with `dd`** (no report): make it read-only yourself, then adopt it. This hashes the file once and writes the report; it opens no device and never changes the image.

```sh
chmod 0444 ~/nissan/sdcard/nissan-sd-485-1972-00.img     # adopt refuses otherwise
python3 -I tools/nz-clock/image_card.py --out ~/nissan/sdcard/nissan-sd-485-1972-00.img --adopt
```

The report says `ADOPTED_UNVERIFIED_SOURCE` with no device identity: the card itself was never compared with the file. It refuses if a report already exists.

Everything else in this repo reads the image, never the card.

**Fallback: manual `dd`.** Same prerequisites, no checks:

```sh
sudo dd if=/dev/rdisk9 of=$HOME/nissan/sdcard/nissan-sd-<label>.img bs=4m status=progress
shasum -a 256 $HOME/nissan/sdcard/nissan-sd-<label>.img
chmod 0444 $HOME/nissan/sdcard/nissan-sd-<label>.img
```

**`if=` is the card and `of=` is a file. Swap them and the card is destroyed. Check that twice.**

## 2. Full-card backup with `backup_card.py` (owner)

`tools/nz-clock/backup_card.py` is the backup the writers trust. It checks that the device is a whole, removable, physical 16,206,790,656-byte disk with no mounted partitions, opens it read-only, writes into a **new** directory under `$NISSAN_ROOT/work/nz-clock/backups/<UTC>/`, then re-reads the saved file and compares hashes.

```sh
sudo python3 -I tools/nz-clock/backup_card.py --device diskN --work-root ~/nissan/work
```

Then:

1. **Verify.** `backup-report.json` next to `card-before-patch.img` records the SHA256 and size, and the tool has already re-read the file once. Recompute with `shasum -a 256` after every copy.
2. **Pin.** The writers only accept a backup whose SHA256 you pin. Backup hashes identify one card, so they are not committed: set `NISSAN_BACKUP_SHA256` to your backup's SHA256 (comma-separated for several) in the terminal that runs the writer. Unset means the writer refuses.
3. **Store a second copy off the machine**, on an encrypted external disk. The image holds your phonebook, paired phones and location history, so never put it in cloud sync, a shared drive or git.
4. The tool leaves the image read-only (mode 0444). Keep it that way on every copy.

The owner's backup is `work/nz-clock/backups/20261024T073738Z/card-before-patch.img`. It predates every write to the card (G214 probe, skin builds, hour row).

## 3. A spare cloned card ([#9](https://github.com/prasys/nz-leaf-discovery/issues/9), untested)

The safest place for an experiment is a clone on a spare card of the same or larger size, with the original in a drawer. **Nobody has tested yet whether a clone boots the car** ([#9](https://github.com/prasys/nz-leaf-discovery/issues/9)). The card may be bound to the unit; the keyed blobs at LBA 800768–800772 are unexplained ([#10](https://github.com/prasys/nz-leaf-discovery/issues/10)). Until [#9](https://github.com/prasys/nz-leaf-discovery/issues/9) is answered, assume a clone may not work, and keep the original card and its backup intact.

Writing a clone is an owner step with `dd` onto the **spare** device. There is no pinned clone tool yet. If you need one, open an issue rather than improvising.

## 4. Writing a skin with `write_skin.py` (preflight, then owner `--apply`)

All current changes are skin builds written by `tools/translation/write_skin.py`. It writes only the sectors of hidden p2 `/SkinChange/002/substance.skn`: LBA 29925953, 20,025,856 bytes.

It refuses unless all of these hold:

- the device is the expected whole removable 16 GB card, unmounted;
- `--backup` is a pinned `backup_card.py` backup that holds the stock skin;
- `--build` is the same size, keeps the stock trailer, parses, and its SHA256 is pinned in `BUILDS`;
- the live exFAT entry still puts the file at that place, contiguous, at that size;
- the live bytes equal the stock skin or a pinned build, and are not already the target.

```sh
# 1. preflight (read-only): must print READ_ONLY_PREFLIGHT_PASSED
sudo python3 -I tools/translation/write_skin.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build <build>/substance.skn --work-root ~/nissan/work
# 2. owner: the same command plus --apply
```

Check the card is in the Mac's reader first. Once it was still in the car. Build-specific steps: [12](findings/12-hour-offset-ui.md) §0.5 (hour row).

## 5. Receipts and rollback snapshots

Every `--apply` leaves a new directory `~/nissan/work/<topic>/writes/<UTC>/` with:

- `write-report.json`: device, backup, build and live SHA256s, byte range, result (`WRITTEN_AND_BYTE_VERIFIED_…`), fsync and read-back status;
- a read-only rollback snapshot of the range as it was before the write (`substance-before-write.bin` for skins, `G214-before-write.bin` for the G214 writer).

If a write or its read-back fails, the writer restores the snapshot itself and verifies it. A refusal before writing never touches the card.

Writes so far: `nz-clock/writes/20261024T084550Z` (G214 probe, 08 §5), `translation/writes/20261025T004225Z` (build `6a54198a`), `translation/writes/20261025T011928Z` (hour row, 12 §7).

## 6. Rolling back

| to undo | how | status |
|---|---|---|
| hour row | set the Clock row to 0 first, then `write_skin.py --build ~/nissan/work/translation/build/substance.skn` (build `6a54198a`) | supported |
| all skin changes | `write_skin.py --build ~/nissan/work/translation/substance.skn` (the skin as found, `ea5b5a34`) | supported |
| G214 probe | needs a pinned restore of the `G214-before-write.bin` snapshot. `write_card.py` only writes its two candidate variants | open ([#5](https://github.com/prasys/nz-leaf-discovery/issues/5), [#8](https://github.com/prasys/nz-leaf-discovery/issues/8)) |
| everything | write the whole `card-before-patch.img` back to the card | no pinned tool yet ([#8](https://github.com/prasys/nz-leaf-discovery/issues/8)); see below |

Set the hour row to 0 before a skin rollback. The stored offset lives in the unit's settings, not in the skin, so a skin without the hour row has no button to clear it.

**Restoring the full backup.** There is no pinned whole-card restore writer today. A raw `dd` of the backup onto the card would work in principle, but it skips every check above, and it also rolls back settings the unit has saved since the backup (VSRAM). Treat it as a last resort, for the owner only, after a fresh backup of the current state. A pinned restore tool is tracked in [#8](https://github.com/prasys/nz-leaf-discovery/issues/8).
