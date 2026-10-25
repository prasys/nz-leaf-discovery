#!/usr/bin/env python3
"""Build the hour-row skin: hour_row_plan.EDITS applied to a pinned skin (issue #29).

Reads the input skin read-only, refuses unless its SHA256 is one of hour_row_plan.KNOWN
and every baseline/decode check passes, and writes <out>/substance.skn plus
<out>/hour-row-report.json into a new directory under $NISSAN_ROOT/work.  It never
touches a card; tools/translation/write_skin.py does that, run by the owner.

Usage: build_hour_row.py --skin ~/nissan/work/translation/build/substance.skn \
           --out ~/nissan/work/hour-offset-ui/build-v1
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hour_row_plan  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skin", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--change", choices=sorted(hour_row_plan.CHANGES), default="hour")
    args = parser.parse_args(argv)
    work = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser().resolve() / "work"
    out = args.out.expanduser().resolve()
    if out == work or not out.is_relative_to(work):
        parser.error("Output must be a new child of NISSAN_ROOT/work")
    d = args.skin.expanduser().read_bytes()
    src = hashlib.sha256(d).hexdigest()
    if src not in hour_row_plan.KNOWN:
        parser.exit(1, "input sha256 %s is not a pinned skin\n" % src)
    patched, problems = hour_row_plan.plan(d, args.change)
    edits = hour_row_plan.CHANGES[args.change][0]
    if problems:
        parser.exit(1, "refused:\n  " + "\n  ".join(problems) + "\n")
    out.mkdir(parents=True, exist_ok=False)
    target = out / "substance.skn"
    target.write_bytes(patched)
    target.chmod(0o444)
    report = {
        "change": args.change, "source": str(args.skin), "source_sha256": src,
        "source_label": hour_row_plan.KNOWN[src],
        "build_sha256": hashlib.sha256(patched).hexdigest(), "bytes": len(patched),
        "edits": [{"offset": "0x%06X" % o, "before": "0x%02X" % b, "after": "0x%02X" % a,
                   "record": r, "meaning": m} for o, b, a, r, m in edits],
    }
    (out / "hour-row-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("source_sha256", "build_sha256", "bytes")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
