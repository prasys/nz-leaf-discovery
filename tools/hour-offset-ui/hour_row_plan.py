#!/usr/bin/env python3
"""Plan (never write) the skin-only "minute row -> hour row" edit (issue #29).

The Clock settings screen's offset row calls NaviSetCC GetExpOffsetMinSetting (DISPID
0x6B) and SetExpOffsetMinSetting (0x6C) and limits the value to -59..+59.  The stock
NaviSetCC hour members 0x69/0x6A have the same shape (PROPERTYGET/PROPERTYPUT, one
LONG).  This tool checks the 11 baseline bytes, applies the edits to an in-memory
copy and re-decodes the touched records.  It opens the skin read-only and writes no
file.  See docs/findings/12-hour-offset-ui.md.

Usage: hour_row_plan.py [--change hour|dst] [skin]
  dst repoints the Clock screen's time-indication toggle at Get/SetExpAutoDstSetting.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skn_script  # noqa: E402

KNOWN = {
    "ea5b5a34d912c3344e3157e453025734474d104046434537775f96c85ae06f4d": "LeafHacker stock skin",
    "6a54198aa04e6c104c6dd5bdc86005f495dca979bda95549ac687da0821ebbb7": "nz-en v1 in-place build",
    "ec1138c812d5bc111ad30d2e8937b0657be1f8092f832cefb67a83916bfa192b": "nz-en v1 + hour row (car-tested 2026-10-25)",
}

# (file offset, before, after, record, meaning)
EDITS = [
    (0x466C9B, 0x6B, 0x69, 70029, "screen init: read GetExpOffsetHourSetting instead of minutes"),
    (0x467024, 0x6C, 0x6A, 70035, "plus (event 3): SetExpOffsetHourSetting"),
    (0x46707A, 0x6C, 0x6A, 70036, "plus (event 0xA, repeat): SetExpOffsetHourSetting"),
    (0x4670D0, 0x6C, 0x6A, 70037, "minus (event 3): SetExpOffsetHourSetting"),
    (0x467126, 0x6C, 0x6A, 70038, "minus (event 0xA, repeat): SetExpOffsetHourSetting"),
    (0x466E86, 0x3B, 0x0C, 70032, "lower bound: value <= -59 -> <= -12 disables minus"),
    (0x466EAA, 0x3B, 0x0C, 70032, "upper bound: 59 <= value -> 12 <= value disables plus"),
    (0x466ECE, 0x3A, 0x0B, 70032, "both enabled: -58 -> -11"),
    (0x466ED6, 0x3A, 0x0B, 70032, "both enabled: 58 -> 11"),
    (0x0054B4, 0x21, 0x20, 255, "label refresh handler: NaviSetCC event 0x21 (minute) -> 0x20 (hour)"),
    (0x0054EC, 0x20, 0x21, 256, "generic refresh handler: event 0x20 (hour) -> 0x21 (minute)"),
]

EXPECT_AFTER = {
    70029: "[obj:0x111CB call(0,0)] := [obj:0x89 #0x69 call(0,0)]",
    70032: "if (arg:1 int:12 op3 op12)",
    70035: "[obj:0x89 #0x6A call(0,0)] := [obj:0x111CB call(0,0)]",
    70036: "[obj:0x89 #0x6A call(0,0)] := [obj:0x111CB call(0,0)]",
    70037: "[obj:0x89 #0x6A call(0,0)] := [obj:0x111CB call(0,0)]",
    70038: "[obj:0x89 #0x6A call(0,0)] := [obj:0x111CB call(0,0)]",
}

SINKS = ((255, 0x20), (256, 0x21))

# The Clock screen's first toggle (time indication, 0x65/0x66, event 0x1E) repointed at
# Get/SetExpAutoDstSetting (0x6D/0x6E, event 0x22): on = OBJ_Time_writeDst(+1 h).
DST_EDITS = [
    (0x466C79, 0x65, 0x6D, 70029, "screen init: toggle state from GetExpAutoDstSetting"),
    (0x466F50, 0x66, 0x6E, 70033, "toggle off branch: SetExpAutoDstSetting(0)"),
    (0x466F60, 0x66, 0x6E, 70033, "toggle on branch: SetExpAutoDstSetting(1)"),
    (0x005444, 0x1E, 0x22, 253, "toggle display sink: event 0x1E (time indication) -> 0x22 (AutoDst)"),
    (0x005518, 0x22, 0x1E, 257, "empty sink: event 0x22 -> 0x1E"),
]
DST_EXPECT = {
    70029: "obj:0x111D0 obj:0x89 #0x6D call(0,0) call(3,1)",
    70033: "[obj:0x89 #0x6E call(0,0)] := [int:1]",
}
DST_SINKS = ((253, 0x22), (257, 0x1E))

CHANGES = {"hour": (EDITS, EXPECT_AFTER, SINKS), "dst": (DST_EDITS, DST_EXPECT, DST_SINKS)}


def decode(d, index):
    recs, _ = skn_script.skn_format.records(d)
    o, s, fl, t = recs[index]
    ids, event, _ = skn_script.header(d, o, fl)
    lines = []
    skn_script.parse(d, o, fl, lines)
    return ids, event, lines


def plan(d, change="hour"):
    """Return (patched copy, problems).  Problems are baseline or decode mismatches."""
    edits, expect, sinks = CHANGES[change]
    if len(d) <= max(e[0] for e in edits):
        return d, ["file too short (%d bytes) to be substance.skn" % len(d)]
    problems = []
    for off, before, after, rec, _ in edits:
        if d[off] != before:
            problems.append("0x%06X: expected 0x%02X, found 0x%02X" % (off, before, d[off]))
    patched = bytearray(d)
    for off, before, after, rec, _ in edits:
        patched[off] = after
    patched = bytes(patched)
    if problems:
        return patched, problems
    for rec, needle in expect.items():
        _, _, lines = decode(patched, rec)
        if not any(needle in line for line in lines):
            problems.append("rec %d: decoded text lacks %r" % (rec, needle))
    for rec, event in sinks:
        ids, ev, _ = decode(patched, rec)
        if ids != [0x89] or ev != event:
            problems.append("rec %d: sink is %s/%s, expected [0x89]/0x%X" % (rec, ids, ev, event))
    return patched, problems


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--change", choices=sorted(CHANGES), default="hour")
    parser.add_argument("skin", nargs="?", default=skn_script.DEFAULT_SKIN)
    args = parser.parse_args(argv)
    change, path = args.change, args.skin
    with open(path, "rb") as source:
        d = source.read()
    sha = hashlib.sha256(d).hexdigest()
    print("skin   %s\nsha256 %s (%s)" % (path, sha, KNOWN.get(sha, "unknown build")))
    patched, problems = plan(d, change)
    edits, expect, sinks = CHANGES[change]
    print("change %s" % change)
    print("\n%-9s %-6s %-6s %-6s %s" % ("offset", "before", "after", "record", "meaning"))
    for off, before, after, rec, why in edits:
        print("0x%06X  0x%02X   0x%02X   %-6d %s" % (off, before, after, rec, why))
    if problems:
        print("\nREFUSED: baseline/decode check failed")
        for p in problems:
            print("  " + p)
        return 1
    print("\nbaseline matches; in-memory result decodes as intended (nothing written):")
    for rec in sorted({r for r, _ in sinks} | set(expect)):
        ids, ev, lines = decode(patched, rec)
        print("  rec %d senders=%s event=%s" % (rec, [hex(x) for x in ids], "-" if ev is None else hex(ev)))
        for line in lines[:4]:
            print("    " + line.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
