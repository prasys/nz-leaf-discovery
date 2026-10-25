"""Fault-injection tests use ordinary temporary files, never actual devices."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("nz_writer", Path(__file__).with_name("write_card.py"))
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


class Writer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "ordinary-file.bin"
        self.original = b"A" * 1024
        self.initial = b"P" * 512 + self.original + b"S" * 512
        self.source.write_bytes(self.initial)
        self.slot = b"B" * 512
        self.out = self.root / "receipt"

    def run_write(self, identity=None):
        return writer.apply_range(self.source, 512, self.original, self.slot,
                                  {"id": 9}, identity or (lambda: {"id": 9}), self.out, {})

    def status(self):
        return json.loads((self.out / "write-report.json").read_text())["status"]

    def test_success_only_changes_exact_range(self):
        report = self.run_write()
        self.assertEqual(self.source.read_bytes(), b"P" * 512 + self.slot + b"A" * 512 + b"S" * 512)
        self.assertEqual((self.out / "G214-before-write.bin").read_bytes(), self.original)
        self.assertEqual(report["status"], "WRITTEN_AND_BYTE_VERIFIED_HARDWARE_BOOT_UNTESTED")

    def test_identity_change_refuses_without_restore_or_write(self):
        with self.assertRaises(ValueError):
            self.run_write(lambda: {"id": 10})
        self.assertEqual(self.source.read_bytes(), self.initial)
        self.assertEqual(self.status(), "REFUSED_BEFORE_WRITE_NO_ROLLBACK_NEEDED")

    def test_changed_baseline_is_not_overwritten_by_rollback(self):
        changed = b"C" * len(self.initial)
        self.source.write_bytes(changed)
        with self.assertRaises(ValueError):
            self.run_write()
        self.assertEqual(self.source.read_bytes(), changed)
        self.assertEqual(self.status(), "REFUSED_BEFORE_WRITE_NO_ROLLBACK_NEEDED")

    def test_partial_write_failure_restores_original(self):
        real = writer.write_exact
        calls = 0
        def fail_once(stream, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                stream.write(data[:256])
                raise OSError("injected partial write")
            real(stream, data)
        with patch.object(writer, "write_exact", fail_once), self.assertRaises(OSError):
            self.run_write()
        self.assertEqual(self.source.read_bytes(), self.initial)
        self.assertEqual(self.status(), "FAILED_AND_ORIGINAL_RANGE_RESTORED")

    def test_readback_failure_restores_original(self):
        real = writer.read_exact
        calls = 0
        def corrupt_once(stream, size):
            nonlocal calls
            calls += 1
            data = real(stream, size)
            return b"?" * size if calls == 2 else data
        with patch.object(writer, "read_exact", corrupt_once), self.assertRaises(OSError):
            self.run_write()
        self.assertEqual(self.source.read_bytes(), self.initial)
        self.assertEqual(self.status(), "FAILED_AND_ORIGINAL_RANGE_RESTORED")

    def test_rollback_failure_is_reported(self):
        with patch.object(writer, "write_exact", side_effect=OSError("injected I/O failure")):
            with self.assertRaises(OSError):
                self.run_write()
        self.assertEqual(self.status(), "FAILED_ROLLBACK_NOT_VERIFIED")

    def test_unaligned_or_oversized_ranges_are_refused(self):
        for offset, slot in ((513, self.slot), (512, b""), (512, b"x"), (512, b"X" * 1536)):
            with self.assertRaises(ValueError):
                writer.apply_range(self.source, offset, self.original, slot,
                                   {}, lambda: {}, self.out, {})
        self.assertEqual(self.source.read_bytes(), self.initial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
