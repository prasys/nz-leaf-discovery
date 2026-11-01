#!/usr/bin/env python3
"""Synthetic parser/codec tests; no firmware or audio fixtures in git.

Run: python3 -I tools/language-speech/test_speech.py
"""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gid_catalog import Gid, span
from ssc_decode import Bits, coefficients, decode, i32, mul, transform


def packed(bits):
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits)//8, "big")


class FakeTables:
    bands = tuple(range(0, 113, 8)) + (128,)
    radix = (0, 3, 3, 9, 8, 13, 17)
    bias = (0, 1, 0, 4, 0, 0, 0)
    rotation = (0x7fffffff, 0) * 64
    twiddle = (0x7fffffff, 0) * 64
    window = (0,) * 128

    def symbol(self, bits, mode):
        return 272 if bits.read(1) else 0


def member():
    # Two boundaries, one playlist word, one PCM descriptor; all synthetic.
    data = bytearray(164)
    struct.pack_into("<9I", data, 0, 2, 80, 16, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<2I", data, 64, 80, 84)
    struct.pack_into("<I", data, 80, 128)
    struct.pack_into("<5I", data, 96, 1, 64, 4, 0, 4)
    struct.pack_into("<4sIII", data, 128, bytes.fromhex("02010102"), 160, 4, 4)
    return data


class SpeechTests(unittest.TestCase):
    def test_bit_order_and_eof(self):
        b = Bits(b"\xa5\x80")
        self.assertEqual((b.read(3), b.read(6), b.read(7)), (5, 11, 0))
        with self.assertRaises(ValueError): b.read(1)

    def test_end_and_silence_markers(self):
        t = FakeTables()
        self.assertEqual(decode(packed("111"), t), b"")
        self.assertEqual(decode(packed("000111111"), t), bytes(256))
        # A third-band 7 is neither silence nor end.
        with self.assertRaises(ValueError): decode(packed("000000111"), t)

    def test_zero_transform_block(self):
        bits = "000"*15 + "00000" + "101"*14 + "111"
        self.assertEqual(decode(packed(bits), FakeTables()), bytes(256))
        out, pending = transform([0]*128, [0]*128, FakeTables())
        self.assertEqual((out, pending), ([0]*128, [0]*128))

    def test_escape_and_dequantization(self):
        # First pair symbol (16,0), positive, escape width4 value3 =>19.
        bits = "110" + "000"*14 + "1" + "0" + "0" + "0011" + "000"
        bits += "00000" + "101"*14
        values = coefficients(Bits(packed(bits)), FakeTables())
        self.assertEqual(values[0], 36 << 10)
        self.assertEqual(values[1:], [0]*127)

    def test_truncation_and_trailing_data(self):
        with self.assertRaises(ValueError): decode(b"\0", FakeTables())
        with self.assertRaises(ValueError): decode(b"\xe0\0", FakeTables())

    def test_signed_fixed_multiply(self):
        self.assertEqual(i32(0xffffffff), -1)
        self.assertEqual(mul(0x7fffffff, 0x7fffffff), 0x3fffffff)
        self.assertEqual(mul(-1, 0x7fffffff), 0)
        self.assertEqual(mul(-0x80000000, -0x80000000), 0x40000000)

    def test_member_and_wrapper(self):
        data = member()
        gid = Gid(bytes(data))
        self.assertEqual(gid.tokens(0), ["clip:0"])
        wrapper = bytearray(56) + data
        wrapper[:16] = b"0000507520150717"
        struct.pack_into("<4I", wrapper, 16, len(wrapper), 56, 0, 1)
        struct.pack_into("<12sIII", wrapper, 32, b"SJP00000.GID", 56, len(data), len(data))
        self.assertEqual(Gid(bytes(wrapper)).container_offset, 56)
        with self.assertRaises(ValueError): gid.playlist(1)

    def test_bad_boundaries_and_descriptors(self):
        for offset, value in ((68, 76), (80, 127), (132, 1000), (140, 8)):
            data = member()
            struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): Gid(bytes(data))
        with self.assertRaises(ValueError): span(b"abc", -1, 1)

    def test_ce_e8_header(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"ce-extract"))
        import lzx
        br = lzx._Bits(bytes.fromhex("5b80808d0000"))
        self.assertEqual(br.read(1), 1)
        self.assertEqual((br.read(16)<<16)|br.read(16), 12000000)
        data = bytearray(b"\xe8" + (100).to_bytes(4, "little") + bytes(11))
        # At offset0 an absolute displacement stays100; offset1 becomes99.
        data = bytearray(b"\0") + data
        lzx._e8_untranslate(data, 12000000)
        self.assertEqual(int.from_bytes(data[2:6], "little"), 99)


if __name__ == "__main__": unittest.main()
