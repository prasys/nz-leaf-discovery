#!/usr/bin/env python3
"""Record-level parser and serialiser for substance.skn. Pure functions on bytes.

Layout (docs/findings/11-skin-pipeline.md):
  0x000000  section 1: u32 0x04020001, head (0x40 bytes), then a chain of records
            u32 (flags << 24 | size), u32 type, payload; size includes the 8-byte
            header and is a multiple of 4. 78,668 records to 0x51B9F0.
  0x51B9F0  section 2: u32 0x04020002, u32 count (279), u32 ?, count x u32
            (values < 78,668: record indices, not offsets), then zero fill.
  0x520000  section 3: u32 0x04020003, u32 0xDF9000, ...: the PNGs.
  end-36    trailer: u32 0x04020004, part no, u32 value, name.

Type 0x802 records (and 0x8802, the same with bit 15 set) are typed tables:
  u32 0, u16 ndims, u16 has_header, u16 dims[ndims],
  [has_header: per column a string + u16 type, each aligned to 4]
  u8 elem_type, u8 flag, align 4, then prod(dims) elements.
Element encodings (all aligned to 4 except where noted):
  1  u32
  8  string: u32 nbytes, UTF-16LE text, u16 NUL, align 4
  0x0C variant: u16 vtype (low byte = type), align 4, then a value of that type
       (0 = null, nothing; 1 = u32; 8 = string without its own trailing align)
       The record ends aligned to 4.
Other element types and header tables are kept as opaque bytes.

Text-element records (types 0x2A2001, 0x2A2004, 0x2AA001, 0x2AA004) hold one
string: u32 nbytes, UTF-16LE, u16 NUL, align 4, filling the record exactly.
They carry layout default text (placeholders like "88.8", but also messages).
"""
import struct

SEC1_TAG = 0x04020001
SEC2_TAG = 0x04020002
SEC3_TAG = 0x04020003
TABLE = 0x802
TEXT_TYPES = {0x2A2001, 0x2A2004, 0x2AA001, 0x2AA004}
STR, U32, VAR = 8, 1, 0x0C


def align4(n):
    return (n + 3) & ~3


def records(d, start=0x40):
    """Return [(offset, size, flags, type)] for section 1 and the section-2 offset."""
    out, p = [], start
    while True:
        h, t = struct.unpack_from("<II", d, p)
        if h == SEC2_TAG:
            return out, p
        size = h & 0xFFFFFF
        if size < 8 or size % 4 or p + size > len(d):
            raise ValueError("bad record at 0x%X (h=0x%08X)" % (p, h))
        out.append((p, size, h >> 24, t))
        p += size


class Table:
    """A parsed 0x802 table with string cells. Opaque bytes are kept as-is."""

    def __init__(self, d, off, size):
        self.off, self.size = off, size
        self.head = d[off:off + 8]
        z, nd, hdr = struct.unpack_from("<IHH", d, off + 8)
        if z or hdr or not 1 <= nd <= 4:
            raise ValueError("unsupported table")
        dims = struct.unpack_from("<%dH" % nd, d, off + 16)
        q = off + 16 + 2 * nd
        self.etype = d[q]
        q = align4(q + 2)
        self.pre = d[off + 8:q]
        n = 1
        for x in dims:
            n *= x
        self.cells = []      # (vtype or None, value); value is str for strings, bytes otherwise
        end = off + size
        if self.etype == STR:
            for _ in range(n):
                s, q = self._str(d, q)
                q = align4(q)
                self.cells.append((None, s))
        elif self.etype == VAR:
            for _ in range(n):
                vt, = struct.unpack_from("<H", d, q)
                q += 2
                if vt & 0xFF == 0:
                    self.cells.append((vt, b""))
                    continue
                q = align4(q)
                if vt & 0xFF == STR:
                    s, q = self._str(d, q)
                elif vt & 0xFF == U32:
                    s, q = d[q:q + 4], q + 4
                else:
                    raise ValueError("variant type 0x%X" % vt)
                self.cells.append((vt, s))
            q = align4(q)
        else:
            raise ValueError("element type 0x%X" % self.etype)
        if q != end:
            raise ValueError("table 0x%X parsed to 0x%X, record ends 0x%X" % (off, q, end))

    @staticmethod
    def _str(d, q):
        n, = struct.unpack_from("<I", d, q)
        if n % 2 or d[q + 4 + n:q + 6 + n] != b"\0\0":
            raise ValueError("bad string at 0x%X" % q)
        return d[q + 4:q + 4 + n].decode("utf-16le"), q + 6 + n

    def string_cells(self):
        """Yield (cell index, file offset of the u32 length, text) for each string cell."""
        q = self.off + len(self.head) + len(self.pre)
        for i, (vt, v) in enumerate(self.cells):
            if self.etype == STR:
                yield i, q, v
                q = align4(q + 6 + len(v.encode("utf-16le")))
                continue
            q += 2
            if vt & 0xFF == 0:
                continue
            q = align4(q)
            if vt & 0xFF == STR:
                yield i, q, v
                q += 6 + len(v.encode("utf-16le"))
            else:
                q += 4

    def serialise(self):
        out = bytearray(self.pre)
        for vt, v in self.cells:
            if self.etype == STR:
                b = v.encode("utf-16le")
                out += struct.pack("<I", len(b)) + b + b"\0\0"
                out += b"\0" * (align4(len(out)) - len(out))
                continue
            out += struct.pack("<H", vt)
            if vt & 0xFF == 0:
                continue
            out += b"\0" * (align4(len(out)) - len(out))
            if vt & 0xFF == STR:
                b = v.encode("utf-16le")
                out += struct.pack("<I", len(b)) + b + b"\0\0"
            else:
                out += v
        out += b"\0" * (align4(len(out)) - len(out))
        size = 8 + len(out)
        flags = struct.unpack_from("<I", self.head)[0] >> 24
        rtype = struct.unpack_from("<I", self.head, 4)[0]
        return struct.pack("<II", flags << 24 | size, rtype) + bytes(out)


def tables(d, recs=None):
    """Yield Table for every 0x802 record this module can parse (string or variant tables)."""
    if recs is None:
        recs, _ = records(d)
    for off, size, _, t in recs:
        if t & 0x7FFF != TABLE:
            continue
        nd, = struct.unpack_from("<H", d, off + 12)
        if nd < 1 or nd > 4:
            continue
        et = d[off + 16 + 2 * nd]
        if et not in (STR, VAR):
            continue
        try:
            yield Table(d, off, size)
        except ValueError:
            continue


class StringRecord(Table):
    """A text-element record: one string cell, serialised like a type-8 table."""

    def __init__(self, d, off, size):
        self.off, self.size = off, size
        self.head, self.pre, self.etype = d[off:off + 8], b"", STR
        s, q = self._str(d, off + 8)
        if align4(q) != off + size or d[q:off + size].strip(b"\0"):
            raise ValueError("text record 0x%X does not end at its string" % off)
        self.cells = [(None, s)]


def editable(d, recs=None):
    """Yield every record whose strings the build can rewrite: tables and text records."""
    if recs is None:
        recs, _ = records(d)
    by_off = {t.off: t for t in tables(d, recs)}
    for off, size, _, t in recs:
        if off in by_off:
            yield by_off[off]
        elif t in TEXT_TYPES:
            try:
                yield StringRecord(d, off, size)
            except ValueError:
                continue
