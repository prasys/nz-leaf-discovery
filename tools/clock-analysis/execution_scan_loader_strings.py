#!/usr/bin/env python3 -I
"""execution-: UTF-16LE string scan of extracted CE modules for loader/
loader-check markers (MTLD/MTCP/SUM/NKOK/LoadNk/_.nb0/G214/G314/part numbers).
Read-only; no code executed."""
import re
import os
from pathlib import Path

root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser() / "work/ce-extract"
SLOTS = ["G214JLNI.066-HMI", "G314JLNI.066", "PM13XKNI.039", "UP14XNNI.139"]
WORDS = ["MTLD", "MTCP", "SUM4", "NKOK", "LoadNkFromStorage", "CLoadImage",
         "G214JLNI", "G314JLNI", "470-5120-12", "470-4651-16", "470-4650-14",
         "chkSum", "chkSumDat32", "LoadShBin", "ROMIMG", "PRGUPDATE"]
PATTERNS = [(w, w.encode("utf-16-le")) for w in WORDS]


def scan(path):
    data = path.read_bytes()
    out = {}
    for w, pat in PATTERNS:
        n = len(re.findall(re.escape(pat), data))
        if n:
            out[w] = n
    return out


def main():
    for slot in SLOTS:
        mdir = root / slot / "modules"
        if not mdir.is_dir():
            continue
        print(f"== {slot} ==")
        for mod in sorted(mdir.iterdir()):
            try:
                out = scan(mod)
            except OSError:
                continue
            if out:
                print(f"  {mod.name}: " + ", ".join(f"{k}:{v}" for k, v in sorted(out.items())))


if __name__ == "__main__":
    main()
