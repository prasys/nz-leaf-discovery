#!/usr/bin/env python3
"""Tests for tools/mtcp/mtcp.py.

Run from the repository root with::

    python3 -I tools/mtcp/test_mtcp.py

The tests cover the raw LZ4 block decoder (including overlap and every
malformed-input class we reject), the SUM4 checksum, MTCP container parsing
bounds, full synthetic round-trips, output-path safety, and -- when the real
carve and reference files are present -- the complete G214 decode against the
trusted liblz4 reference.
"""

import io
import contextlib
import json
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mtcp  # noqa: E402

# Synthetic binaries, like firmware outputs, stay outside the checkout.
os.makedirs(mtcp.DEFAULT_OUTDIR, exist_ok=True)
tempfile.tempdir = mtcp.DEFAULT_OUTDIR


# --------------------------------------------------------------------------
# helpers


def lz4_literals(payload):
    """Encode ``payload`` as a single literals-only (final) LZ4 sequence."""
    size = len(payload)
    out = bytearray()
    if size < 15:
        out.append(size << 4)
    else:
        out.append(0xF0)
        remaining = size - 15
        while remaining >= 255:
            out.append(0xFF)
            remaining -= 255
        out.append(remaining)
    out += payload
    return bytes(out)


def build_mtcp_from_packed(chunks, chunk_size):
    """Build an MTCP container from ``[(packed, unpacked_size), ...]``."""
    count = len(chunks)
    header = bytearray(mtcp.SECTOR)
    header[0:4] = b"MTCP"
    struct.pack_into("<I", header, 4, count)
    struct.pack_into("<I", header, 8, chunk_size)

    body = bytearray()
    for index, (packed, unpacked_size) in enumerate(chunks):
        span = ((len(packed) + mtcp.SECTOR - 1) // mtcp.SECTOR) * mtcp.SECTOR
        if span == 0:
            span = mtcp.SECTOR
        sector_count = span // mtcp.SECTOR
        padded = packed + b"\x00" * (span - len(packed))
        struct.pack_into(
            "<IIII",
            header,
            0x20 + index * 0x20,
            sector_count,
            unpacked_size,
            len(packed),
            mtcp.sum4(padded),
        )
        body += padded

    return bytes(header) + bytes(body)


def build_mtcp(payloads, chunk_size=None):
    """Build a container whose chunks are literals-only LZ4 blocks."""
    if chunk_size is None:
        chunk_size = max(len(payload) for payload in payloads)
    chunks = [(lz4_literals(payload), len(payload)) for payload in payloads]
    return build_mtcp_from_packed(chunks, chunk_size)


# --------------------------------------------------------------------------
# SUM4


class Sum4Tests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(mtcp.sum4(b""), 0)

    def test_single_word(self):
        self.assertEqual(mtcp.sum4(b"\x01\x00\x00\x00"), 1)

    def test_two_words(self):
        self.assertEqual(
            mtcp.sum4(b"\x01\x00\x00\x00\x02\x00\x00\x00"), 3
        )

    def test_wrap_mod_2_32(self):
        # 0xffffffff + 1 == 0 (mod 2**32)
        self.assertEqual(
            mtcp.sum4(b"\xff\xff\xff\xff\x01\x00\x00\x00"), 0
        )

    def test_little_endian(self):
        # bytes 00 01 00 00 == 0x00000100 little endian
        self.assertEqual(mtcp.sum4(b"\x00\x01\x00\x00"), 0x100)

    def test_trailing_bytes_zero_padded(self):
        self.assertEqual(mtcp.sum4(b"\x01"), 1)
        self.assertEqual(mtcp.sum4(b"\x00\x01"), 0x100)


# --------------------------------------------------------------------------
# LZ4 block decoder


class Lz4Tests(unittest.TestCase):
    def test_literals_only(self):
        self.assertEqual(
            mtcp.lz4_block_decode(bytes([0x50]) + b"hello", 5), b"hello"
        )

    def test_literal_length_extension(self):
        block = bytes([0xF0, 0x05]) + b"x" * 20
        self.assertEqual(mtcp.lz4_block_decode(block, 20), b"x" * 20)

    def test_literal_plus_match(self):
        # token 0x32: 3 literals, match length 2+4 = 6, offset 3
        block = bytes([0x32]) + b"abc" + b"\x03\x00"
        self.assertEqual(mtcp.lz4_block_decode(block, 9), b"abcabcabc")

    def test_overlapping_match(self):
        # one literal 'a', then offset 1, match length 5+4 = 9 -> ten 'a's
        block = bytes([0x15]) + b"a" + b"\x01\x00"
        self.assertEqual(mtcp.lz4_block_decode(block, 10), b"a" * 10)

    def test_match_length_extension(self):
        # one literal 'z', offset 1, match length 19 + 255 + 0 = 274
        block = bytes([0x1F]) + b"z" + b"\x01\x00" + bytes([0xFF, 0x00])
        decoded = mtcp.lz4_block_decode(block, 275)
        self.assertEqual(len(decoded), 275)
        self.assertEqual(decoded, b"z" * 275)

    def test_two_sequences_with_trailing_literals(self):
        block = (
            bytes([0x32]) + b"abc" + b"\x03\x00"  # "abc" + 6-byte match
            + bytes([0x20]) + b"de"               # final literals
        )
        self.assertEqual(
            mtcp.lz4_block_decode(block, 11), b"abcabcabcde"
        )

    def test_malformed_truncated_literal_length(self):
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0xF0]), 10)

    def test_malformed_literal_runs_past_end(self):
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0x50]) + b"ab", 10)

    def test_malformed_truncated_offset(self):
        # token with zero literals followed by a single offset byte
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0x01, 0x00]), 10)

    def test_malformed_zero_offset(self):
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0x01, 0x00, 0x00]), 10)

    def test_malformed_offset_beyond_output(self):
        # one literal, then a back-reference of 2 with only 1 byte written
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0x10]) + b"a" + b"\x02\x00", 10)

    def test_malformed_truncated_match_length(self):
        block = bytes([0x1F]) + b"a" + b"\x01\x00" + bytes([0xFF])
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(block, 1000)

    def test_overrun_literals(self):
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(bytes([0x50]) + b"hello", 3)

    def test_overrun_match(self):
        block = bytes([0x15]) + b"a" + b"\x01\x00"  # 10 bytes out
        with self.assertRaises(mtcp.LZ4Error):
            mtcp.lz4_block_decode(block, 5)


