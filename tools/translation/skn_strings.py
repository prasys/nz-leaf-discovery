#!/usr/bin/env python3
"""Inspect the SkinChange skin file (substance.skn) on hidden p2 (issue #32). Read-only.

Usage: python3 -I tools/translation/skn_strings.py [--src PATH] CMD
  info              trailer, record types, PNG summary, string-pair counts
  strings           TSV of every length-prefixed string: offset, kind, text
  pairs             TSV of the 0x802 EN/JP text records: offset, EN, JP
  untranslated      Japanese strings still in the skin, with the nearest
                    preceding identifier and English string as context
  pngs --out DIR    copy the embedded PNGs to DIR (must be outside the repo)

PATH is the card image ($NISSAN_IMG; the file is read at SKN_SECTOR) or a
carve of the file, e.g. ~/nissan/work/translation/substance.skn. The skin
is vendor data and holds no personal data.

Formats (see docs/findings/11-skin-pipeline.md):
  trailer (last 36 bytes): u32 0x04020004, "470-6253-48\\0", u32 (unknown,
      not crc32/adler32/sum8/sum16/sum32), "SKINSK18NNNI.183"
  string:       u32 nbytes, UTF-16LE text (nbytes), u16 NUL, padded to 4.
      Most UI text is stored this way, English only, in string tables
      beside the layout identifiers (lay_*, SK_*, POP_*, ...).
  text record:  u32 size, u32 0x802, u32 0, u32 1, u16 3, u16 0x0C,
      then 3 variant cells: u16 vtype, align 4, value (vtype 8: u32 nbytes,
      UTF-16LE text, u16 NUL). Cell 0 is empty, 1 English, 2 Japanese
      (docs/findings/11-skin-pipeline.md §1.3).
"""
import argparse
import collections
import os
import re
import struct
import sys

SEC = 512
SKN_SECTOR = 29925953       # p2 cluster run of /SkinChange/002/substance.skn
SKN_SIZE = 20025376         # exFAT directory entry size
TRAILER_LEN = 36
TRAILER_TAG = 0x04020004
TEXT_TYPE = 0x802
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
KANA = re.compile("[\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")
IDENT = re.compile(r"[A-Za-z0-9]+_[A-Za-z0-9_]+")
PUNCT = (0x0A, 0xB0, 0x2019, 0x2026)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_IMG = os.environ.get(
    "NISSAN_IMG", os.path.expanduser("~/nissan/sdcard/nissan-sd-485-1972-00.img"))


def load(path):
    with open(path, "rb") as f:
        if os.path.getsize(path) == SKN_SIZE:
            return f.read()
        f.seek(SKN_SECTOR * SEC)
        b = f.read(SKN_SIZE)
    if len(b) != SKN_SIZE:
        raise SystemExit("short read from %s" % path)
    return b


def trailer(d):
    t = d[-TRAILER_LEN:]
    tag, = struct.unpack_from("<I", t, 0)
    part = t[4:16].split(b"\0")[0].decode("ascii", "replace")
    val, = struct.unpack_from("<I", t, 16)
    name = t[20:].split(b"\0")[0].decode("ascii", "replace")
    return tag, part, val, name


def printable(s):
    return all(0x20 <= ord(c) < 0x7F or ord(c) in PUNCT or 0x3000 <= ord(c) <= 0x303F
               or KANA.match(c) for c in s)


def kind(s):
    if KANA.search(s):
        return "jp"
    return "id" if IDENT.fullmatch(s) else "en"


def strings(d):
    """Yield (offset, kind, text) for every length-prefixed UTF-16LE string."""
    for p in range(0, len(d) - 8, 4):
        n, = struct.unpack_from("<I", d, p)
        if not 4 <= n <= 1024 or n % 2 or d[p + 4 + n:p + 6 + n] != b"\0\0":
            continue
        s = d[p + 4:p + 4 + n].decode("utf-16le", "replace")
        if "\0" not in s and printable(s):
            yield p, kind(s), s


