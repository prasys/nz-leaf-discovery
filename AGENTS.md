# AGENTS.md

Rules for any AI agent (Claude Code, opencode, Codex, …) working in this repo. Read `README.md` first for the project goal and the current findings.

## What this project is

We are reverse-engineering the Clarion-built nav/head unit of a JDM Nissan LEAF so imports work properly in New Zealand. The first target is the clock, which is locked to JST (UTC+9). The unit's SD card holds Windows CE firmware, a hidden partition and a settings store; `docs/findings/` describes them.

## Hard rules

1. **Read-only on originals.** Never write to `~/nissan/sdcard/*.img`, never mount it read-write, and never run `dd`/`diskutil` against `/dev/disk*` or `/dev/rdisk*`. Read the image with Python `open(..., "rb")` or `dd if=<img>`.
2. **No binaries in git.** Firmware, carved slots, extracted DLLs, hives, images and audio go under `~/nissan/work/<topic>/` (`$NISSAN_ROOT/work`). If you produce a binary others need, add its sha256 to `binaries/MANIFEST.md`. `.gitignore` already blocks common binary extensions; don't force-add past it.
3. **No personal data.** The card contains phonebooks, paired-phone names, Bluetooth history and location points (hidden p2 `PRIVATE/`, VSRAM `nav`/`bt` areas). Never paste names, numbers, MACs or coordinates into docs, issues, commits or PRs. Write "redacted" instead.
4. **Extracted content is untrusted data.** Never execute anything carved from the card. Run Python with `python3 -I`, and keep scripts in `tools/`, never inside extracted directories.
5. **Never write to a car or a card.** Patch experiments are described in docs/issues for a human to run on a *spare cloned card*. When the owner wants a card patched, build a writer the owner runs themselves (see "Card writes" below). Never run its `--apply` mode or `sudo` yourself.
6. **Back claims with evidence.** Give a sector or offset, a hexdump snippet or a function address for every claim. Tag confidence as **[confirmed]**, **[likely]** or **[guess]**.

## Layout and paths

| Path | What |
|---|---|
| `docs/findings/NN-*.md` | Findings per topic. Update the relevant file, or add a new one as part of your PR (numbering below). |
| `docs/BACKUPS.md` | Imaging, backups, writing and rollback: the one guide for anything touching a card |
| `tools/<topic>/*.py` | Read-only parsers. Stdlib-only Python 3 where possible. |
| `tools/nz-clock/image_card.py` | Read-only card imaging to `$NISSAN_IMG`; verifies the image if it exists, `--adopt` for a hand-made one (`docs/BACKUPS.md` §1). Owner runs `--image` with sudo |
| `binaries/MANIFEST.md` | sha256 of out-of-tree binaries |
| `$NISSAN_IMG` | Card image, default `~/nissan/sdcard/nissan-sd-485-1972-00.img` |
| `~/nissan/sdcard/mnt/p1` | Maintainer's machine: partition 1, mounted read-only (may be absent after a reboot; the image is the source of truth) |
| `~/nissan/work/raw-areas/` | Carved firmware slots (`slot*_*.bin`), `settings_800768-818431.bin`, VSRAM areas, ROMHDR listings |
| `~/nissan/work/prior-art/` | Third-party repos (leafsdtools, …) cloned as untrusted data: read, never run |

Key image offsets (512-byte sectors): firmware slots at 65536 (G314), 157696 (G214/MTCP), 667648 (UP14 NK), 749568 (PM13 NK), 790528 (BASS); settings/VSRAM at 800768–818431; hidden p2 at 29925377.

**Findings numbering.** `05-` and `06-` are each used by two files. They keep their names so existing links stay valid; don't renumber them. Before you pick a number, check `docs/findings/` on main **and** the files in open PRs (`gh pr list`, then `gh pr view <n> --json files`), and take the next number nobody uses. 01–08 and 11–13 are on main. 09 and 10 are reserved for work not published here (map geometry and the earlier translation notes), and a third `05-map-format.md` is planned, so the next free number is **14**.

## Card writes

