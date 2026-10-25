"""Fault-injection tests use ordinary temporary files and a mocked diskutil, never actual devices."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("nz_image", Path(__file__).with_name("image_card.py"))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND | os.O_EXCL


class Imaging(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.dev_dir = root / "dev"
        self.out_dir = root / "out"
        self.dev_dir.mkdir()
        self.out_dir.mkdir()
        self.data = bytes(range(256)) * 64          # 16 KiB "card"
        self.fake_dev = self.dev_dir / "rdisk9"
        self.fake_dev.write_bytes(self.data)
        self.target = self.out_dir / "card.img"
        self.report = self.out_dir / "card.img.report.json"
        self.info = {"DeviceIdentifier": "disk9", "TotalSize": len(self.data), "VirtualOrPhysical": "Physical",
                     "RemovableMedia": True, "WholeDisk": True, "DeviceTreePath": "IODeviceTree:/fake",
                     "MediaName": "Fake SD"}
        self.parts = [{"DeviceIdentifier": "disk9s1"}]
        self.calls = []
        self.device_opens = []
        for p in (patch.object(tool.subprocess, "check_output", self.fake_diskutil),
                  patch.object(tool, "CHUNK", 4096),
                  patch.dict(os.environ, {"NISSAN_IMG": str(root / "must-not-be-used.img")}),
                  patch.object(os, "open", self.recording_open)):
            p.start()
            self.addCleanup(p.stop)

    # -- fakes -----------------------------------------------------------
    def fake_diskutil(self, argv, *a, **k):
        self.calls.append(list(argv))
        if argv[:3] == ["diskutil", "info", "-plist"]:
            return plistlib.dumps(self.info)
        if argv[:3] == ["diskutil", "list", "-plist"]:
            return plistlib.dumps({"AllDisksAndPartitions": [
                {"DeviceIdentifier": "disk9", "Partitions": self.parts}]})
        raise AssertionError(f"unexpected subprocess call {argv}")

    _real_open = staticmethod(os.open)

    def recording_open(self, path, flags, *a, **k):
        if Path(path).parent == self.dev_dir:
            self.device_opens.append((str(path), flags))
        return Imaging._real_open(path, flags, *a, **k)

    def run_tool(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(tool, "DEV_PREFIX", str(self.dev_dir / "r")):
            code = tool.main(list(argv))
        return code, out.getvalue()

    def image_args(self, *extra):
        return ["--out", str(self.target), "--device", "disk9", "--expect-bytes", str(len(self.data)), *extra]

    def sha(self, data=None):
        return hashlib.sha256(self.data if data is None else data).hexdigest()

    def assertNoOutput(self):
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), [])

    # -- success ---------------------------------------------------------
    def test_preflight_passes_and_prints_exact_command(self):
        code, out = self.run_tool(*self.image_args())
        self.assertEqual(code, 0)
        self.assertIn("READ_ONLY_PREFLIGHT_PASSED", out)
        self.assertIn(f"sudo python3 -I tools/nz-clock/image_card.py --device disk9 "
                      f"--expect-bytes {len(self.data)} --out {self.target.resolve()} --image", out)
        self.assertNoOutput()
        self.assertEqual(self.device_opens, [])

    def test_image_success_and_reverify(self):
        code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 0, out)
        self.assertIn("IMAGED_AND_VERIFIED", out)
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(self.report.stat().st_mode), 0o444)
        rep = json.loads(self.report.read_text())
        self.assertEqual((rep["bytes"], rep["sha256"], rep["image"]), (len(self.data), self.sha(), "card.img"))
        self.assertEqual(rep["device"]["DeviceIdentifier"], "disk9")
        self.assertRegex(rep["utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["card.img", "card.img.report.json"])
        # a second run only verifies, and never touches diskutil or the device
        self.calls.clear()
        self.device_opens.clear()
        code, out = self.run_tool("--out", str(self.target), "--device", "disk9", "--image")
        self.assertEqual((code, self.calls, self.device_opens), (0, [], []))
        self.assertIn("IMAGE_VERIFIED", out)

    def test_device_is_only_opened_read_only_and_only_diskutil_info_list(self):
        self.run_tool(*self.image_args("--image"))
        self.assertTrue(self.device_opens)
        for _, flags in self.device_opens:
            self.assertEqual(flags & WRITE_FLAGS, 0)
            self.assertEqual(flags & os.O_ACCMODE, os.O_RDONLY)
        self.assertTrue(self.calls)
        for call in self.calls:
            self.assertEqual(call[0], "diskutil")
            self.assertIn(call[1], ("info", "list"))
        self.assertEqual(self.fake_dev.read_bytes(), self.data)

    def test_source_is_never_opened_with_write_mode_via_builtin_open(self):
        modes = []
        real = open
        def spy(file, mode="r", *a, **k):
            if Path(file).parent == self.dev_dir:
                modes.append(mode)
            return real(file, mode, *a, **k)
        with patch("builtins.open", spy):
            self.run_tool(*self.image_args("--image"))
        for mode in modes:
            self.assertEqual(mode, "rb")

    # -- verify mode -----------------------------------------------------
    def make_verified(self):
        code, _ = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 0)
        self.calls.clear()

    def verify(self, *extra):
        code, out = self.run_tool("--out", str(self.target), *extra)
        self.assertEqual(self.calls, [])
        return code, out

    def test_verify_wrong_expect_bytes(self):
        self.make_verified()
        code, out = self.verify("--expect-bytes", str(len(self.data) + 512))
        self.assertEqual(code, 3)
        self.assertIn("IMAGE_VERIFY_FAILED", out)

    def test_verify_detects_modified_image(self):
        self.make_verified()
        os.chmod(self.target, 0o644)
        with open(self.target, "r+b") as f:
            f.write(b"X")
        os.chmod(self.target, 0o444)
        code, out = self.verify()
        self.assertEqual(code, 3)
        self.assertIn("SHA256", out)

    def test_verify_detects_size_change(self):
        self.make_verified()
        os.chmod(self.target, 0o644)
        with open(self.target, "ab") as f:
            f.write(b"X")
        os.chmod(self.target, 0o444)
        code, out = self.verify()
        self.assertEqual(code, 3)
        self.assertIn("size", out)

    def test_verify_requires_mode_0444(self):
        self.make_verified()
        os.chmod(self.target, 0o644)
        code, out = self.verify()
        self.assertEqual(code, 3)
        self.assertIn("0444", out)

    def test_verify_requires_sidecar_report(self):
        self.make_verified()
        os.chmod(self.report, 0o644)
        self.report.unlink()
        code, out = self.verify()
        self.assertEqual(code, 3)
        self.assertIn("missing sidecar", out)

    def test_verify_report_mismatch(self):
        self.make_verified()
        rep = json.loads(self.report.read_text())
        rep["sha256"] = "0" * 64
        os.chmod(self.report, 0o644)
        self.report.write_text(json.dumps(rep))
        os.chmod(self.report, 0o444)
        code, out = self.verify()
        self.assertEqual(code, 3)
        self.assertIn("SHA256", out)

    def test_verify_never_overwrites_even_with_image_flag(self):
        self.make_verified()
        self.fake_dev.write_bytes(b"\xff" * len(self.data))
        self.run_tool(*self.image_args("--image"))
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(self.calls, [])

    # -- refusals --------------------------------------------------------
    def refused(self, *extra):
        code, out = self.run_tool(*self.image_args(*extra))
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("REFUSED:"), out)
        self.assertNoOutput()
        return out

    def test_wrong_size_refused(self):
        self.info["TotalSize"] = len(self.data) + 512
        self.assertIn("--expect-bytes", self.refused("--image"))
        self.assertEqual(self.device_opens, [])

    def test_mounted_partition_refused(self):
        self.parts = [{"DeviceIdentifier": "disk9s1", "MountPoint": "/Volumes/NAV"}]
        self.assertIn("mounted", self.refused("--image"))
        self.assertEqual(self.device_opens, [])

    def test_non_removable_refused(self):
        self.info["RemovableMedia"] = False
        self.assertIn("removable", self.refused())

    def test_not_whole_disk_refused(self):
        self.info["WholeDisk"] = False
        self.assertIn("whole disk", self.refused("--image"))

    def test_virtual_disk_refused(self):
        self.info["VirtualOrPhysical"] = "Virtual"
        self.assertIn("physical", self.refused())

    def test_bad_device_name_is_usage_error(self):
        for bad in ("disk9s1", "/dev/disk9", "rdisk9"):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                tool.main(["--out", str(self.target), "--device", bad, "--expect-bytes", "512"])
            self.assertEqual(cm.exception.code, 2)

    def test_missing_expect_bytes_is_usage_error(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            tool.main(["--out", str(self.target), "--device", "disk9"])
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.calls, [])

    def test_stale_report_without_image_refused(self):
        self.report.write_text("{}")
        code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("never overwrites", out)
        self.assertEqual(self.report.read_text(), "{}")

    # -- faults during --image -------------------------------------------
    def assertFailedClean(self, out):
        self.assertTrue(out.startswith("IMAGING_FAILED:") or out.startswith("REFUSED:"), out)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.report.exists())
        self.assertNoOutput()                       # including our temp file

    def test_short_read_leaves_nothing(self):
        self.fake_dev.write_bytes(self.data[:-512])
        code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("Short read", out)
        self.assertFailedClean(out)

    def test_hash_mismatch_on_reread_leaves_nothing(self):
        real = tool.sha256_file
        with patch.object(tool, "sha256_file", lambda p: "f" * 64 if ".partial." in str(p) else real(p)):
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("Re-read", out)
        self.assertFailedClean(out)

    def test_target_appears_mid_run_is_not_overwritten(self):
        real = os.fsync
        def sneaky(fd):
            real(fd)
            if not self.target.exists():
                self.target.write_bytes(b"someone else's file")
        with patch.object(os, "fsync", sneaky):
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("IMAGING_FAILED", out)
        self.assertEqual(self.target.read_bytes(), b"someone else's file")
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["card.img"])   # temp removed, nothing else

    def test_identity_change_during_imaging_leaves_nothing(self):
        real = tool.identify
        calls = 0
        def drift(*a, **k):
            nonlocal calls
            calls += 1
            result = real(*a, **k)
            return {**result, "MediaName": "Other"} if calls == 2 else result
        with patch.object(tool, "identify", drift):
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("identity changed", out)
        self.assertFailedClean(out)

    def test_report_verify_mismatch_is_reported(self):
        real = tool.write_new
        def bad(path, data):
            if not data.startswith(b"{"):
                return real(path, data)
            rep = json.loads(data)
            rep["sha256"] = "0" * 64
            real(path, json.dumps(rep).encode())
        with patch.object(tool, "write_new", bad):
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertIn("SHA256", out)
        self.assertEqual(self.target.read_bytes(), self.data)    # published image is kept, never deleted

    def test_unreadable_device_creates_nothing(self):
        self.fake_dev.unlink()
        code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertFailedClean(out)

    def test_sudo_ownership_handed_back(self):
        with patch.object(tool.os, "geteuid", return_value=0), \
                patch.dict(os.environ, {"SUDO_UID": "501", "SUDO_GID": "20"}), \
                patch.object(tool.os, "fchown") as fchown:
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 0, out)
        self.assertTrue(fchown.called)
        for call in fchown.call_args_list:
            self.assertEqual(call.args[1:], (501, 20))

    # -- --adopt ----------------------------------------------------------
    def hand_made(self, mode=0o444):
        self.target.write_bytes(self.data)
        os.chmod(self.target, mode)

    def test_adopt_writes_report_without_touching_image_or_device(self):
        self.hand_made()
        before = self.target.stat().st_mtime_ns
        code, out = self.run_tool("--out", str(self.target), "--adopt")
        self.assertEqual(code, 0, out)
        self.assertIn("IMAGE_ADOPTED_UNVERIFIED_SOURCE", out)
        rep = json.loads(self.report.read_text())
        self.assertEqual((rep["status"], rep["sha256"], rep["device"]), ("ADOPTED_UNVERIFIED_SOURCE", self.sha(), None))
        self.assertIn("not checked", rep["note"])
        self.assertEqual(stat.S_IMODE(self.report.stat().st_mode), 0o444)
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), (self.data, before))
        self.assertEqual((self.calls, self.device_opens), ([], []))
        code, out = self.run_tool("--out", str(self.target))
        self.assertEqual(code, 0)
        self.assertIn("IMAGE_VERIFIED", out)

    def test_adopt_refuses_non_0444_and_prints_chmod(self):
        self.hand_made(0o644)
        code, out = self.run_tool("--out", str(self.target), "--adopt")
        self.assertEqual(code, 1)
        self.assertIn(f"chmod 0444 {self.target.resolve()}", out)
        self.assertFalse(self.report.exists())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o644)

    def test_adopt_refuses_existing_report(self):
        self.hand_made()
        self.report.write_text("{}")
        code, out = self.run_tool("--out", str(self.target), "--adopt")
        self.assertEqual(code, 1)
        self.assertIn("never overwrites", out)
        self.assertEqual(self.report.read_text(), "{}")

    def test_adopt_refuses_matching_legacy_report_but_ignores_other_images(self):
        self.hand_made()
        legacy = self.out_dir / "image-report.json"
        legacy.write_text(json.dumps({"image": "card.img"}))
        self.assertEqual(self.run_tool("--out", str(self.target), "--adopt")[0], 1)
        legacy.write_text(json.dumps({"image": "other.img"}))
        self.assertEqual(self.run_tool("--out", str(self.target), "--adopt")[0], 0)
        self.assertEqual(legacy.read_text(), json.dumps({"image": "other.img"}))

    def test_adopt_needs_existing_image_and_excludes_image_flag(self):
        for argv in (["--out", str(self.target), "--adopt"], ["--out", str(self.target), "--adopt", "--image"]):
            if argv[-1] == "--image":
                self.hand_made()
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                tool.main(argv)
            self.assertEqual(cm.exception.code, 2)

    def test_old_shared_report_is_read_only_if_it_names_the_image(self):
        self.make_verified()
        legacy = self.out_dir / "image-report.json"
        os.chmod(self.report, 0o644)
        self.report.rename(legacy)
        os.chmod(legacy, 0o444)
        self.assertEqual(self.verify()[0], 0)       # it names card.img
        other = self.out_dir / "other.img"
        other.write_bytes(self.data)
        os.chmod(other, 0o444)
        code, out = self.run_tool("--out", str(other))
        self.assertEqual(code, 3)
        self.assertIn("missing sidecar", out)

    # -- several images in one directory ----------------------------------
    def test_two_images_share_a_directory(self):
        self.make_verified()
        first_report = self.report.read_text()
        second = self.out_dir / "second.img"
        self.fake_dev.write_bytes(b"\x07" * len(self.data))
        code, out = self.run_tool("--out", str(second), "--device", "disk9",
                                  "--expect-bytes", str(len(self.data)), "--image")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.report.read_text(), first_report)
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()),
                         ["card.img", "card.img.report.json", "second.img", "second.img.report.json"])
        for img in (self.target, second):
            self.assertEqual(self.run_tool("--out", str(img))[0], 0)

    # -- file systems without hard links ----------------------------------
    @staticmethod
    def fake_rename_excl(src, dst):
        if os.path.lexists(dst):
            raise FileExistsError(17, "exists", str(dst))
        os.rename(src, dst)

    def test_no_hard_links_publishes_with_rename_excl(self):
        with patch.object(tool.os, "link", side_effect=OSError(1, "no links")), \
                patch.object(tool, "rename_excl", self.fake_rename_excl):
            code, out = self.run_tool(*self.image_args())
            self.assertIn("publish by rename_excl", out)
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["card.img", "card.img.report.json"])

    def test_no_link_support_at_all_is_refused_in_preflight_before_any_read(self):
        with patch.object(tool.os, "link", side_effect=OSError(1, "no links")), \
                patch.object(tool, "rename_excl", side_effect=OSError("unsupported")):
            for extra in ((), ("--image",)):
                code, out = self.run_tool(*self.image_args(*extra))
                self.assertEqual(code, 1)
                self.assertTrue(out.startswith("REFUSED:"), out)
                self.assertIn("hard links", out)
        self.assertNoOutput()                       # probe files removed
        self.assertEqual(self.device_opens, [])

    def test_target_appears_mid_run_with_rename_excl(self):
        real = os.fsync
        def sneaky(fd):
            real(fd)
            if not self.target.exists():
                self.target.write_bytes(b"someone else's file")
        with patch.object(tool.os, "link", side_effect=OSError(1, "no links")), \
                patch.object(tool, "rename_excl", self.fake_rename_excl), patch.object(os, "fsync", sneaky):
            code, out = self.run_tool(*self.image_args("--image"))
        self.assertEqual(code, 1)
        self.assertEqual(self.target.read_bytes(), b"someone else's file")
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["card.img"])

    @unittest.skipUnless(sys.platform == "darwin", "renamex_np is macOS only")
    def test_real_rename_excl_refuses_to_overwrite(self):
        a, b = self.out_dir / "a", self.out_dir / "b"
        a.write_bytes(b"A")
        b.write_bytes(b"B")
        with self.assertRaises(FileExistsError):
            tool.rename_excl(a, b)
        self.assertEqual((a.read_bytes(), b.read_bytes()), (b"A", b"B"))
        b.unlink()
        tool.rename_excl(a, b)
        self.assertEqual((b.read_bytes(), a.exists()), (b"A", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
