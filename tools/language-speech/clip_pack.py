#!/usr/bin/env python3
"""English clip packs: list the clip sets, export a pack, build a GID from one.

Run with python3 -I. A pack holds only our English clips (encoded exactly as
written to the card), their decoded preview WAVs and a manifest with hashes.
It never holds stock audio. `build` patches your own stock GID with a pack and
refuses unless the result matches the manifest's build hash, so a pack
reproduces a pinned build byte for byte with no TTS account, ffmpeg or
Speech.exe. No device I/O.

  list         the clip IDs, wording and slot sizes for a clip set (TSV on stdout)
  extract-gid  copy SPEECH/JP/GID/SJP00300.GID out of a card image (read-only)
  export       maintainers: turn a prepare_greeting.py build directory into a pack
  build        owners: stock GID (+ greeting build for EV) + pack -> SJP00300.GID
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from greeting import CLIP_SETS, locked_text, output_path
from gid_patch import OUTER_SHA, patch, sha

REPO = Path(__file__).resolve().parents[2]
FITS = {"greeting": REPO/"translations/greeting-slot-fits.tsv",
        "ev": REPO/"translations/ev-slot-fits.tsv"}
FORMATS = {"02010102": "PCM16 22050 Hz mono", "02040102": "SSC 22050 Hz mono"}
PACK_VERSION = 1


def list_clips(clip_set):
    """Committed slot table rows: clip, wording, slot bytes, rough SSC seconds."""
    with FITS[clip_set].open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    rate = [int(r["encoded_bytes"])/(int(r["trimmed_frames"])/22050/float(r["speed"]))
            for r in rows if r["format"] == "02040102" and r["trimmed_frames"]]
    rate = sorted(rate)[len(rate)//2] if rate else 0
    text = locked_text(clip_set)
    for r in rows:
        clip, slot = int(r["clip"]), int(r["slot_bytes"])
        yield {"clip": clip, "en_nz": text[clip], "slot_bytes": slot,
               "approx_ssc_seconds": f"{slot/rate:.2f}" if rate else ""}


def extract_gid(image, out):
    """Find the GID through the image's own FAT32 (opened "rb") and copy it out."""
    import write_gid
    with image.open("rb") as f:
        read = write_gid.sector_reader(f)
        offset, size = write_gid.gid_extent(read, pinned=False, card_bytes=image.stat().st_size)
        data = read(offset, size)
    if out.exists():
        raise ValueError(f"{out} exists; choose a new path")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as f:
        f.write(data)
    return {"gid_offset": offset, "bytes": size, "sha256": sha(data),
            "is_pinned_stock": sha(data) == OUTER_SHA}


def export(clip_set, build_dir, out, credit):
    report = json.loads((build_dir/"build-report.json").read_text())
    if report.get("status") != "BUILT_HARDWARE_UNTESTED" or report.get("fits") != len(CLIP_SETS[clip_set]):
        raise ValueError("export needs a complete prepare_greeting.py build")
    with (build_dir/"fits.tsv").open() as f:
        fits = {int(r["clip"]): r for r in csv.DictReader(f, delimiter="\t")}
    if set(fits) != set(CLIP_SETS[clip_set]):
        raise ValueError("fit table does not match the clip set")
    out.mkdir(parents=True, exist_ok=False)
    (out/"clips").mkdir()
    (out/"previews").mkdir()
    clips = {}
    for i in CLIP_SETS[clip_set]:
        row = fits[i]
        if row["status"] != "FIT" or row["format"] not in FORMATS:
            raise ValueError(f"clip {i}: not a fitted PCM/SSC clip")
        audio = (build_dir/f"clip{i:04d}.bin").read_bytes()
        if len(audio) != int(row["encoded_bytes"]):
            raise ValueError(f"clip {i}: encoded size differs from fits.tsv")
        shutil.copyfile(build_dir/f"clip{i:04d}.bin", out/"clips"/f"clip{i:04d}.bin")
        shutil.copyfile(build_dir/f"clip{i:04d}.wav", out/"previews"/f"clip{i:04d}.wav")
        clips[str(i)] = {"en_nz": row["en_nz"], "format": row["format"],
                         "bytes": len(audio), "sha256": sha(audio),
                         "preview_sha256": sha((out/"previews"/f"clip{i:04d}.wav").read_bytes())}
    shutil.copyfile(build_dir/"fits.tsv", out/"fits.tsv")
    example = report.get("example_wav", "welcome-example.wav")
    if (build_dir/example).exists():
        shutil.copyfile(build_dir/example, out/example)
    manifest = {"pack_version": PACK_VERSION, "clip_set": clip_set,
                "stock_gid_sha256": OUTER_SHA, "base_gid_sha256": report.get("base_gid_sha256", OUTER_SHA),
                "build_sha256": report["build_sha256"], "bytes": report["bytes"],
                "voice_id": report.get("voice_id", ""), "rms_dbfs": report.get("rms_dbfs"),
                "peak_dbfs": report.get("peak_dbfs"), "credit": credit, "clips": clips}
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def load_pack(pack):
    manifest = json.loads((pack/"manifest.json").read_text())
    if manifest.get("pack_version") != PACK_VERSION or manifest.get("clip_set") not in CLIP_SETS:
        raise ValueError("unknown pack version or clip set")
    clip_set = manifest["clip_set"]
    if set(map(int, manifest["clips"])) != set(CLIP_SETS[clip_set]):
        raise ValueError("pack clips do not match the clip set")
    replacements = {}
    for key, c in manifest["clips"].items():
        audio = (pack/"clips"/f"clip{int(key):04d}.bin").read_bytes()
        if sha(audio) != c["sha256"] or len(audio) != c["bytes"] or c["format"] not in FORMATS:
            raise ValueError(f"clip {key}: pack file hash/size/format mismatch")
        replacements[int(key)] = (bytes.fromhex(c["format"]), audio)
    return manifest, replacements


