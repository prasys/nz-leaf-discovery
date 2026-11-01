#!/usr/bin/env python3
"""Fault injection uses ordinary temporary files only, never devices or images.

Run: python3 -I tools/language-speech/test_write_gid.py
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import write_gid as writer
import gid_patch
from gid_patch import patch as make_patch,validate
from gid_catalog import Gid
from greeting import CLIPS,EV_CLIPS

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
        self.assertEqual((self.out / "gid-before-write.bin").read_bytes(), self.original)
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

    def test_sync_failure_restores_and_verifies(self):
        with patch.object(writer,"sync_device",side_effect=[OSError("injected fsync"),"ok"]):
            with self.assertRaises(OSError):
                self.run_write()
        self.assertEqual(self.source.read_bytes(),self.initial)
        self.assertEqual(self.status(),"FAILED_AND_ORIGINAL_RANGE_RESTORED")

    def test_device_swap_after_partial_write_refuses_restore(self):
        with patch.object(writer,"write_exact",side_effect=OSError("injected write")):
            identities = iter(({"id":9},{"id":10}))
            with self.assertRaises(OSError):
                self.run_write(lambda: next(identities))
        self.assertEqual(self.status(),"FAILED_ROLLBACK_NOT_VERIFIED")

    def test_rollback_snapshot_failure_never_opens_source_writable(self):
        with patch.object(writer.os,"fsync",side_effect=OSError("snapshot fsync failed")):
            with self.assertRaises(OSError):
                self.run_write()
        self.assertEqual(self.source.read_bytes(),self.initial)

    def test_full_file_verification_failure_restores(self):
        def verify(part):
            if part == self.payload:
                raise OSError("injected full-file mismatch")
        with self.assertRaises(OSError):
            writer.apply_range(self.source,512,self.original,self.payload,{"id":9},
                               lambda:{"id":9},self.out,{},verify=verify)
        self.assertEqual(self.source.read_bytes(),self.initial)
        self.assertEqual(self.status(),"FAILED_AND_ORIGINAL_RANGE_RESTORED")


STOCK = Path.home()/"nissan/work/language-speech/SJP00300.GID"


@unittest.skipUnless(STOCK.exists(),"public GID fixture outside git unavailable")
class GidPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()
        cls.gid = Gid(cls.stock)
        cls.build = make_patch(cls.stock,{i:(bytes.fromhex("02010102"),b"\1\0") for i in CLIPS},"greeting")
        cls.greeting_replacements = {i:(bytes.fromhex("02010102"),b"\0\0") for i in CLIPS}
        cls.v11 = make_patch(cls.stock,cls.greeting_replacements,"greeting")
        cls.ev_replacements = {i:(bytes.fromhex("02010102"),b"\0\0") for i in EV_CLIPS}
        with patch.dict(gid_patch.ALLOWED_BASES,{"ev":{writer.sha(cls.v11)}},clear=False):
            cls.v2 = make_patch(cls.v11,cls.ev_replacements,"ev")

    def setUp(self):
        self.tail = b"T"*(writer.SPAN-writer.FILE_LEN)
        self.live = self.stock+self.tail

    def read(self,off,n):
        self.assertEqual((off,n),(writer.OFFSET,writer.SPAN))
        return self.live

    def preflight(self,build=None,pins=None):
        with patch.object(writer,"gid_extent",return_value=(writer.OFFSET,writer.FILE_LEN)):
            return writer.preflight(self.read,self.stock,self.build if build is None else build,
                                    {writer.sha(self.build):"fixture"} if pins is None else pins)

    def test_stock_to_pinned_build_preserves_nonfile_tail(self):
        live,payload,label = self.preflight()
        self.assertEqual(label,"stock GID")
        self.assertEqual(live,self.stock+self.tail)
        self.assertEqual(payload,self.build+self.tail)
        first,last = writer.write_window(live,payload)
        self.assertEqual(first%512,0)
        self.assertEqual(last%512,0)
        self.assertLessEqual(last,writer.FILE_LEN)
        self.assertGreater(first,0)
        self.assertEqual(live[:first],payload[:first])
        self.assertEqual(live[last:],payload[last:])

    def test_partial_last_sector_is_never_writeable(self):
        altered = bytearray(self.live)
        altered[writer.FILE_LEN-1] ^= 1
        with self.assertRaisesRegex(ValueError,"beyond"):
            writer.write_window(self.live,bytes(altered))

    def test_unpinned_payload_refused(self):
        with self.assertRaisesRegex(ValueError,"not pinned"):
            self.preflight(pins={})

    def test_unknown_live_baseline_refused(self):
        self.live = b"X"+self.live[1:]
        with self.assertRaisesRegex(ValueError,"baseline"):
            self.preflight()

    def test_already_applied_refused(self):
        self.live = self.build+self.tail
        with self.assertRaisesRegex(ValueError,"already holds"):
            self.preflight()

    def test_stock_rollback_over_pinned_build(self):
        self.live = self.build+self.tail
        _,payload,label = self.preflight(build=self.stock)
        self.assertEqual(label,"fixture")
        self.assertEqual(payload,self.stock+self.tail)

    def test_navigation_clip_change_refused_even_if_hash_pinned(self):
        altered = bytearray(self.build)
        altered[self.gid.container_offset+self.gid.clips[20].offset] ^= 1
        with self.assertRaisesRegex(ValueError,"outside"):
            self.preflight(build=bytes(altered),pins={writer.sha(altered):"bad fixture"})

    def test_playlist_edit_refused(self):
        altered = bytearray(self.build)
        altered[self.gid.container_offset+0xe1a0] ^= 4
        with self.assertRaises(ValueError):
            validate(self.stock,bytes(altered),"all")

    def test_slot_overflow_refused(self):
        replacements = {i:(bytes.fromhex("02010102"),b"\0\0") for i in CLIPS}
        replacements[764] = (bytes.fromhex("02010102"),bytes(self.gid.clips[764].padded_size+2))
        with self.assertRaisesRegex(ValueError,"overflow"):
            make_patch(self.stock,replacements,"greeting")

    def test_missing_or_extra_clip_refused(self):
        with self.assertRaisesRegex(ValueError,"56"):
            make_patch(self.stock,{},"greeting")

    def test_ev_build_requires_v11_base_and_preserves_greeting(self):
        with patch.dict(gid_patch.ALLOWED_BASES,{"ev":{writer.sha(self.v11)}},clear=False):
            with self.assertRaisesRegex(ValueError,"base GID"):
                make_patch(self.build,self.ev_replacements,"ev")
            observed = make_patch(self.v11,self.ev_replacements,"ev")
        self.assertEqual(observed,self.v2)
        for i in CLIPS:
            self.assertEqual(observed[self.gid.container_offset+self.gid.clips[i].descriptor:
                                      self.gid.container_offset+self.gid.clips[i].descriptor+16],
                             self.v11[self.gid.container_offset+self.gid.clips[i].descriptor:
                                      self.gid.container_offset+self.gid.clips[i].descriptor+16])

    def test_live_v1_and_v11_baselines_accepted(self):
        pins = {writer.sha(self.v2):"v2", writer.sha(self.build):"v1",
                writer.sha(self.v11):"v11"}
        for live in (self.build,self.v11):
            self.live = live+self.tail
            _,payload,label = self.preflight(build=self.v2,pins=pins)
            self.assertIn(label,("v1","v11"))
            self.assertEqual(payload,self.v2+self.tail)

    def test_ev_outside_allowlist_refused(self):
        altered = bytearray(self.v2)
        altered[self.gid.container_offset+self.gid.clips[20].offset] ^= 1
        with self.assertRaisesRegex(ValueError,"outside"):
            validate(self.stock,bytes(altered),"all")

    def test_ev_missing_or_extra_clip_refused(self):
        with patch.dict(gid_patch.ALLOWED_BASES,{"ev":{writer.sha(self.v11)}},clear=False):
            with self.assertRaisesRegex(ValueError,"41"):
                make_patch(self.v11,{},"ev")
            extra = dict(self.ev_replacements)
            extra[764] = (bytes.fromhex("02010102"),b"\0\0")
            with self.assertRaisesRegex(ValueError,"41"):
                make_patch(self.v11,extra,"ev")

    def test_clip_443_stays_untranslated(self):
        self.assertNotIn(443,EV_CLIPS)
        r=self.gid.clips[443]
        start=self.gid.container_offset
        self.assertEqual(self.v2[start+r.descriptor:start+r.descriptor+16],
                         self.v11[start+r.descriptor:start+r.descriptor+16])
        self.assertEqual(self.v2[start+r.offset:start+r.offset+r.padded_size],
                         self.v11[start+r.offset:start+r.offset+r.padded_size])

    def test_ev_slot_overflow_refused(self):
        replacements = dict(self.ev_replacements)
        replacements[1297] = (bytes.fromhex("02010102"),
                              bytes(self.gid.clips[1297].padded_size+2))
        with patch.dict(gid_patch.ALLOWED_BASES,{"ev":{writer.sha(self.v11)}},clear=False):
            with self.assertRaisesRegex(ValueError,"overflow"):
                make_patch(self.v11,replacements,"ev")

    def test_v2_is_pinned(self):
        self.assertIn("4635b41235237f13492154b40fba35ec3cd9dc297b4752bd9a9dfe9a57c7b090",
                      writer.BUILDS)

    def test_v2_rollback_to_v11_or_stock(self):
        self.live = self.v2+self.tail
        pins = {writer.sha(self.v2):"v2", writer.sha(self.v11):"v11"}
        _,payload,label = self.preflight(build=self.v11,pins=pins)
        self.assertEqual(label,"v2")
        self.assertEqual(payload,self.v11+self.tail)
        _,payload,label = self.preflight(build=self.stock,pins=pins)
        self.assertEqual(payload,self.stock+self.tail)


class LayoutOnImage(unittest.TestCase):
    def test_read_only_fat_chain_and_mirror(self):
        image = Path.home()/"nissan/sdcard/nissan-sd-485-1972-00.img"
        if not image.exists():
            self.skipTest("read-only original not available")
        with image.open("rb") as f:
            self.assertEqual(writer.gid_extent(writer.sector_reader(f)),(writer.OFFSET,writer.FILE_LEN))

    def test_geometry_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError,"MBR"):
            writer.gid_extent(lambda off,n:bytes(n))


class BackupVerification(unittest.TestCase):
    def test_full_hash_is_recomputed_not_just_trusted_from_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            b = root/"card-before-patch.img"
            data = b"A"*1024
            b.write_bytes(data)
            b.chmod(0o444)
            digest = writer.sha(data)
            (root/"backup-report.json").write_text(json.dumps({
                "status":"VERIFIED_READ_ONLY_CARD_BACKUP","bytes":1024,"sha256":digest}))
            with patch.object(writer,"BACKUP_SHAS",{digest}),patch.object(writer,"gid_extent",return_value=(0,1024)),patch.object(
                    writer,"OFFSET",0),patch.object(writer,"FILE_LEN",1024),patch.object(writer,"OUTER_SHA",digest):
                observed,h = writer.verified_backup(b,expected_size=1024)
                self.assertEqual((observed,h),(data,digest))
                b.chmod(0o644)
                b.write_bytes(b"B"*1024)
                b.chmod(0o444)
                with self.assertRaisesRegex(ValueError,"full backup hash"):
                    writer.verified_backup(b,expected_size=1024)


if __name__ == "__main__":
    unittest.main()