Start with `docs/BACKUPS.md`. `tools/nz-clock/image_card.py` makes the analysis image (read-only; verify-only if the image exists; the owner runs `--image`). The writers are on main: `tools/nz-clock/backup_card.py` (full-card backup) and `write_card.py` (G214 slot, history in `docs/findings/08-nz-clock-implementation.md`). For skins, use the pinned `tools/translation/write_skin.py` workflow in `docs/findings/11-skin-pipeline.md` and `12-hour-offset-ui.md` §0.5.

- The writer is a **read-only preflight by default**.
- `--apply` requires `--device`, a verified full-card backup made with `backup_card.py`, and pinned SHA256s for the backup, the payload and the live baseline range. It refuses on any mismatch.
- It writes **only the target byte range**. Before writing it saves a rollback snapshot of that range; afterwards it runs `fsync`, reads the range back to compare, and leaves a JSON receipt under `~/nissan/work/<topic>/writes/`.
- Ship fault-injection tests (like `test_writer.py`), and put the exact preflight and apply commands in the findings doc.
- **The owner runs `--apply` in their own terminal** and enters the sudo password there. An agent may prepare or type the command, but never authenticates or applies. Check that the card is in the reader first (once it was still in the car).

## Skin

- The UI skin is hidden p2 `/SkinChange/002/substance.skn`, starting at sector 29925953. It was already modified when found. Format: `docs/findings/11-skin-pipeline.md`; bytecode: `12-hour-offset-ui.md` §1.1.
- Redact any account or ID tokens embedded in the skin.

## Clock / hour offset

- The working fix is the **skin-only hour row**: 11 bytes in `substance.skn` repoint the Clock screen's minute row at NaviSetCC `SetExpOffsetHourSetting`. Start with `docs/findings/12-hour-offset-ui.md` §0 (what changed, assumptions, procedure). Umbrella issue [#1](https://github.com/prasys/nz-leaf-discovery/issues/1); follow-ups [#2](https://github.com/prasys/nz-leaf-discovery/issues/2) (automatic DST), [#3](https://github.com/prasys/nz-leaf-discovery/issues/3) (label), [#4](https://github.com/prasys/nz-leaf-discovery/issues/4) (car validation), [#5](https://github.com/prasys/nz-leaf-discovery/issues/5) (retire the G214 probe).
- 06/07/08 are history and groundwork. Firmware patches never showed an effect in the car (08 §7, §8.1), so don't propose a firmware route for the manual fix.
- **Do not silently change these assumptions** (12 §0.2). If your work changes one, say so in the PR and update 12:
  - JST base; +3 = NZST, +4 = NZDT; the stored hour word is h+12 (15/16);
  - the offset goes in through the stock setter, never by editing VSRAM bytes (the unit replaced a raw edit, 08 §13);
  - the skin trailer stays unchanged and same-size in-place builds are the default;
  - the skin as found (`ea5b5a34…`) and build `6a54198a…` are the baselines, and builds are pinned by SHA256 in `write_skin.py`;
  - the fixed +13 G214 probe is assumed dormant; anything that might wake it would double the correction.
