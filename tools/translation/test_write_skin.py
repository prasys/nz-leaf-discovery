"""Fault-injection tests for write_skin.py. Ordinary temporary files only, never devices."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("write_skin", Path(__file__).with_name("write_skin.py"))
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


class ApplyRange(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "ordinary-file.bin"
        self.original = b"A" * 1024
        self.initial = b"P" * 512 + self.original + b"S" * 512
        self.source.write_bytes(self.initial)
        self.payload = b"B" * 1024
        self.out = self.root / "receipt"

    def run_write(self, identity=None):
        return writer.apply_range(self.source, 512, self.original, self.payload,
                                  {"id": 9}, identity or (lambda: {"id": 9}), self.out, {})

    def status(self):
        return json.loads((self.out / "write-report.json").read_text())["status"]

    def test_success_only_changes_exact_range(self):
        report = self.run_write()
        self.assertEqual(self.source.read_bytes(), b"P" * 512 + self.payload + b"S" * 512)
        self.assertEqual((self.out / "substance-before-write.bin").read_bytes(), self.original)
        self.assertEqual(report["status"], "WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED")

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

    def test_interrupt_mid_write_restores_original(self):
        def interrupt(stream, data):
            stream.write(data[:256])
            raise KeyboardInterrupt
        real = writer.write_exact
        calls = 0

        def once(stream, data):
            nonlocal calls
            calls += 1
            return interrupt(stream, data) if calls == 1 else real(stream, data)
        with patch.object(writer, "write_exact", once), self.assertRaises(KeyboardInterrupt):
            self.run_write()
        self.assertEqual(self.source.read_bytes(), self.initial)
        self.assertEqual(self.status(), "FAILED_AND_ORIGINAL_RANGE_RESTORED")

    def test_rollback_failure_is_reported(self):
        with patch.object(writer, "write_exact", side_effect=OSError("injected I/O failure")):
            with self.assertRaises(OSError):
                self.run_write()
        self.assertEqual(self.status(), "FAILED_ROLLBACK_NOT_VERIFIED")

    def test_unaligned_or_resized_ranges_are_refused(self):
        for offset, payload in ((513, self.payload), (512, b""), (512, b"x"),
                                (512, b"X" * 512), (512, b"X" * 1536)):
            with self.assertRaises(ValueError):
                writer.apply_range(self.source, offset, self.original, payload,
                                   {}, lambda: {}, self.out, {})
        self.assertEqual(self.source.read_bytes(), self.initial)


IMG = os.path.expanduser(os.environ.get("NISSAN_IMG", "~/nissan/sdcard/nissan-sd-485-1972-00.img"))


class StrictStream:
    """File wrapper that fails like /dev/rdiskN on unaligned or partial-sector reads."""

    def __init__(self, f):
        self.f, self.pos = f, 0

    def seek(self, off):
        if off % 512:
            raise OSError(22, "Invalid argument (unaligned seek)")
        self.pos = off
        self.f.seek(off)

    def read(self, n):
        if n % 512:
            raise OSError(22, "Invalid argument (partial sector)")
        return self.f.read(n)


@unittest.skipUnless(os.path.exists(IMG), "no card image")
class SkinExtentOnImage(unittest.TestCase):
    def test_finds_skin_with_sector_reads_only(self):
        with open(IMG, "rb") as f:
            got = writer.skin_extent(writer.sector_reader(StrictStream(f)))
        self.assertEqual(got, (writer.OFFSET, writer.FILE_LEN, True))


class Preflight(unittest.TestCase):
    """preflight() against a fake card: the skin range lives at OFFSET in a sparse dict."""

    def setUp(self):
        body = b"\x01\x00\x02\x04" + b"\0" * 60 + b"\x08\x00\x00\x00\x01\x40\x00\x00"
        body += b"\x02\x00\x02\x04" + b"\0" * 8
        self.stock = body + b"\0" * (writer.FILE_LEN - len(body) - 36) + writer.STOCK_TRAILER
        self.build = bytearray(self.stock)
        self.build[0x44:0x48] = b"\x01\x50\x00\x00"
        self.build = bytes(self.build)
        self.tail = b"T" * (writer.SPAN - writer.FILE_LEN)
        self.card = self.stock + self.tail
        self.pins = {writer.sha(self.build): "test build"}
        self.extent = (writer.OFFSET, writer.FILE_LEN, True)
        patcher = patch.object(writer, "BASELINE_SHA", writer.sha(self.stock))
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, off, n):
        self.assertEqual((off, n), (writer.OFFSET, writer.SPAN))
        return self.card

    def run_preflight(self, build=None, pins=None):
        with patch.object(writer, "skin_extent", lambda read: self.extent):
            return writer.preflight(self.read, self.build if build is None else build,
                                    self.pins if pins is None else pins)

    def test_pinned_build_over_stock_keeps_tail(self):
        live, payload, label = self.run_preflight()
        self.assertEqual(label, "stock skin")
        self.assertEqual(payload, self.build + self.tail)
        self.assertEqual(len(payload), len(live))

    def test_unpinned_build_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not pinned"):
            self.run_preflight(pins={})

    def test_wrong_size_build_is_refused(self):
        with self.assertRaisesRegex(ValueError, "same-size"):
            self.run_preflight(build=self.build + b"\0" * 4)

    def test_changed_trailer_is_refused(self):
        with self.assertRaisesRegex(ValueError, "trailer"):
            self.run_preflight(build=self.build[:-1] + b"X")

    def test_moved_file_is_refused(self):
        self.extent = (writer.OFFSET + 512, writer.FILE_LEN, True)
        with self.assertRaisesRegex(ValueError, "exFAT"):
            self.run_preflight()
        self.extent = (writer.OFFSET, writer.FILE_LEN, False)
        with self.assertRaisesRegex(ValueError, "exFAT"):
            self.run_preflight()

    def test_unknown_live_skin_is_refused(self):
        self.card = b"Z" + self.card[1:]
        with self.assertRaisesRegex(ValueError, "no pinned baseline"):
            self.run_preflight()

    def test_already_applied_is_refused(self):
        self.card = self.build + self.tail
        with self.assertRaisesRegex(ValueError, "already holds"):
            self.run_preflight()

    def test_restore_stock_over_pinned_build(self):
        self.card = self.build + self.tail
        live, payload, label = self.run_preflight(build=self.stock)
        self.assertEqual(label, "test build")
        self.assertEqual(payload, self.stock + self.tail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
