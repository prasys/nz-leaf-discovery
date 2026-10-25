"""Synthetic container corruption tests; no devices or extracted code used."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("nz_pack", Path(__file__).with_name("pack_slot.py"))
packer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packer)


def container():
    raw = b"abcdefghijklmnop"
    compressed = b"\xf0\x01" + raw  # one LZ4 literal-only block
    stored = compressed + b"\0" * (512 - len(compressed))
    chunkhead = bytearray(512)
    chunkhead[:4] = b"MTCP"
    struct.pack_into("<2I", chunkhead, 4, 1, len(raw))
    struct.pack_into("<4I", chunkhead, 0x20, 1, len(raw), len(compressed), packer.sum32(stored))
    part0 = bytes(chunkhead) + stored
    tail = b"T" * 512
    payload = bytearray(part0 + tail)
    header = bytearray(512)
    struct.pack_into("<2I", header, 0, len(payload), len(payload) // 512)
    header[0x30:0x34] = b"SUM4"
    struct.pack_into("<I", header, 0x34, packer.sum32(payload))
    header[0x70:0x74] = b"MTLD"
    struct.pack_into("<I", header, 0x74, 2)
    struct.pack_into("<4I", header, 0x90, 0, 2, len(part0), packer.sum32(part0))
    header[0xa0:0xa4] = b"MTCP"
    struct.pack_into("<4I", header, 0xb0, 2, 1, len(tail), packer.sum32(tail))
    struct.pack_into("<I", header, 0xc4, len(raw))
    header[0x1fc:] = b"NKOK"
    return header, payload, raw + tail


class Pack(unittest.TestCase):
    def test_valid_container(self):
        header, payload, expected = container()
        self.assertEqual(packer.decode(header, payload), expected)

    def test_outer_checksum_detects_corruption(self):
        header, payload, _ = container()
        payload[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "SUM4"):
            packer.decode(header, payload)

    def test_part_checksum_detects_corruption_even_if_outer_updated(self):
        header, payload, _ = container()
        payload[-1] ^= 1
        struct.pack_into("<I", header, 0x34, packer.sum32(payload))
        with self.assertRaisesRegex(ValueError, "part sum"):
            packer.decode(header, payload)

    def test_chunk_checksum_detects_corruption_if_outer_and_part_updated(self):
        header, payload, _ = container()
        payload[514] ^= 1
        struct.pack_into("<I", header, 0x34, packer.sum32(payload))
        struct.pack_into("<I", header, 0x9c, packer.sum32(payload[:1024]))
        with self.assertRaisesRegex(ValueError, "chunk sum"):
            packer.decode(header, payload)

    def test_wrong_load_offset_rejected(self):
        header, payload, _ = container()
        struct.pack_into("<I", header, 0xc4, 17)
        with self.assertRaisesRegex(ValueError, "output offset"):
            packer.decode(header, payload)

    def test_unknown_source_rejected_before_compression(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            packer.pack(b"unknown", b"unknown", b"unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