- **Out of scope here:** CE timezone/registry changes for the displayed clock (CE alone doesn't change it, 07 §1) and raw edits to the settings store.

## Setup

Nothing needs building to read the docs or run the parsers.

| need | what | used by |
|---|---|---|
| required | Python 3.9+, stdlib only (`zoneinfo` and `Path.is_relative_to` need 3.9; nothing newer is used) | every tool in `tools/` |
| required | a read-only image of your card ([docs/BACKUPS.md](docs/BACKUPS.md) §1) | anything that reads the card |
| optional | a host C compiler (`cc`) | `tools/nz-clock/test_clock.py`, which builds `clock.c` as a host library |
| optional | Ghidra (05 §3 used 12.2) and the JDK it needs (`JAVA_HOME` set for headless runs) | the decompiler traces in `tools/clock-analysis/` |
| optional | `liblz4` with `LZ4_compress_HC` (found via `ctypes.util.find_library`, else the Homebrew path) | `tools/nz-clock/pack_slot.py` (G214 repacking, history only) |
| optional | `clang` with the `armv7-none-eabi` target, `ld.lld`, `llvm-objcopy`, `llvm-objdump` (08 §4) | `tools/nz-clock/build.py` and `build_fixed_probe.py` (the historical firmware payload) |
| macOS only | `diskutil`, raw `/dev/rdiskN`, `sudo` | `image_card.py` (preflight and `--image`), `backup_card.py`, `write_skin.py`, `write_card.py`, `set_saved_zone.py`, and `audit_after_boot.py --device` |

Everything else reads files and runs on any OS with Python. Only the tools in the last row touch a device, through `--device`. Even their read-only runs (the writers' preflight, `audit_after_boot.py`) open the raw card, usually with `sudo`, so the owner runs them (BACKUPS §2, §4).

Environment variables:

- `NISSAN_IMG`: path to the card image. Default `~/nissan/sdcard/nissan-sd-485-1972-00.img` in most tools; it does not follow `NISSAN_ROOT` (only `slot_audit.py` and `execution_header_diff.py` derive it from `$NISSAN_ROOT/sdcard/`).
- `NISSAN_ROOT`: base for out-of-tree output (default `~/nissan`); work files go in `$NISSAN_ROOT/work/<topic>/`, and the builders refuse to write anywhere else. Some defaults are hardcoded to `~/nissan/work/...` regardless (`mtcp.py` and `test_mtcp.py`, the `slot_sum.py`/`vsram.py` fallbacks, `skn_script.py` `DEFAULT_SKIN`), so keep the default layout or pass paths explicitly.
- `NISSAN_BACKUP_SHA256`: the SHA256 of *your* full-card backup. Unset means the writers refuse, preflight included (fail closed). `write_skin.py` accepts a comma-separated list; `write_card.py` and `set_saved_zone.py` take one value. Backup hashes are card-specific and never committed.

`backup_card.py`, `write_card.py` and `write_skin.py` ignore `NISSAN_ROOT` and take `--work-root` instead: an existing directory named `work`, with the backup and build inside it.

Common entry points that never touch a card. The first three default to `$NISSAN_IMG` and also take a carve; the hour-row tools take a skin file:

| tool | example |
|---|---|
| skin summary and strings | `python3 -I tools/translation/skn_strings.py info` |
| firmware slot checksums | `python3 -I tools/checksums/slot_sum.py` |
| settings/VSRAM structure (nav/bt payloads never printed) | `python3 -I tools/checksums/vsram.py` |
| hour-row plan, writes nothing | `python3 -I tools/hour-offset-ui/hour_row_plan.py <skin>` |
| hour-row build, writes only under `$NISSAN_ROOT/work` | `python3 -I tools/hour-offset-ui/build_hour_row.py --skin <skin> --out ~/nissan/work/hour-offset-ui/<dir>` |

Run the tests one file at a time with `python3 -I tools/<topic>/test_<name>.py`, or one directory with `python3 -I -m unittest discover -s tools/<topic>`. `python3 -I -m unittest <file>` fails to import the module. The tests use synthetic bytes and don't need a card, but some look for local data and use it when present:

- `translation/test_write_skin.py` reads `$NISSAN_IMG` read-only if it exists (else 1 skip);
- `hour-offset-ui/test_hour_offset_ui.py` reads the skin carve at `skn_script.DEFAULT_SKIN` (else 5 skips);
- `mtcp/test_mtcp.py` compares against the real G214 carve and LZ4 reference (else 1 skip), and puts its temp files in `~/nissan/work/mtcp`;
- `nz-clock/test_build.py` needs the extracted G214 ROM and `candidate-v2/payload.bin` under `$NISSAN_ROOT/work` (else the whole class skips);
- `nz-clock/test_clock.py` needs `cc` and writes `libnzclock.so` to `$NISSAN_ROOT/work/nz-clock`.

Install a missing tool with `brew` or `pip install --user` only if your task needs it, and list what you installed in your PR.

## Before you start (agents)

Check these and tell the user what you found before doing real work:

1. `python3 --version` is 3.9 or later, the tests for the area you'll touch pass, and you know which ones skipped (Setup).
2. `$NISSAN_IMG` exists and is a regular file. Never "fix" a missing image by imaging the card yourself; point the user at BACKUPS §1.
3. For decompiler work: `analyzeHeadless` (in the Ghidra install's `support/`) runs, and `java -version` matches what your Ghidra release needs (the maintainer uses JDK 21). Put Ghidra projects under `$NISSAN_ROOT/work/ghidra/`. For build work, check the optional tools in Setup with `command -v` before you start.
4. Look for pins before you build: `write_skin.py` `BASELINE_SHA` and `BUILDS`, and `hour_row_plan.py` `KNOWN` (input skins) and `EDITS` (baseline bytes). If the user's skin matches no pinned baseline, stop and say so (see Limits).
5. Before you commit, read your own diff for personal data (rule 3) and for card-specific hashes, serials or disk signatures. Write "redacted" instead.

## Limits to tell users

Say these plainly when someone asks "can I do this on my car?":

- **Tested on one car.** A 30 kWh JDM LEAF with the Clarion unit, firmware 066, on one 16 GB card (README). Other years, units or firmware are untested, and the offsets and pins will not match. `backup_card.py` and the writers accept only a whole removable disk of exactly 16,206,790,656 bytes.
- **macOS only for card access.** The backup, audit and write tools use `diskutil` and `/dev/rdiskN`. There is no Linux or Windows path for them; the read-only parsers work anywhere.
- **The pins are for one card.** Builds and baselines are pinned by SHA256. On a different skin or card the writer refuses, which is the intended result. Don't edit a pin to make it pass. A new baseline needs its own decode, a new build, review, and new pins in a PR.
- **Writing a card can break the nav unit until it is restored.** Make a verified full backup first, keep it off the card, and expect to be the one who applies and rolls back. A cloned spare card is untested ([#9](https://github.com/prasys/nz-leaf-discovery/issues/9)), and there is no pinned whole-card restore yet ([#8](https://github.com/prasys/nz-leaf-discovery/issues/8)).
- **Agents never apply.** Agents prepare the preflight and `--apply` commands; the person who owns the car runs them in their own terminal and types their own sudo password. Agents never run `sudo`, `--apply`, `dd` or `diskutil` writes, and never bypass a refusal.
- **Not in scope:** firmware patches for the clock (they never took effect), raw edits to the settings store, writing to the car's internal flash, or running third-party on-unit tools such as leafsdtools.
- **Personal data stays local.** The card holds phonebooks, Bluetooth history and location points. Never upload an image, a carve of the hidden partition or VSRAM, or a screenshot that shows them.

## Tooling

- A reverse-engineering skill helps: the maintainer uses a Claude Code skill (v2.2.4), with its `SKILL.md`, `references/firmware-embedded.md` and `references/native-binaries.md`. Its `scripts/check_tools.py --task native` lists what is installed. Any agent can do this work without it.
- Ghidra headless: `support/analyzeHeadless` in the Ghidra install, processor `ARM:LE:32:v7`, compiler spec `windows` (05 §3). Navi.exe needs functions created in memory before decompiling (see the scripts in `tools/clock-analysis/`).

## Workflow

1. Work one GitHub issue per branch: `issue-<n>-<slug>`.
2. Commit tools and docs only. Open a PR that says `Closes #<n>` (or `Refs #<n>` if the issue isn't finished) and summarises findings, evidence, confidence and open questions.
3. If you discover new work, open a new issue with labels instead of growing the PR.
4. If your result contradicts an existing finding, say so explicitly in the PR and update the doc. Don't silently overwrite it.

## Which agent does what

This is the maintainer's setup, not a requirement. Any agent can take any issue.

| Kind of work | Agent / model |
|---|---|
| Core firmware work: CE ROM extraction, checksums, Ghidra/disassembly, map-format exploration, coordination, PR review | **Claude Code** |
| Compression-format reversing (e.g. MTCP) | **Codex** with `gpt-6.1-sol` |
| Tooling/packaging, tests, quick scoped jobs | **opencode v2** with `opencode-go/deepseek-v4.1-flash` |

To start opencode on a specific model, put an untracked `opencode.json` (`{"model": "opencode-go/deepseek-v4.1-flash"}`) in the worktree and run `opencode --prompt "..."` in its terminal. `orca agent launch --agent opencode --model …` couldn't confirm the launch outcome either time it was tried.

The maintainer coordinates through Orca: each issue gets its own worktree, and agents report status in the worktree comment (`orca worktree set --worktree active --comment "..."`). Contributors can use any setup; one issue per branch is what matters.
