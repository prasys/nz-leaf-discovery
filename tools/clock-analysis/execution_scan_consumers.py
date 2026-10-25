#!/usr/bin/env python3 -I
"""execution-: scan extracted CE modules (read-only bytes) for import name
strings of the OBJ_Time_* clock exports, to identify consumers of
OBJ_Time_getTotalOffset vs OBJ_Time_getLocalTime/OBJ_Time_readLocalTime.
Also prints any MTLD/MTCP/NK-loader strings found per slot dir.
Never executes extracted code."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root -> n/a; use env below
import os
root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser() / "work/ce-extract"
OUT = ROOT if False else None

SLOTS = ["G214JLNI.066-HMI", "G314JLNI.066", "PM13XKNI.039", "UP14XNNI.139"]
PATTERNS = [
    b"OBJ_Time_getTotalOffset", b"OBJ_Time_getLocalTime", b"OBJ_Time_readLocalTime",
    b"OBJ_Time_initialize", b"OBJ_Time_writeGMT", b"OBJ_Time_writeZone",
    b"MTLD", b"MTCP", b"LoadNkFromStorage", b"NK.bin", b".nb0",
]


def scan(path: Path):
    data = path.read_bytes()
    hits = []
    for pat in PATTERNS:
        for m in re.finditer(re.escape(pat), data):
            hits.append((pat.decode(), m.start()))
    # dedupe consecutive repeats: keep first and count
    summary = {}
    for name, pos in hits:
        summary.setdefault(name, []).append(pos)
    return summary


def main():
    for slot in SLOTS:
        mdir = root / slot / "modules"
        if not mdir.is_dir():
            continue
        print(f"== {slot} ==")
        for mod in sorted(mdir.iterdir()):
            try:
                summary = scan(mod)
            except OSError:
                continue
            clock = {k: v for k, v in summary.items() if k.startswith("OBJ_Time")}
            loader = {k: v for k, v in summary.items() if not k.startswith("OBJ_Time")}
            if clock or loader:
                parts = [f"{k}:{len(v)}" for k, v in sorted(clock.items())]
                parts += [f"{k}:{len(v)}" for k, v in sorted(loader.items())]
                print(f"  {mod.name}: " + ", ".join(parts))


if __name__ == "__main__":
    main()
