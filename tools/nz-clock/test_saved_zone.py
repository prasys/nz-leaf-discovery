"""Checksum/state and transactional I/O tests using synthetic ordinary files."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("saved_zone", Path(__file__).with_name("set_saved_zone.py"))
zone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zone)


def fixture():
    copies = []
    for copy in (1, 2):
        b = bytearray(zone.AREA_SIZE)
        b[:4] = b"SRST"
        struct.pack_into("<3I", b, 4, 0x6000000c, 100 + copy, copy)
        struct.pack_into("<HBBBBB", b, zone.CLOCK, 2026, 10, 24, 8, 57, 26)
        struct.pack_into("<I", b, zone.CLOCK + 8, 1)
        struct.pack_into("<iIii", b, zone.CLOCK + 0x14, 3240000, 61, 0, 0)
        b[512:1024] = bytes(range(256)) * 2  # Unrelated data must survive.
        b[-4:] = b"SRED"
        struct.pack_into("<I", b, len(b) - 16, zone.sum32(b[:-16]))
        copies.append(bytes(b))
    return b"".join(copies)


class SavedZone(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original = fixture()
        self.candidate, self.plan = zone.patch_pair(self.original)
        self.source = self.root / "ordinary-card-file"
        self.source.write_bytes(self.original)
        self.out = self.root / "receipt"

    def apply(self, identify=lambda: "same"):
        return zone.apply_pair(self.source, self.original, self.candidate,
                               "same", identify, self.out, offset=0)

    def test_zone_type_integrity_generations_and_idempotence(self):
        for row, gen in zip(self.plan["after"], (103, 104)):
            self.assertEqual((row["zone"], row["zone_type"], row["dst"], row["user_offset"]),
                             (4680000, 0, 0, 0))
            self.assertEqual(row["generation"], gen)
        again, report = zone.patch_pair(self.candidate)
        self.assertEqual(again, self.candidate)
        self.assertEqual(report["status"], "ALREADY_FIXED_PLUS_13")
        self.assertEqual(self.candidate[512:1024], self.original[512:1024])
        self.assertEqual(self.candidate[zone.CLOCK:zone.CLOCK + 0x14],
                         self.original[zone.CLOCK:zone.CLOCK + 0x14])

    def test_corruption_and_unrecognized_clock_refused(self):
        b = bytearray(self.original)
        b[1000] ^= 1
        with self.assertRaisesRegex(ValueError, "word-sum"):
            zone.patch_pair(bytes(b))
        b = bytearray(self.original)
        struct.pack_into("<i", b, zone.CLOCK + 0x20, 6000)
        struct.pack_into("<I", b, zone.AREA_SIZE - 16, zone.sum32(b[:zone.AREA_SIZE - 16]))
        with self.assertRaisesRegex(ValueError, "Saved clock"):
            zone.patch_pair(bytes(b))

    def test_write_touches_only_four_sectors_and_preserves_snapshots(self):
        real_write = zone.write_sector
        writes = []
        def record(stream, offset, data):
            writes.append(offset)
            return real_write(stream, offset, data)
        with patch.object(zone, "write_sector", record):
            report = self.apply()
        self.assertEqual(writes, [s * 512 for s in zone.SECTORS])
        self.assertEqual(self.source.read_bytes(), self.candidate)
        self.assertEqual((self.out / "nav-pair-before.bin").read_bytes(), self.original)
        self.assertEqual((self.out / "nav-pair-before.bin").stat().st_mode & 0o222, 0)
        self.assertEqual(report["status"], "SAVED_PLUS_13_WRITTEN_BYTE_VERIFIED_CAR_TEST_PENDING")

    def test_identity_and_changed_baseline_refuse_without_rollback(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            self.apply(lambda: "different")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.out = self.root / "second-receipt"
        changed = bytes([self.original[0] ^ 1]) + self.original[1:]
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "baseline"):
            self.apply()
        self.assertEqual(self.source.read_bytes(), changed)

    def test_partial_write_restores_current_full_pair(self):
        real_write = zone.write_sector
        calls = 0
        def fail_once(stream, offset, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                stream.seek(offset)
                stream.write(data[:256])
                raise OSError("Injected partial write")
            return real_write(stream, offset, data)
        with patch.object(zone, "write_sector", fail_once):
            with self.assertRaisesRegex(OSError, "partial"):
                self.apply()
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertIn("FAILED_ORIGINAL_NAV_PAIR_RESTORED", (self.out / "write-report.json").read_text())

    def test_remount_after_write_allows_read_only_verification(self):
        mounted = False
        real_write = zone.write_sector
        def identify_write():
            if mounted:
                raise ValueError("Mounted; writes forbidden")
            return "same"
        def mount_after_last_write(stream, offset, data):
            nonlocal mounted
            real_write(stream, offset, data)
            if offset == zone.SECTORS[-1] * 512:
                mounted = True
        with patch.object(zone, "write_sector", mount_after_last_write):
            report = zone.apply_pair(self.source, self.original, self.candidate,
                                     "same", identify_write, self.out, offset=0,
                                     identify_read=lambda: "same")
        self.assertTrue(mounted)
        self.assertEqual(self.source.read_bytes(), self.candidate)
        self.assertEqual(report["status"], "SAVED_PLUS_13_WRITTEN_BYTE_VERIFIED_CAR_TEST_PENDING")

    def test_readback_failure_rolls_back_and_rollback_failure_is_explicit(self):
        real_read = zone.read_at
        calls = 0
        def bad_once(path, offset, length):
            nonlocal calls
            calls += 1
            data = real_read(path, offset, length)
            return bytes([data[0] ^ 1]) + data[1:] if calls == 1 else data
        with patch.object(zone, "read_at", bad_once):
            with self.assertRaisesRegex(OSError, "read-back"):
                self.apply()
        self.assertEqual(self.source.read_bytes(), self.original)
        self.out = self.root / "failed-rollback-receipt"
        with patch.object(zone, "write_sector", side_effect=OSError("Device failed")):
            with self.assertRaises(OSError):
                self.apply()
        self.assertIn("FAILED_ROLLBACK_UNVERIFIED", (self.out / "write-report.json").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