def build(pack, stock_path, base_path, out):
    manifest, replacements = load_pack(pack)
    stock = stock_path.read_bytes()
    if sha(stock) != OUTER_SHA:
        raise ValueError("your SJP00300.GID is not the stock file these packs were made for; stop")
    base = base_path.read_bytes() if base_path else stock
    if sha(base) != manifest["base_gid_sha256"]:
        raise ValueError(f"{manifest['clip_set']} pack needs base {manifest['base_gid_sha256'][:12]}… "
                         "(build the greeting pack first and pass it with --base)")
    result = patch(base, replacements, manifest["clip_set"], stock)
    if sha(result) != manifest["build_sha256"]:
        raise ValueError("built GID does not match the pack's pinned build hash")
    out.mkdir(parents=True, exist_ok=False)
    with (out/"SJP00300.GID").open("xb") as f:
        f.write(result)
    report = {"status": "BUILT_FROM_PACK_HARDWARE_UNTESTED", "clip_set": manifest["clip_set"],
              "build_sha256": sha(result), "base_gid_sha256": sha(base), "bytes": len(result),
              "pack_manifest_sha256": sha((pack/"manifest.json").read_bytes())}
    (out/"build-report.json").write_text(json.dumps(report, indent=2)+"\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list", help="clip IDs, wording and slot sizes (TSV)")
    ls.add_argument("--clip-set", choices=tuple(CLIP_SETS), default="greeting")
    eg = sub.add_parser("extract-gid", help="copy the GID out of a card image (read-only)")
    eg.add_argument("--image", type=Path, required=True, help="your full-card backup image")
    eg.add_argument("--output", type=Path, required=True, help="new file, e.g. $NISSAN_ROOT/work/language-speech/SJP00300.GID")
    ex = sub.add_parser("export", help="maintainers: build directory -> pack")
    ex.add_argument("--clip-set", choices=tuple(CLIP_SETS), required=True)
    ex.add_argument("--build-dir", type=Path, required=True)
    ex.add_argument("--output", type=Path, required=True, help="new directory outside the repo")
    ex.add_argument("--credit", default="", help="voice/TTS credit line stored in the manifest")
    bd = sub.add_parser("build", help="owners: stock GID + pack -> SJP00300.GID")
    bd.add_argument("--pack", type=Path, required=True)
    bd.add_argument("--stock-gid", type=Path, required=True, help="SPEECH/JP/GID/SJP00300.GID from your card backup")
    bd.add_argument("--base", type=Path, help="EV pack only: the GID built from the greeting pack")
    bd.add_argument("--output", type=Path, required=True, help="new directory under $NISSAN_ROOT/work")
    args = ap.parse_args()
    try:
        if args.command == "list":
            w = csv.DictWriter(sys.stdout, fieldnames=["clip", "en_nz", "slot_bytes", "approx_ssc_seconds"],
                               delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(list_clips(args.clip_set))
            return
        if args.command == "extract-gid":
            out = args.output.expanduser().resolve()
            if out.is_relative_to(REPO):
                raise ValueError("the GID is Nissan/Clarion audio: keep it outside the repo")
            report = extract_gid(args.image.expanduser().resolve(), out)
            print(json.dumps(report, indent=2))
            if not report["is_pinned_stock"]:
                ap.exit(1, "This GID is not the stock file the packs and tools were made for. Stop here.\n")
            return
        if args.command == "export":
            out = args.output.expanduser().resolve()
            if out.is_relative_to(REPO):
                raise ValueError("packs hold audio: write them outside the repo")
            m = export(args.clip_set, args.build_dir.expanduser().resolve(), out, args.credit)
            print(json.dumps({k: v for k, v in m.items() if k != "clips"}, indent=2))
            return
        pack = args.pack.expanduser().resolve()
        clip_set = json.loads((pack/"manifest.json").read_text()).get("clip_set", "greeting")
        out = output_path(args.output, clip_set if clip_set in CLIP_SETS else "greeting")
        print(json.dumps(build(pack, args.stock_gid.expanduser(),
                               args.base.expanduser() if args.base else None, out), indent=2))
    except (OSError, ValueError, KeyError) as e:
        ap.exit(1, f"Clip pack refused: {e}\n")


if __name__ == "__main__":
    main()
