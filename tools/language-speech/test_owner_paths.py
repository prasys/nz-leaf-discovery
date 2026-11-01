#!/usr/bin/env python3
"""Paths for other owners: own wording, imported TTS, clip packs, pins.

Ordinary temporary files only; never a device or the card image for writing.
Run: python3 -I tools/language-speech/test_owner_paths.py
"""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clip_pack
import greeting
import import_wavs
import write_gid as writer
from gid_patch import OUTER_SHA, patch as make_patch, sha, validate
from greeting import CLIP_SETS, ENGLISH, locked_text

WORK = greeting.WORK/"language-speech"
STOCK = WORK/"SJP00300.GID"
IMAGE = Path(os.environ.get("NISSAN_IMG", Path.home()/"nissan/sdcard/nissan-sd-485-1972-00.img"))
PCM = bytes.fromhex("02010102")


def own_file(d, changes):
    path = Path(d)/"wording.tsv"
    rows = {**ENGLISH, **changes}
    path.write_text("clip\ten_nz\n"+"".join(f"{i}\t{t}\n" for i, t in rows.items()))
    return path


class OwnWording(unittest.TestCase):
    def test_kia_ora_replaces_hello_only_with_voice_wording(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ, {"VOICE_WORDING": str(own_file(d, {765: "Kia ora."}))}):
                text = locked_text("greeting")
            self.assertEqual(text[765], "Kia ora.")
            self.assertEqual(text[764], "Good morning.")
        self.assertEqual(locked_text("greeting")[765], "Hello.")

    def test_missing_or_non_english_rows_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = own_file(d, {766: "こんばんは"})
            with self.assertRaisesRegex(ValueError, "766"):
                greeting.own_wording(path, "greeting")
            path.write_text("clip\ten_nz\n764\tGood morning.\n")
            with self.assertRaisesRegex(ValueError, "765"):
                greeting.own_wording(path, "greeting")


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class ImportWavs(unittest.TestCase):
    def test_any_rate_stereo_input_becomes_receipted_22050_mono(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/"clip0764.flac"
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=0.5:sample_rate=44100", "-ac", "2", str(src)], check=True)
            data, meta = import_wavs.receipt("Good morning.", "test:sine", import_wavs.to_pcm(src), "0"*64)
            self.assertEqual(meta["frames"], 11025)
            self.assertEqual(meta["wav_sha256"], sha(data))
            self.assertEqual(meta["output_format"], "pcm_22050")
            out = Path(d)/"clip0764.json"
            out.write_text(json.dumps(meta))
            (Path(d)/"clip0764.wav").write_bytes(data)
            from prepare_greeting import read_generated
            samples, label, _ = read_generated(Path(d), 764, "Good morning.")
            self.assertEqual((len(samples), label), (11025, "test:sine"))

    def test_duplicate_or_missing_source_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "exactly one"):
                import_wavs.source_for(Path(d), 764)
            (Path(d)/"clip0764.wav").write_bytes(b"x")
            (Path(d)/"clip0764.mp3").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                import_wavs.source_for(Path(d), 764)


