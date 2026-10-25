#!/usr/bin/env python3
"""Read-only decoder for the AUI script bytecode in substance.skn (issue #29).

The grammar was recovered from G214 auirtdll.dll; see docs/findings/12-hour-offset-ui.md.

Code records (type 0x402 / 0x8402) hold
    [u32 if record flags & 2], u32 n, n x u32 sender ids, u32 0, u32 event (-1 = none),
    then one statement.
Statements (FUN_411eab34) are u16 words on 2-byte boundaries:
    w < 0x8000  block of w bytes counted from the length word (0 = empty)
    0x8001 return, 0x8003 expr, 0x8004 if expr stmt, 0x8005 else stmt,
    0x8006 elseif expr stmt, 0x8007 end-if, 0x8008 assign target-expr value-expr,
    0x8009 while expr stmt, 0x800a/0x800b/0x800d/0x800e expr, 0x800c (none)
Expressions (FUN_411e7340 length, FUN_411e6f98 token kind; operands big-endian):
    0x60-0x7f header with the expression length; without a header the expression
    is one token.  0x00-0x1f, 0x20-0x29 ints; 0x2a string; 0x2b end; 0x2c/0x2d
    false/true; 0x2e u32 and 0x80-0xff u15 object ids; 0x2f u32 handle;
    0x30-0x39 DISPID; 0x3a member name; 0x40 u32; 0x41-0x5b operator (b & 0x1f);
    0x5d @argument; 0x5e flags argc and 0x5f (argc 0): IDispatch::Invoke.
A member access pushes the object and then its DISPID (FUN_411e8d94 kind 0x104
over 0x101), so "object, DISPID" is adjacent whatever the arguments are.

Usage:
    skn_script.py [skin] [--object 0x89] [--dispid 0x69,0x6a]   member references
    skn_script.py [skin] --dump 70029-70038                      decompile records
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "translation"))
import skn_format  # noqa: E402

DEFAULT_SKIN = os.path.expanduser("~/nissan/work/raw-areas/hiddenp2_files/SkinChange__002__substance.skn")
CODE_TYPES = {0x402, 0x8402}
STATEMENTS = {0x8001: "return", 0x8005: "else", 0x8007: "end-if", 0x800C: "op800c"}
ONE_EXPR = {0x8003: "", 0x800A: "op800a ", 0x800B: "op800b ", 0x800D: "op800d ", 0x800E: "op800e "}
COND = {0x8004: "if", 0x8006: "elif", 0x8009: "while"}


class ParseError(Exception):
    pass


def sx(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def expr_end(d, p):
    """Return (body_start, end) of the expression at p (FUN_411e7340)."""
    b = d[p]
    if 0x60 <= b < 0x70:
        return p + 1, p + 1 + (b & 0xF)
    if 0x70 <= b < 0x78:
        return p + 2, p + 2 + (((b & 7) << 8) | d[p + 1])
    if b == 0x78:
        return p + 3, p + 3 + (((d[p + 1] & 0x7F) << 8) | d[p + 2])
    if b == 0x79:
        return p + 5, p + 5 + (((d[p + 1] & 0x7F) << 8) | d[p + 2])
    if 0x7A <= b <= 0x7F:
        return p + 4, p + 4 + (((b & 3) << 8) | d[p + 1])
    return p, token_end(d, p)


def token_end(d, p):
    return next(tokens(d, p, None))[3]


def tokens(d, p, end):
    """Yield (offset, kind, value, next offset) for tokens in [p, end); end None = one."""
    while end is None or p < end:
        b, q = d[p], p + 1
        if b < 0x20:
            kind, v, n = "int", b, q
        elif b == 0x2B:
            kind, v, n = "end", 0, q
        elif b in (0x2C, 0x2D):
            kind, v, n = "bool", b == 0x2D, q
        elif b in (0x2E, 0x2F, 0x40):
            kind = {0x2E: "obj", 0x2F: "handle", 0x40: "k107"}[b]
            v, n = struct.unpack_from(">I", d, q)[0], q + 4
        elif 0x20 <= b < 0x40:
            kind, lo = ("int" if b < 0x30 else "dispid"), b & 0xF
            if lo < 8:
                v, n = sx(((b & 7) << 8) | d[q], 11), q + 1
            elif lo == 8:
                v, n = sx(struct.unpack_from(">H", d, q)[0], 16), q + 2
            elif lo == 9:
                v, n = sx(struct.unpack_from(">I", d, q)[0], 32), q + 4
            elif lo == 10:
                a = (q + 3) & ~3
                size = struct.unpack_from("<I", d, a)[0]
                kind = "str" if b == 0x2A else "name"
                v, n = d[a + 4:a + 4 + size].decode("utf-16-le", "replace"), a + 4 + size + 2
            else:
                raise ParseError("bad token 0x%02X at 0x%X" % (b, p))
        elif 0x41 <= b <= 0x5B:
            kind, v, n = "op", b & 0x1F, q
        elif b == 0x5D:
            kind, v, n = "arg", d[q], q + 1
        elif b == 0x5E:
            kind, v, n = "call", (d[q], d[q + 1]), q + 2
        elif b == 0x5F:
            kind, v, n = "call", (0, 0), q
        elif b >= 0x80:
            kind, v, n = "obj", ((b & 0x7F) << 8) | d[q], q + 1
        else:
            raise ParseError("bad token 0x%02X at 0x%X" % (b, p))
        yield p, kind, v, n
        if end is None:
            return
        p = n
    if p != end:
        raise ParseError("expression overrun at 0x%X" % end)


def render(toks):
    out = []
    for _, kind, val, _ in toks:
        if kind == "obj":
            out.append("obj:0x%X" % val)
        elif kind == "dispid":
            out.append("#%s0x%X" % ("-" if val < 0 else "", abs(val)))
        elif kind == "call":
            out.append("call(%d,%d)" % val)
        elif kind == "str":
            out.append(repr(val))
        elif kind == "op":
            out.append("op%d" % val)
        else:
            out.append("%s:%s" % (kind, val))
    return " ".join(out)


def expression(d, p, out, lines=None, indent=""):
    body, end = expr_end(d, p)
    out.append((p, body, end))
    return end, (render(list(tokens(d, body, end))) if lines is not None else None)


def statement(d, p, out, lines=None, indent=""):
    """Walk one statement at p; append (start, body, end) of each expression to out."""
    p += p & 1
    w = struct.unpack_from("<H", d, p)[0]
    if w < 0x8000:
        start, end = p, p + w
        if w == 0:
            return p + 2
        if w < 2:
            raise ParseError("bad block at 0x%X" % start)
        p += 2
        while p < end:
            p = statement(d, p, out, lines, indent)
            p += p & 1
        if p - end not in (0, 1):  # the interpreter re-aligns after each statement
            raise ParseError("block overrun at 0x%X" % start)
        return end
    p += 2
    say = lines.append if lines is not None else (lambda s: None)
    if w in (0x8001, 0x8007, 0x800C):
        say(indent + STATEMENTS[w])
        return p
    if w in ONE_EXPR:
        p, text = expression(d, p, out, lines)
        say(indent + ONE_EXPR[w] + (text or ""))
        return p
    if w == 0x8008:
        p, target = expression(d, p, out, lines)
        p, value = expression(d, p, out, lines)
        say("%s[%s] := [%s]" % (indent, target, value))
        return p
    if w in COND:
        p, text = expression(d, p, out, lines)
        say("%s%s (%s)" % (indent, COND[w], text))
        return statement(d, p, out, lines, indent + "    ")
    if w == 0x8005:
        say(indent + "else")
        return statement(d, p, out, lines, indent + "    ")
    raise ParseError("bad statement 0x%04X at 0x%X" % (w, p - 2))


def header(d, o, flags):
    """Return (sender ids, event or None, statement offset) of a code record."""
    base = o + 8
    if flags & 1:  # named record: u32 nbytes, UTF-16LE, u16 0, align 4
        base = (base + 4 + struct.unpack_from("<I", d, base)[0] + 2 + 3) & ~3
    base += 4 if flags & 2 else 0
    n = struct.unpack_from("<I", d, base)[0]
    if n > 0x40:
        raise ParseError("unexpected code header at 0x%X" % o)
    ids = list(struct.unpack_from("<%dI" % n, d, base + 4))
    event = struct.unpack_from("<I", d, base + 8 + 4 * n)[0]
    return ids, (None if event == 0xFFFFFFFF else event), base + 4 + 4 * n + 8


def code_records(d):
    recs, _ = skn_format.records(d)
    for i, (o, s, fl, t) in enumerate(recs):
        if t in CODE_TYPES and s > 0x16:
            yield i, o, s, fl


def parse(d, o, flags, lines=None):
    exprs = []
    statement(d, header(d, o, flags)[2], exprs, lines, "    ")
    return exprs


def member_refs(d):
    """Yield (record index, record offset, expression offset, object, dispid, tokens)."""
    for i, o, s, fl in code_records(d):
        try:
            exprs = parse(d, o, fl)
        except (ParseError, IndexError, struct.error):
            continue
        for start, body, end in exprs:
            toks = list(tokens(d, body, end))
            for k in range(1, len(toks)):
                if toks[k][1] == "dispid" and toks[k - 1][1] == "obj":
                    yield i, o, start, toks[k - 1][2], toks[k][2], toks


def dump(d, lo, hi):
    recs, _ = skn_format.records(d)
    for i in range(lo, hi + 1):
        o, s, fl, t = recs[i]
        if t not in CODE_TYPES:
            continue
        ids, event, _ = header(d, o, fl)
        print("== rec %d @0x%06X senders=%s event=%s"
              % (i, o, [hex(x) for x in ids], "-" if event is None else hex(event)))
        lines = []
        parse(d, o, fl, lines)
        print("\n".join(lines))


def take(args, flag):
    if flag not in args:
        return None
    k = args.index(flag)
    value = args[k + 1]
    del args[k:k + 2]
    return value


def main(argv):
    args = list(argv)
    objects, dispids, span = take(args, "--object"), take(args, "--dispid"), take(args, "--dump")
    d = open(args[0] if args else DEFAULT_SKIN, "rb").read()
    if span:
        for part in span.split(","):
            lo, _, hi = part.partition("-")
            dump(d, int(lo, 0), int(hi or lo, 0))
        return 0
    objects = objects and {int(x, 0) for x in objects.split(",")}
    dispids = dispids and {int(x, 0) for x in dispids.split(",")}
    ok = bad = 0
    for i, o, s, fl in code_records(d):
        try:
            parse(d, o, fl)
            ok += 1
        except (ParseError, IndexError, struct.error):
            bad += 1
    print("code records parsed: %d ok, %d not parsed" % (ok, bad))
    for i, o, start, ob, disp, toks in member_refs(d):
        if (not objects or ob in objects) and (not dispids or disp in dispids):
            print("rec %6d @0x%06X expr@0x%06X obj=0x%X dispid=0x%X | %s"
                  % (i, o, start, ob, disp, render(toks)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