def text_records(d):
    """Yield (offset, [strings]) for every 0x802 text record."""
    pat = re.compile(re.escape(struct.pack("<IIIHH", TEXT_TYPE, 0, 1, 3, 0x0C)))
    for m in pat.finditer(d):
        off = m.start() - 4
        if off < 0 or off % 4:
            continue
        size, = struct.unpack_from("<I", d, off)
        if not 0x14 < size < 0x10000:
            continue
        end, p, items = off + size, off + 0x14, []
        for _ in range(3):          # variant cells: u16 vtype, align 4, value
            if p + 2 > end:
                break
            vt, = struct.unpack_from("<H", d, p)
            p += 2
            if vt & 0xFF == 0:
                continue
            p = (p + 3) & ~3
            if vt & 0xFF != 8:
                p += 4
                continue
            n, = struct.unpack_from("<I", d, p)
            if p + 4 + n > end or n % 2:
                break
            items.append(d[p + 4:p + 4 + n].decode("utf-16le", "replace"))
            p += 4 + n + 2
        if items:
            yield off, items


def pngs(d):
    for m in re.finditer(re.escape(PNG_MAGIC), d):
        e = d.find(b"IEND", m.start())
        if e < 0:
            continue
        w, h = struct.unpack_from(">II", d, m.start() + 16)
        yield m.start(), w, h, d[m.start():e + 8]


def cmd_info(d):
    tag, part, val, name = trailer(d)
    print("size        %d (0x%X)" % (len(d), len(d)))
    print("head        %s" % d[:16].hex(" "))
    print("trailer     tag 0x%08X ok=%s part %s value 0x%08X name %s"
          % (tag, tag == TRAILER_TAG, part, val, name))
    ss = list(strings(d))
    by = collections.defaultdict(list)
    for off, k, s in ss:
        by[k].append((off, s))
    print("strings     %d in 0x%X-0x%X" % (len(ss), ss[0][0], ss[-1][0]))
    for k, label in (("id", "identifiers"), ("en", "English"), ("jp", "Japanese")):
        print("  %-11s %6d (%d unique)" % (label, len(by[k]), len({s for _, s in by[k]})))
    recs = list(text_records(d))
    print("0x802 recs  %d (items per record %s)"
          % (len(recs), dict(collections.Counter(len(i) for _, i in recs))))
    ps = list(pngs(d))
    dims = collections.Counter((w, h) for _, w, h, _ in ps)
    print("pngs        %d, %d bytes, top sizes %s"
          % (len(ps), sum(len(b) for *_, b in ps), dims.most_common(8)))


def clean(s):
    return s.replace("\t", " ").replace("\n", "\\n").replace("\r", "")


def cmd_strings(d):
    print("offset\tkind\ttext")
    for off, k, s in strings(d):
        print("0x%X\t%s\t%s" % (off, k, clean(s)))


def cmd_pairs(d):
    print("offset\ten\tjp")
    for off, items in text_records(d):
        jp = items[1] if len(items) > 1 else ""
        print("0x%X\t%s\t%s" % (off, clean(items[0]), clean(jp)))


def cmd_untranslated(d):
    print("offset\tjp\tlast_id\tlast_en")
    last = {"id": "", "en": ""}
    for off, k, s in strings(d):
        if k == "jp":
            print("0x%X\t%s\t%s\t%s" % (off, clean(s), last["id"], clean(last["en"])))
        else:
            last[k] = s


def cmd_pngs(d, out):
    out = os.path.abspath(os.path.expanduser(out))
    if out == REPO or out.startswith(REPO + os.sep):
        raise SystemExit("refusing to write binaries inside the repo; use ~/nissan/work/...")
    os.makedirs(out, exist_ok=True)
    n = 0
    for off, w, h, b in pngs(d):
        with open(os.path.join(out, "%07X_%dx%d.png" % (off, w, h)), "wb") as f:
            f.write(b)
        n += 1
    print("wrote %d PNGs to %s" % (n, out))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=DEFAULT_IMG)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("strings")
    sub.add_parser("pairs")
    sub.add_parser("untranslated")
    p = sub.add_parser("pngs")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    d = load(a.src)
    if a.cmd == "info":
        cmd_info(d)
    elif a.cmd == "strings":
        cmd_strings(d)
    elif a.cmd == "pairs":
        cmd_pairs(d)
    elif a.cmd == "untranslated":
        cmd_untranslated(d)
    else:
        cmd_pngs(d, a.out)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