@unittest.skipUnless(STOCK.exists(), "stock GID fixture outside git unavailable")
class PacksAndBases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = STOCK.read_bytes()
        cls.greet = make_patch(cls.stock, {i: (PCM, b"\1\0") for i in CLIP_SETS["greeting"]}, "greeting")

    def test_ev_on_stock_or_own_greeting_needs_the_stock_file(self):
        ev = {i: (PCM, b"\2\0") for i in CLIP_SETS["ev"]}
        with self.assertRaisesRegex(ValueError, "base"):
            make_patch(self.greet, ev, "ev")
        for base in (self.stock, self.greet):
            build = make_patch(base, ev, "ev", self.stock)
            validate(self.stock, build, "all")

    def test_ev_base_with_navigation_change_refused(self):
        bad = bytearray(self.greet)
        bad[-1] ^= 1
        with self.assertRaises(ValueError):
            make_patch(bytes(bad), {i: (PCM, b"\2\0") for i in CLIP_SETS["ev"]}, "ev", self.stock)

    def pack(self, d, replacements, base, clip_set):
        build = make_patch(base, replacements, clip_set, self.stock)
        pack = Path(d)/"pack"
        (pack/"clips").mkdir(parents=True)
        clips = {}
        for i, (fmt, audio) in replacements.items():
            (pack/"clips"/f"clip{i:04d}.bin").write_bytes(audio)
            clips[str(i)] = {"en_nz": "x", "format": fmt.hex(), "bytes": len(audio), "sha256": sha(audio)}
        (pack/"manifest.json").write_text(json.dumps({
            "pack_version": 1, "clip_set": clip_set, "base_gid_sha256": sha(base),
            "build_sha256": sha(build), "clips": clips}))
        return pack, build

    def test_pack_rebuilds_exact_hash_and_refuses_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            pack, build = self.pack(d, {i: (PCM, b"\1\0") for i in CLIP_SETS["greeting"]}, self.stock, "greeting")
            stock = Path(d)/"stock.GID"
            stock.write_bytes(self.stock)
            report = clip_pack.build(pack, stock, None, Path(d)/"out")
            self.assertEqual(report["build_sha256"], sha(build))
            self.assertEqual((Path(d)/"out/SJP00300.GID").read_bytes(), build)
            (pack/"clips/clip0764.bin").write_bytes(b"\3\0")
            with self.assertRaisesRegex(ValueError, "764"):
                clip_pack.build(pack, stock, None, Path(d)/"out2")

    def test_pack_refuses_non_stock_gid_and_wrong_base(self):
        with tempfile.TemporaryDirectory() as d:
            pack, _ = self.pack(d, {i: (PCM, b"\2\0") for i in CLIP_SETS["ev"]}, self.greet, "ev")
            stock, other = Path(d)/"stock.GID", Path(d)/"other.GID"
            stock.write_bytes(self.stock)
            other.write_bytes(b"X"+self.stock[1:])
            with self.assertRaisesRegex(ValueError, "not the stock"):
                clip_pack.build(pack, other, None, Path(d)/"o1")
            with self.assertRaisesRegex(ValueError, "needs base"):
                clip_pack.build(pack, stock, None, Path(d)/"o2")

    def test_list_covers_every_clip_with_slot_sizes(self):
        for clip_set, clips in CLIP_SETS.items():
            rows = list(clip_pack.list_clips(clip_set))
            self.assertEqual([r["clip"] for r in rows], list(clips))
            self.assertTrue(all(r["slot_bytes"] > 0 and float(r["approx_ssc_seconds"]) > 0 for r in rows))


