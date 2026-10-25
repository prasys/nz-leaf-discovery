#!/usr/bin/env python3
"""setter-strings-scan.py - read-only scan for ASCII and UTF-16LE strings."""
import re, struct, sys
path = sys.argv[1]
pat = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
data = open(path, "rb").read()
# ASCII runs
for m in re.finditer(rb"[\x20-\x7e]{4,120}", data):
    s = m.group().decode()
    if pat is None or pat.search(s):
        print("A 0x%06x %r" % (m.start(), s))
# UTF-16LE runs
for m in re.finditer(rb"(?:[\x20-\x7e]\x00){4,120}", data):
    s = m.group().decode("utf-16-le")
    if pat is None or pat.search(s):
        print("W 0x%06x %r" % (m.start(), s))