# --------------------------------------------------------------------------
# MTCP container parsing bounds


class ParserBoundsTests(unittest.TestCase):
    def _header(self, count=1, chunk_size=0x200000):
        header = bytearray(mtcp.SECTOR)
        header[0:4] = b"MTCP"
        struct.pack_into("<I", header, 4, count)
        struct.pack_into("<I", header, 8, chunk_size)
        return header

    def test_too_small(self):
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(b"\x00" * 10)

    def test_bad_magic(self):
        header = self._header()
        header[0:4] = b"XXXX"
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_zero_count(self):
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(self._header(count=0)))

    def test_count_too_large(self):
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(self._header(count=mtcp.MAX_COUNT + 1)))

    def test_table_past_header(self):
        # 0x20 + 16*0x20 == 0x220 > 0x200
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(self._header(count=16)))

    def test_zero_sector_count(self):
        header = self._header()
        struct.pack_into("<IIII", header, 0x20, 0, 10, 5, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_zero_unpacked(self):
        header = self._header()
        struct.pack_into("<IIII", header, 0x20, 1, 0, 5, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_zero_packed(self):
        header = self._header()
        struct.pack_into("<IIII", header, 0x20, 1, 10, 0, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_packed_exceeds_span(self):
        header = self._header()
        # sectorCount 1 -> span 512, packedSize 600
        struct.pack_into("<IIII", header, 0x20, 1, 10, 600, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_unpacked_exceeds_chunk_size(self):
        header = self._header(chunk_size=100)
        struct.pack_into("<IIII", header, 0x20, 1, 200, 5, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_only_last_chunk_may_be_short(self):
        header = self._header(count=2, chunk_size=100)
        struct.pack_into("<IIII", header, 0x20, 1, 50, 5, 0)
        struct.pack_into("<IIII", header, 0x40, 1, 50, 5, 0)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtcp(bytes(header))

    def test_valid_single_chunk(self):
        data = build_mtcp([b"A" * 10])
        info = mtcp.parse_mtcp(data)
        self.assertEqual(info["count"], 1)
        self.assertEqual(info["table"][0]["unpackedSize"], 10)
        self.assertEqual(info["packedEnd"], len(data))


# --------------------------------------------------------------------------
# full decode of synthetic containers


class DecodeTests(unittest.TestCase):
    def test_roundtrip_two_chunks(self):
        payloads = [b"A" * 100, b"B" * 50]
        data = build_mtcp(payloads, chunk_size=100)
        info = mtcp.parse_mtcp(data)
        decoded, reports = mtcp.decode_part_a(data, info)
        self.assertEqual(decoded, b"".join(payloads))
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(r["sum4Ok"] and r["lz4Ok"] for r in reports))

    def test_sum4_mismatch_is_rejected(self):
        data = bytearray(build_mtcp([b"A" * 10]))
        # Corrupt a packed-data byte, leaving the header SUM4 unchanged.
        data[mtcp.SECTOR] ^= 0xFF
        info = mtcp.parse_mtcp(bytes(data))
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(bytes(data), info)

    def test_sum4_includes_actual_sector_padding(self):
        data = bytearray(build_mtcp([b"A" * 10]))
        info = mtcp.parse_mtcp(data)
        data[mtcp.SECTOR + info["table"][0]["packedSize"]] = 1
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(data, info)
        # A matching checksum over nonzero stored padding is also supported.
        struct.pack_into("<I", data, 0x2C, mtcp.sum4(data[mtcp.SECTOR:]))
        result, _ = mtcp.decode_part_a(data, mtcp.parse_mtcp(data))
        self.assertEqual(result, b"A" * 10)

    def test_truncated_container_is_rejected(self):
        data = build_mtcp([b"A" * 10])
        info = mtcp.parse_mtcp(data)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(data[:-mtcp.SECTOR], info)

    def test_malformed_lz4_chunk_is_rejected(self):
        # Correct SUM4, but the block is a truncated literal-length extension.
        data = build_mtcp_from_packed([(bytes([0xF0]), 10)], 10)
        info = mtcp.parse_mtcp(data)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(data, info)

    def test_declared_length_mismatch_is_rejected(self):
        packed = lz4_literals(b"A" * 10)  # actually decodes to 10
        data = build_mtcp_from_packed([(packed, 20)], 20)
        info = mtcp.parse_mtcp(data)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(data, info)

    def test_declared_packed_past_end_is_rejected(self):
        data = bytearray(build_mtcp([b"A" * 10]))
        # Make chunk 0 claim two sectors while only one is present.
        struct.pack_into("<I", data, 0x20, 2)
        info = mtcp.parse_mtcp(bytes(data))
        with self.assertRaises(mtcp.MTCPError):
            mtcp.decode_part_a(bytes(data), info)


# --------------------------------------------------------------------------
# output path safety


class DescriptorTests(unittest.TestCase):
    def fixture(self):
        part_a = build_mtcp([b"A" * 10])
        part_b = b"B" * mtcp.SECTOR
        sector = bytearray(mtcp.SECTOR)
        sector[0x70:0x74] = b"MTLD"
        struct.pack_into("<I", sector, 0x74, 2)
        struct.pack_into("<8I", sector, 0x90, 0, len(part_a) // 512,
                         len(part_a), mtcp.sum4(part_a),
                         int.from_bytes(b"MTCP", "little"), 0, 0, 0)
        struct.pack_into("<8I", sector, 0xB0, len(part_a) // 512, 1,
                         len(part_b), mtcp.sum4(part_b), 0, 10, 0, 0)
        return sector, part_a + part_b

    def invoke(self, sector, payload):
        with tempfile.TemporaryDirectory() as root:
            card, carve = (os.path.join(root, n) for n in ("card.img", "carve.bin"))
            with open(card, "wb") as handle:
                handle.write(sector + payload)
            with open(carve, "wb") as handle:
                handle.write(payload)
            with contextlib.redirect_stdout(io.StringIO()):
                return mtcp.main(["--card-image", card, "--mtcp-file", carve,
                                  "--slot-lba", "0", "--info", "--no-reference"])

    def test_valid_descriptor(self):
        self.assertEqual(self.invoke(*self.fixture()), 0)

    def test_descriptor_count_checked_before_indexing(self):
        sector, _ = self.fixture()
        struct.pack_into("<I", sector, 0x74, 1)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.parse_mtld_sector(sector, 0)

    def test_descriptor_part_b_offset_is_checked(self):
        sector, payload = self.fixture()
        struct.pack_into("<I", sector, 0xB0, 3)
        with self.assertRaises(mtcp.MTCPError):
            self.invoke(sector, payload)

    def test_descriptor_length_detects_trailing_zero_truncation(self):
        sector, payload = self.fixture()
        # SUM4 alone cannot distinguish omitted trailing zero bytes.
        payload = payload[:-4] + b"\0" * 4
        struct.pack_into("<I", sector, 0xBC, mtcp.sum4(payload[-512:]))
        with self.assertRaises(mtcp.MTCPError):
            self.invoke(sector, payload[:-4])


class PathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.source = os.path.join(self.root, "source.bin")
        with open(self.source, "wb") as handle:
            handle.write(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reject_direct_source_alias(self):
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs(
                {"out": self.source}, [self.source], set(), force=True
            )

    def test_reject_symlink_alias(self):
        link = os.path.join(self.root, "link.bin")
        os.symlink(self.source, link)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs({"out": link}, [self.source], set(), force=True)

    def test_reject_hardlink_alias(self):
        link = os.path.join(self.root, "hardlink.bin")
        os.link(self.source, link)
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs({"out": link}, [self.source], set(), force=True)

    def test_reject_output_aliases(self):
        path = os.path.join(self.root, "out.bin")
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs({"a": path, "b": path}, [], set(), True)

    def test_reject_protected_directory(self):
        protected = os.path.join(self.root, "protected")
        os.makedirs(protected)
        target = os.path.join(protected, "out.bin")
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs({"out": target}, [self.source], {protected}, True)

    def test_reject_existing_without_force(self):
        existing = os.path.join(self.root, "existing.bin")
        with open(existing, "wb") as handle:
            handle.write(b"y")
        with self.assertRaises(mtcp.MTCPError):
            mtcp.guard_outputs({"out": existing}, [self.source], set(), False)

    def test_allow_existing_with_force(self):
        existing = os.path.join(self.root, "existing.bin")
        with open(existing, "wb") as handle:
            handle.write(b"y")
        mtcp.guard_outputs({"out": existing}, [self.source], set(), True)


# --------------------------------------------------------------------------
# CLI integration (synthetic source, no card image / reference)


class CliTests(unittest.TestCase):
    def _run(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                return mtcp.main(argv)

    def test_cli_writes_expected_outputs(self):
        payload_a = b"A" * 100
        payload_b = b"B" * 50
        data = build_mtcp([payload_a, payload_b], chunk_size=100)
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "g214.mtcp")
            out = os.path.join(root, "out")
            with open(src, "wb") as handle:
                handle.write(data)

            rc = self._run(
                [
                    "--mtcp-file", src,
                    "--out-dir", out,
                    "--no-card-image",
                    "--no-reference",
                ]
            )
            self.assertEqual(rc, 0)

            expected_a = payload_a + payload_b
            with open(os.path.join(out, "part-a.bin"), "rb") as handle:
                self.assertEqual(handle.read(), expected_a)
            with open(os.path.join(out, "part-b.bin"), "rb") as handle:
                self.assertEqual(handle.read(), b"")
            with open(os.path.join(out, "g214-rom.bin"), "rb") as handle:
                self.assertEqual(handle.read(), expected_a)
            with open(os.path.join(out, "metadata.json"), "rb") as handle:
                metadata = json.load(handle)
            self.assertEqual(metadata["mtcp"]["count"], 2)
            self.assertEqual(metadata["parts"]["b"]["storedOffset"], len(data))
            self.assertEqual(metadata["parts"]["b"]["romOffset"], 150)
            self.assertEqual(metadata["mtcp"]["table"][0]["storageOffset"], 512)

    def test_reference_mismatch_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            src, ref, out = (os.path.join(root, n) for n in ("src", "ref", "out"))
            with open(src, "wb") as handle:
                handle.write(build_mtcp([b"a" * 10]))
            with open(ref, "wb") as handle:
                handle.write(b"wrong reference")
            with self.assertRaises(mtcp.MTCPError):
                self._run(["--mtcp-file", src, "--no-card-image", "--reference", ref,
                           "--out-dir", out])
            self.assertFalse(os.path.exists(out))

    def test_cli_refuses_overwrite_without_force(self):
        data = build_mtcp([b"A" * 10])
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "g214.mtcp")
            out = os.path.join(root, "out")
            with open(src, "wb") as handle:
                handle.write(data)

            args = [
                "--mtcp-file", src,
                "--out-dir", out,
                "--no-card-image",
                "--no-reference",
            ]
            self.assertEqual(self._run(args), 0)
            with self.assertRaises(mtcp.MTCPError):
                self._run(args)
            self.assertEqual(self._run(args + ["--force"]), 0)

    def test_info_writes_nothing(self):
        data = build_mtcp([b"A" * 10])
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "g214.mtcp")
            out = os.path.join(root, "out")
            with open(src, "wb") as handle:
                handle.write(data)
            rc = self._run(
                [
                    "--mtcp-file", src,
                    "--out-dir", out,
                    "--no-card-image",
                    "--no-reference",
                    "--info",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(out))


# --------------------------------------------------------------------------
# real data (skipped when the carve/reference are not present)


HAS_REAL = os.path.isfile(mtcp.DEFAULT_CARVE) and os.path.isfile(
    mtcp.DEFAULT_REFERENCE
)


@unittest.skipUnless(HAS_REAL, "real carve/reference not present")
class RealDataTests(unittest.TestCase):
    def test_real_decode_matches_reference(self):
        part_a_stored, part_b, packed_end = mtcp.load_from_mtcp_file(
            mtcp.DEFAULT_CARVE
        )
        info = mtcp.parse_mtcp(part_a_stored)
        part_a, reports = mtcp.decode_part_a(part_a_stored, info)
        combined = part_a + part_b

        self.assertEqual(info["count"], 11)
        self.assertEqual(packed_end, 0x93E000)
        self.assertEqual(len(part_a), 0x147FE00)
        self.assertEqual(len(part_b), 0x1412400)
        self.assertEqual(len(combined), 0x2892200)

        self.assertEqual(mtcp.sum4(part_a_stored), 0xB9E60A6A)
        self.assertEqual(mtcp.sum4(part_b), 0x64212552)

        reference = mtcp._read_file(mtcp.DEFAULT_REFERENCE)
        self.assertEqual(combined, reference)

        self.assertEqual(len(reports), 11)
        self.assertTrue(all(r["sum4Ok"] for r in reports))
        self.assertTrue(all(r["lengthOk"] for r in reports))


if __name__ == "__main__":
    unittest.main(verbosity=2)