class Pins(unittest.TestCase):
    def test_pins_file_schema(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"pins.json"
            good = {"card_bytes": 31914983424, "backup_sha256": ["a"*64], "builds": {"b"*64: "mine"}}
            p.write_text(json.dumps(good))
            self.assertEqual(writer.load_pins(p)["card_bytes"], 31914983424)
            for bad in ({**good, "backup_sha256": []}, {**good, "card_bytes": "16GB"},
                        {**good, "builds": {"XYZ": "bad"}}, {**good, "card_bytes": 1000}):
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    writer.load_pins(p)

    def test_owner_backup_hash_replaces_ours(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)/"card-before-patch.img"
            b.write_bytes(b"A"*1024)
            b.chmod(0o444)
            (Path(d)/"backup-report.json").write_text(json.dumps({
                "status": "VERIFIED_READ_ONLY_CARD_BACKUP", "bytes": 1024, "sha256": sha(b"A"*1024)}))
            with self.assertRaisesRegex(ValueError, "pinned read-only"):
                writer.verified_backup(b, 1024)
            with patch.object(writer, "gid_extent", return_value=(0, 1024)), patch.object(
                    writer, "FILE_LEN", 1024), patch.object(writer, "OUTER_SHA", sha(b"A"*1024)):
                self.assertEqual(writer.verified_backup(b, 1024, {sha(b"A"*1024)}, False)[0], b"A"*1024)

    @unittest.skipUnless(IMAGE.exists(), "read-only analysis image unavailable")
    def test_discovered_geometry_matches_pinned_on_our_image(self):
        with IMAGE.open("rb") as f:
            read = writer.sector_reader(f)
            self.assertEqual(writer.gid_extent(read, False, IMAGE.stat().st_size), writer.gid_extent(read, True))

    def test_unpinned_mode_still_needs_fat32(self):
        mbr = bytearray(512)
        mbr[454:458] = (2048).to_bytes(4, "little")
        mbr[510:] = b"\x55\xaa"
        def read(off, n):
            return bytes(mbr[:n]) if off == 0 else bytes(n)
        with self.assertRaisesRegex(ValueError, "FAT32"):
            writer.gid_extent(read, False, 1 << 34)
        with self.assertRaisesRegex(ValueError, "MBR"):
            writer.gid_extent(read, True)



class ElevenModel(unittest.TestCase):
    def test_other_model_is_sent_without_speaker_boost(self):
        import eleven_greeting as api
        for model, boost in ((api.MODEL, True), ("eleven_v3", None)):
            with patch.object(api, "request", return_value=b"\0\0"*100) as request:
                _, meta = api.synthesize("Good morning.", "A"*20, "greeting", model)
            body = request.call_args[0][1]
            self.assertEqual((body["model_id"], meta["model_id"]), (model, model))
            self.assertEqual(body["voice_settings"].get("use_speaker_boost"), boost)
        with self.assertRaisesRegex(ValueError, "model"):
            api.synthesize("Good morning.", "A"*20, "greeting", "gpt-4o-tts")


def fat32_card(spc=64, partition_sectors=100000, total=100000, card_sectors=1 << 20, other=None):
    """In-memory MBR + FAT32 with SPEECH/JP/GID/SJP00300.GID contiguous (no audio)."""
    p1, reserved, fatsz = 2048, 2, 2048
    fat0 = (p1+reserved)*512
    data0 = fat0+2*fatsz*512
    csz = spc*512
    fat = bytearray(fatsz*512)
    struct.pack_into("<II", fat, 0, 0xffffff8, 0xfffffff)
    for c in range(2, 6):
        struct.pack_into("<I", fat, c*4, 0xfffffff)
    run = (writer.FILE_LEN+csz-1)//csz
    for c in range(6, 6+run):
        struct.pack_into("<I", fat, c*4, c+1 if c < 5+run else 0xfffffff)

    def entry(name, ext, c, size, isdir):
        e = bytearray(32)
        e[:11] = (name.ljust(8)+ext.ljust(3)).encode()
        e[11] = 16 if isdir else 32
        struct.pack_into("<H", e, 26, c)
        struct.pack_into("<I", e, 28, size)
        return e

    mbr = bytearray(512)
    mbr[450] = 0x0c
    struct.pack_into("<II", mbr, 454, p1, partition_sectors)
    if other:
        struct.pack_into("<II", mbr, 446+16+8, *other)
    mbr[510:] = b"\x55\xaa"
    bpb = bytearray(512)
    struct.pack_into("<HBHB", bpb, 11, 512, spc, reserved, 2)
    struct.pack_into("<I", bpb, 32, total)
    struct.pack_into("<I", bpb, 36, fatsz)
    struct.pack_into("<I", bpb, 44, 2)
    bpb[82:90] = b"FAT32   "
    segments = [(0, mbr), (p1*512, bpb), (fat0, fat), (fat0+len(fat), fat),
                (data0, entry("SPEECH", "", 3, 0, True)), (data0+csz, entry("JP", "", 4, 0, True)),
                (data0+2*csz, entry("GID", "", 5, 0, True)),
                (data0+3*csz, entry("SJP00300", "GID", 6, writer.FILE_LEN, False))]

    def read(o, n):
        out = bytearray(n)
        for start, data in segments:
            lo, hi = max(o, start), min(o+n, start+len(data))
            if lo < hi:
                out[lo-o:hi-o] = data[lo-start:hi-start]
        return bytes(out)
    return read, card_sectors*512, data0+4*csz


class DiscoveredGeometry(unittest.TestCase):
    def test_16k_and_32k_clusters_accepted(self):
        for spc in (32, 64):
            read, size, offset = fat32_card(spc=spc)
            self.assertEqual(writer.gid_extent(read, False, size), (offset, writer.FILE_LEN))

    def test_volume_larger_than_partition_refused(self):
        read, size, _ = fat32_card(partition_sectors=100, total=10000000)
        with self.assertRaisesRegex(ValueError, "fit its partition"):
            writer.gid_extent(read, False, size)

    def test_partition_past_card_end_refused(self):
        read, _, _ = fat32_card()
        with self.assertRaisesRegex(ValueError, "inside the card"):
            writer.gid_extent(read, False, 50000*512)

    def test_overlapping_partition_refused(self):
        read, size, _ = fat32_card(other=(50000, 1000))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            writer.gid_extent(read, False, size)

    def test_gid_past_volume_end_refused(self):
        read, size, _ = fat32_card(partition_sectors=76000, total=76000)
        with self.assertRaises(ValueError):
            writer.gid_extent(read, False, size)

    def test_card_size_is_required(self):
        read, _, _ = fat32_card()
        with self.assertRaisesRegex(ValueError, "card size"):
            writer.gid_extent(read, False)


if __name__ == "__main__":
    unittest.main()
