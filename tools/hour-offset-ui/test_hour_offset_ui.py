#!/usr/bin/env python3
"""Tests for the issue #29 hour-offset helpers.  Synthetic bytes first; checks that
need the skin carve are skipped when it is absent.  Nothing is written anywhere.

    python3 -I tools/hour-offset-ui/test_hour_offset_ui.py
"""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import expset_scan  # noqa: E402
import hour_row_plan  # noqa: E402
import skn_script as S  # noqa: E402

HAVE_SKIN = os.path.exists(S.DEFAULT_SKIN)


def toks(b):
    return [(k, v) for _, k, v, _ in S.tokens(b, 0, len(b))]


def code_record(body, senders=(), event=0xFFFFFFFF, flags=0):
    payload = (struct.pack("<I", 0x575B) if flags & 2 else b"")
    payload += struct.pack("<I", len(senders)) + b"".join(struct.pack("<I", s) for s in senders)
    payload += struct.pack("<II", 0, event) + body
    payload += b"\0" * (-len(payload) % 4)
    return struct.pack("<II", (flags << 24) | (8 + len(payload)), 0x402) + payload


def skin(*records):
    return b"\0" * 0x40 + b"".join(records) + struct.pack("<II", 0x04020002, 0)


class Tokens(unittest.TestCase):
    def test_ints_are_big_endian_and_signed(self):
        self.assertEqual(toks(b"\x05"), [("int", 5)])
        self.assertEqual(toks(b"\x20\x3b"), [("int", 59)])
        self.assertEqual(toks(b"\x24\x00"), [("int", -1024)])
        self.assertEqual(toks(b"\x28\x01\x00"), [("int", 256)])
        self.assertEqual(toks(b"\x29\xff\xff\xff\xfe"), [("int", -2)])

    def test_objects_dispids_and_calls(self):
        self.assertEqual(toks(b"\x80\x89\x30\x6a\x5f"),
                         [("obj", 0x89), ("dispid", 0x6A), ("call", (0, 0))])
        self.assertEqual(toks(b"\x2e\x00\x01\x11\xcb\x5e\x02\x01"),
                         [("obj", 0x111CB), ("call", (2, 1))])
        self.assertEqual(toks(b"\x35\xfa"), [("dispid", -0x206)])

    def test_string_is_aligned_from_the_record(self):
        text = "Hi".encode("utf-16-le")
        b = b"\x2a\0\0\0" + struct.pack("<I", len(text)) + text + b"\0\0"
        self.assertEqual(toks(b), [("str", "Hi")])

    def test_bad_token_refused(self):
        with self.assertRaises(S.ParseError):
            toks(b"\x5c")


class Statements(unittest.TestCase):
    def test_header_less_expression_is_one_token(self):
        self.assertEqual(S.expr_end(b"\x2e\0\0\0\x01\x99", 0), (0, 5))

    def test_block_with_odd_statements_and_if(self):
        # block{ expr <obj 0x89 #0x6b call>; if (true) expr 1; end-if }
        inner = b"\x03\x80\x65\x80\x89\x30\x6b\x5f"
        # each odd-length statement is followed by one re-alignment byte
        cond = b"\x04\x80\x2d" + b"\x00" + b"\x03\x80\x01" + b"\x00" + b"\x07\x80"
        body = inner + cond
        block = struct.pack("<H", len(body) + 2) + body
        lines, exprs = [], []
        end = S.statement(block, 0, exprs, lines)
        self.assertEqual(end, len(block))
        self.assertIn("obj:0x89 #0x6B call(0,0)", lines[0])
        self.assertTrue(lines[1].startswith("if (bool:True)"))
        self.assertEqual(len(exprs), 3)

    def test_overrun_refused(self):
        with self.assertRaises(S.ParseError):
            S.statement(b"\x04\x00\x03\x80\x2e\0\0\0\x01", 0, [])

    def test_member_refs_on_synthetic_skin(self):
        setter = b"\x08\x80" + b"\x65\x80\x89\x30\x6c\x5f" + b"\x20\x05"  # operands not re-aligned
        d = skin(code_record(struct.pack("<H", len(setter) + 2) + setter, [0x111E8], 3),
                 code_record(b"\x00\x00", flags=2))
        refs = [(ob, disp) for _, _, _, ob, disp, _ in S.member_refs(d)]
        self.assertEqual(refs, [(0x89, 0x6C)])
        recs = list(S.code_records(d))
        self.assertEqual(S.header(d, recs[0][1], 0)[:2], ([0x111E8], 3))


class ExpSet(unittest.TestCase):
    def test_decode(self):
        unset = expset_scan.UNSET
        self.assertEqual(expset_scan.decode_expset([0] * 5 + [unset, 59, 3001]), (None, 0, False, 0))
        self.assertEqual(expset_scan.decode_expset([0] * 5 + [16, 59, 0]), (4, 0, False, 1440000))
        self.assertEqual(expset_scan.decode_expset([0] * 5 + [15, unset, 1]), (3, None, True, 1080000))


@unittest.skipUnless(HAVE_SKIN, "skin carve not present")
class RealSkin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(S.DEFAULT_SKIN, "rb") as source:
            cls.d = source.read()

    def test_parse_coverage(self):
        bad = 0
        for i, o, s, fl in S.code_records(self.d):
            try:
                S.parse(self.d, o, fl)
            except (S.ParseError, IndexError, struct.error):
                bad += 1
        self.assertEqual(bad, 0)

    def test_naviset_clock_members(self):
        used = {disp for _, _, _, ob, disp, _ in S.member_refs(self.d) if ob == 0x89}
        self.assertTrue({0x65, 0x66, 0x67, 0x68, 0x6B, 0x6C} <= used)
        self.assertFalse(used & {0x69, 0x6A, 0x6D, 0x6E, 0x6F, 0x70})

    def test_event_sinks(self):
        self.assertEqual(hour_row_plan.decode(self.d, 255)[:2], ([0x89], 0x21))
        self.assertEqual(hour_row_plan.decode(self.d, 256)[:2], ([0x89], 0x20))

    def test_plan_accepts_stock_and_refuses_changed_baseline(self):
        patched, problems = hour_row_plan.plan(self.d)
        self.assertEqual(problems, [])
        self.assertEqual(sum(a != b for a, b in zip(self.d[0x5000:0x470000], patched[0x5000:0x470000])),
                         len(hour_row_plan.EDITS))
        broken = bytearray(self.d)
        broken[hour_row_plan.EDITS[0][0]] ^= 1
        self.assertTrue(hour_row_plan.plan(bytes(broken))[1])

    def test_dst_toggle_stacks_on_hour_row(self):
        hour, problems = hour_row_plan.plan(self.d)
        self.assertEqual(problems, [])
        both, problems = hour_row_plan.plan(hour, "dst")
        self.assertEqual(problems, [])
        self.assertEqual(sum(a != b for a, b in zip(hour[0x5000:0x470000], both[0x5000:0x470000])),
                         len(hour_row_plan.DST_EDITS))
        self.assertFalse({e[0] for e in hour_row_plan.EDITS} & {e[0] for e in hour_row_plan.DST_EDITS})
        used = {disp for _, _, _, ob, disp, _ in S.member_refs(both) if ob == 0x89}
        self.assertTrue({0x69, 0x6A, 0x6D, 0x6E} <= used)
        self.assertFalse(used & {0x66, 0x6B, 0x6C})


if __name__ == "__main__":
    unittest.main()
