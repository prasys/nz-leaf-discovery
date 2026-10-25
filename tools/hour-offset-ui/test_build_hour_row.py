"""Filesystem boundaries for the offline hour-row builder; ordinary temporary files only."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hour_row as builder


class OutputBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / "work"
        self.work.mkdir()
        self.source = self.root / "sdcard" / "original.skn"
        self.source.parent.mkdir()
        self.source.write_bytes(b"original")
        env = patch.dict(os.environ, {"NISSAN_ROOT": str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def refuse(self, out):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as err:
            builder.main(["--skin", str(self.source), "--out", str(out)])
        self.assertEqual(err.exception.code, 2)
        self.assertEqual(self.source.read_bytes(), b"original")

    def test_originals_directory_is_not_an_output(self):
        out = self.source.parent / "candidate"
        self.refuse(out)
        self.assertFalse(out.exists())

    def test_work_root_itself_is_refused(self):
        self.refuse(self.work)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_symlink_cannot_escape_work(self):
        (self.work / "escape").symlink_to(self.source.parent, target_is_directory=True)
        self.refuse(self.work / "escape" / "candidate")
        self.assertFalse((self.source.parent / "candidate").exists())

    def test_new_build_is_read_only_and_keeps_input(self):
        out = self.work / "hour-row" / "candidate"
        source_sha = hashlib.sha256(b"original").hexdigest()
        with patch.dict(builder.hour_row_plan.KNOWN, {source_sha: "test fixture"}), \
                patch.object(builder.hour_row_plan, "plan", return_value=(b"candidate", [])), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(["--skin", str(self.source), "--out", str(out)]), 0)
        target = out / "substance.skn"
        self.assertEqual(target.read_bytes(), b"candidate")
        self.assertEqual(target.stat().st_mode & 0o222, 0)
        self.assertEqual(self.source.read_bytes(), b"original")
        report = json.loads((out / "hour-row-report.json").read_text())
        self.assertEqual(report["build_sha256"], hashlib.sha256(b"candidate").hexdigest())


if __name__ == "__main__":
    unittest.main()
