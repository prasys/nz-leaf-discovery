#!/usr/bin/env python3 -I
"""Dump a Windows CE (6/7) registry hive file (boot.hv / default.hv / user.hv, signature 'EKIM').

Usage:
    python3 -I tools/ce-extract/cehive.py <hive> [--grep REGEX] [--path PREFIX]

Record layout, worked out from default.hv (4-byte aligned, little-endian) [likely]:
    u32 tag   high byte = record type, low 24 bits = size (see below)
    0xB0 root:  u32 0, u32 0, then 4 links = HKCR, HKCU, HKLM, HKU first subkeys
    0xC0 key:   u32 0, u32 handle, u32 next-sibling, u32 first-subkey, u32 first-value,
                u16 namelen(chars), u16 0, name UTF-16             size = 16 + 2*namelen (+-alignment)
    0xD0 value: u32 0, u32 handle, u32 next-value, u16 type, u16 datalen(bytes),
                u16 namelen(chars), name UTF-16, data              size = 14 + 2*namelen + datalen (+-alignment)
Links are 0x20000000 | handle (0 = end of list). Lists are prepended, so siblings
come out in reverse creation order; this tool sorts them by name.
Records are found by scanning (the size check rejects false hits), then tied
together by handle.
"""

import re
import struct
import sys

REG_TYPES = {0: "NONE", 1: "SZ", 2: "EXPAND_SZ", 3: "BINARY", 4: "DWORD", 5: "DWORD_BE",
             6: "LINK", 7: "MULTI_SZ", 11: "QWORD", 21: "MUI_SZ"}
LINK = 0x20000000


def _name(d, o, n):
    raw = d[o:o + 2 * n]
    if len(raw) != 2 * n:
        return None
    try:
        s = raw.decode("utf-16le")
    except UnicodeDecodeError:
        return None
    if any(ord(c) < 0x20 for c in s):
        return None
    return s


ROOT_NAMES = ("HKEY_CLASSES_ROOT", "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "HKEY_USERS")


def roots(d):
    """[(root name, first-subkey link)] from the 0xB0 root record."""
    out = []
    for o in range(0, len(d) - 32, 4):
        if d[o + 3] == 0xB0 and d[o + 2] == 0 and d[o + 4:o + 12] == bytes(8):
            links = struct.unpack_from("<4I", d, o + 12)
            out += [(ROOT_NAMES[k], l) for k, l in enumerate(links) if l & LINK]
    return out


def parse(d):
    keys, vals = {}, {}
    for o in range(0, len(d) - 32, 4):
        tag = d[o + 3]
        if tag not in (0xC0, 0xD0) or d[o + 2] != 0:
            continue
        z, h, nxt = struct.unpack_from("<III", d, o + 4)
        if z != 0 or not 0 < h < 0x1000000:
            continue
        if tag == 0xC0:
            sub, val = struct.unpack_from("<II", d, o + 16)
            nl, pad = struct.unpack_from("<HH", d, o + 24)
            if pad or not 0 < nl < 260 or abs((struct.unpack_from("<I", d, o)[0] & 0xFFFFFF) - (16 + 2 * nl)) > 3:
                continue
            nm = _name(d, o + 28, nl)
            if nm is None:
                continue
            keys.setdefault(h, (nm, nxt, sub, val, o))
        else:
            typ, dl, nl = struct.unpack_from("<HHH", d, o + 16)
            if typ not in REG_TYPES or nl > 260 or abs((struct.unpack_from("<I", d, o)[0] & 0xFFFFFF) - (14 + 2 * nl + dl)) > 3:
                continue
            nm = _name(d, o + 22, nl) if nl else ""
            if nm is None:
                continue
            p = o + 22 + 2 * nl
            vals.setdefault(h, (nm, nxt, typ, d[p:p + dl], o))
    return keys, vals


def chain(first, table, limit=100000):
    out, h = [], first
    while h & LINK and len(out) < limit:
        h &= ~LINK
        if h not in table:
            break
        out.append(h)
        h = table[h][1]
    return out


def fmt(typ, data):
    if typ in (1, 2, 6, 21):
        return repr(data.decode("utf-16le", "replace").rstrip("\0"))
    if typ == 7:
        return repr([s for s in data.decode("utf-16le", "replace").split("\0") if s])
    if typ == 4 and len(data) == 4:
        v = struct.unpack("<I", data)[0]
        return "%#x (%d)" % (v, v)
    return data.hex(" ")


def tzi(data):
    """Decode a 44-byte TIME_ZONE_INFORMATION-style REG_BINARY (Bias, StdBias, DltBias, 2 SYSTEMTIMEs)."""
    if len(data) != 44:
        return ""
    b, sb, db = struct.unpack_from("<iii", data)
    st = struct.unpack_from("<8H", data, 12)
    dt = struct.unpack_from("<8H", data, 28)
    return "  [Bias=%d -> UTC%+.2g, StdBias=%d, DltBias=%d, std=%s, dst=%s]" % (
        b, -b / 60, sb, db, st[:5], dt[:5])


def walk_list(keys, vals, first, path, out):
    for kh in sorted(chain(first, keys), key=lambda x: keys[x][0].lower()):
        walk(keys, vals, kh, path, out)


def walk(keys, vals, h, path, out):
    nm, nxt, sub, val, off = keys[h]
    p = path + "\\" + nm if path else nm
    out.append(("K", p, None, None, off))
    for vh in sorted(chain(val, vals), key=lambda x: vals[x][0].lower()):
        vn, _, typ, data, voff = vals[vh]
        out.append(("V", p, vn, (typ, data), voff))
    walk_list(keys, vals, sub, p, out)


def main(argv):
    grep = path = None
    if "--grep" in argv:
        i = argv.index("--grep")
        grep = re.compile(argv[i + 1], re.I)
        del argv[i:i + 2]
    if "--path" in argv:
        i = argv.index("--path")
        path = argv[i + 1].lower()
        del argv[i:i + 2]
    if len(argv) < 2:
        print(__doc__)
        return 2
    d = open(argv[1], "rb").read()
    if d[8:12] != b"EKIM":
        print("warning: no EKIM signature at +8", file=sys.stderr)
    keys, vals = parse(d)
    rts = roots(d)
    out = []
    for rname, first in rts:
        out.append(("K", rname, None, None, 0))
        walk_list(keys, vals, first, rname, out)
    seen = sum(1 for x in out if x[0] == "K") - len(rts)
    print("# %s: %d keys (%d reachable), %d values, roots=%s" % (
        argv[1], len(keys), seen, len(vals), [r for r, _ in rts]))
    for kind, p, vn, tv, off in out:
        if path and not p.lower().startswith(path):
            continue
        if kind == "K":
            line = "[%s]" % p
        else:
            typ, data = tv
            line = "  %s = %s:%s" % (vn or "@", REG_TYPES.get(typ, typ), fmt(typ, data))
            if typ == 3 and vn in ("TZI",):
                line += tzi(data)
        if grep and not grep.search(p + " " + line):
            continue
        print(line if not grep else "%s  %s" % (p, line.strip()) if kind == "V" else line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
