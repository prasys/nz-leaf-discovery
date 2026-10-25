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
| `binaries/MANIFEST.md` | sha256 of out-of-tree binaries |
| `$NISSAN_IMG` | Card image, default `~/nissan/sdcard/nissan-sd-485-1972-00.img` |
| `~/nissan/sdcard/mnt/p1` | Partition 1, mounted read-only (may be absent after a reboot; the image is the source of truth) |
| `~/nissan/work/raw-areas/` | Carved firmware slots (`slot*_*.bin`), `settings_800768-818431.bin`, VSRAM areas, ROMHDR listings |
| `~/nissan/work/prior-art/` | Third-party repos (leafsdtools, …) cloned as untrusted data: read, never run |

Key image offsets (512-byte sectors): firmware slots at 65536 (G314), 157696 (G214/MTCP), 667648 (UP14 NK), 749568 (PM13 NK), 790528 (BASS); settings/VSRAM at 800768–818431; hidden p2 at 29925377.

**Findings numbering.** `05-` and `06-` are each used by two files. They keep their names so existing links stay valid; don't renumber them. Before you pick a number, check `docs/findings/` on main **and** the files in open PRs (`gh pr list`, then `gh pr view <n> --json files`), and take the next number nobody uses. As of #49: 01–08 and 10–13 are on main, 09 is taken by PR #28, and PR #23 adds a third `05-map-format.md`, so the next free number is **14**.

## Card writes

Start with `docs/BACKUPS.md`. The writers are on main: `tools/nz-clock/backup_card.py` (full-card backup) and `write_card.py` (G214 slot, history in `docs/findings/08-nz-clock-implementation.md`; `write_card.py` landed with #48 and `backup_card.py` was vendored earlier for the skin writer; PR #30 was closed without merging). For skins, use the pinned `tools/translation/write_skin.py` workflow in `docs/findings/11-skin-pipeline.md` and `12-hour-offset-ui.md` §0.5.

- The writer is a **read-only preflight by default**.
- `--apply` requires `--device`, a verified full-card backup made with `backup_card.py`, and pinned SHA256s for the backup, the payload and the live baseline range. It refuses on any mismatch.
- It writes **only the target byte range**. Before writing it saves a rollback snapshot of that range; afterwards it runs `fsync`, reads the range back to compare, and leaves a JSON receipt under `~/nissan/work/<topic>/writes/`.
- Ship fault-injection tests (like `test_writer.py`), and put the exact preflight and apply commands in the findings doc.
- **The owner runs `--apply` in their own Orca terminal** and enters the sudo password there. An agent may prepare or type the command, but never authenticates or applies. Check that the card is in the reader first (once it was still in the car).

## Skin

- The UI skin is hidden p2 `/SkinChange/002/substance.skn`, starting at sector 29925953. It was already modified when found. Format: `docs/findings/11-skin-pipeline.md`; bytecode: `12-hour-offset-ui.md` §1.1.
- Redact any account or ID tokens embedded in the skin.

## Clock / hour offset

- The working fix is the **skin-only hour row**: 11 bytes in `substance.skn` repoint the Clock screen's minute row at NaviSetCC `SetExpOffsetHourSetting`. Start with `docs/findings/12-hour-offset-ui.md` §0 (what changed, assumptions, procedure). Umbrella issue #29; follow-ups #44 (automatic DST), #45 (label), #46 (car validation), #47 (retire the G214 probe).
- 06/07/08 are history and groundwork. Firmware patches never showed an effect in the car (08 §7, §8.1), so don't propose a firmware route for the manual fix.
- **Do not silently change these assumptions** (12 §0.2). If your work changes one, say so in the PR and update 12:
  - JST base; +3 = NZST, +4 = NZDT; the stored hour word is h+12 (15/16);
  - the offset goes in through the stock setter, never by editing VSRAM bytes (the unit replaced a raw edit, 08 §13);
  - the skin trailer stays unchanged and same-size in-place builds are the default;
  - the skin as found (`ea5b5a34…`) and build `6a54198a…` are the baselines, and builds are pinned by SHA256 in `write_skin.py`;
  - the fixed +13 G214 probe is assumed dormant; anything that might wake it would double the correction.
- **Out of scope here:** CE timezone/registry changes for the displayed clock (CE alone doesn't change it, 07 §1) and raw edits to the settings store.

## Tooling

- Reverse-engineering skill: `~/.claude/skills/reverse-engineering/` (pinned at v2.2.4, commit 9a857bd). Read its `SKILL.md` and `references/firmware-embedded.md` and `references/native-binaries.md`. Run `python3 ~/.claude/skills/reverse-engineering/scripts/check_tools.py --task native` to see what's installed.
- Ghidra is installed (`ghidraRun`, `pyghidraRun`; headless via the Ghidra install's `support/analyzeHeadless`). Ghidra project dirs go in `~/nissan/work/ghidra/`.
- Missing tools: install with `brew` or `pip install --user` only if your task needs them, and list what you installed in your PR.

## Workflow

1. Work one GitHub issue per branch: `issue-<n>-<slug>`.
2. Commit tools and docs only. Open a PR that says `Closes #<n>` (or `Refs #<n>` if the issue isn't finished) and summarises findings, evidence, confidence and open questions.
3. If you discover new work, open a new issue with labels instead of growing the PR.
4. If your result contradicts an existing finding, say so explicitly in the PR and update the doc. Don't silently overwrite it.

## Which agent does what

| Kind of work | Agent / model |
|---|---|
| Core firmware work: CE ROM extraction, checksums, Ghidra/disassembly, map-format exploration, coordination, PR review | **Claude Code** |
| Compression-format reversing (e.g. MTCP, #6) | **Codex** with `gpt-6.1-sol` |
| Tooling/packaging, tests, quick scoped jobs | **opencode v2** with `opencode-go/deepseek-v4.1-flash` |

To start opencode on a specific model, put an untracked `opencode.json` (`{"model": "opencode-go/deepseek-v4.1-flash"}`) in the worktree and run `opencode --prompt "..."` in its terminal. `orca agent launch --agent opencode --model …` couldn't confirm the launch outcome either time it was tried.

Coordination runs through Orca: each issue gets its own worktree of this repo, and agents report status in the worktree comment (`orca worktree set --worktree active --comment "..."`).
