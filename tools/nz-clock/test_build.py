"""Integration checks for the offline ROM builder; originals are read-only.

Requires the existing extracted G214 ROM and candidate-v2/payload.bin under
$NISSAN_ROOT/work. No firmware is executed. Missing local artifacts skip tests.
"""
import importlib.util
import os
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nz_builder", HERE / "build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get("NISSAN_ROOT", "~/nissan")).expanduser()
        source = root / "work/ce-extract/G214JLNI.066.nb0"
        payload = root / "work/nz-clock/candidate-v2/payload.bin"
        if not source.is_file() or not payload.is_file():
            raise unittest.SkipTest("Build candidate-v2 from the local extracted ROM first")
        cls.source = source.read_bytes()
        cls.payload = payload.read_bytes()
        cls.result, cls.report = builder.patch(cls.source, cls.payload)

    def test_reject_unknown_source(self):
        changed = bytearray(self.source)
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "SHA256"):
            builder.patch(changed, self.payload)

    def test_reject_empty_or_oversized_payload(self):
        for data in (b"", b"\0" * 3645):
            with self.assertRaises(ValueError):
                builder.patch(self.source, data)

    def test_stock_metadata_beyond_text_is_preserved(self):
        # Regression for treating psize-vsize as empty padding: it contains
        # other modules' metadata in the original ROM and must not be changed.
        start, end = 0x8c41c4, 0x8c5000
        self.assertTrue(any(self.source[start:end]))
        self.assertEqual(self.source[start:end], self.result[start:end])

    def test_only_metadata_words_change_in_original_extent(self):
        clean = bytearray(self.result[:len(self.source)])
        for start, end in self.report["allowed_ranges"]:
            a, b = int(start, 16), int(end, 16)
            clean[a:b] = self.source[a:b]
        self.assertEqual(clean, self.source)

    def test_relocated_section_and_physical_extent(self):
        rom = builder.ceromx.Rom(self.result)
        self.assertEqual(rom.hdr["physlast"], rom.base + len(self.result))
        module = next(m for m in rom.modules if rom.cstr(m[4]).lower() == "objdll.dll")
        e32 = struct.unpack_from(builder.ceromx.E32_FMT, self.result, rom.off(module[5]))
        self.assertEqual(e32[0], 5)
        table = rom.off(module[6])
        section = struct.unpack_from(builder.ceromx.O32_FMT, self.result, table)
        vsize, rva, psize, dataptr, realaddr, flags = section
        self.assertEqual((vsize, rva, psize, realaddr, flags),
                         (0x9d000, 0x1000, 0x9d000, 0x40e01000, 0x68000020))
        self.assertLessEqual(vsize, psize)
        raw = rom.off(dataptr)
        self.assertEqual(raw, 0x827000)
        tail = struct.unpack_from(builder.ceromx.O32_FMT, self.result, table + 24)
        self.assertEqual(tail[1], rva + vsize)
        self.assertEqual(tail[2], 0x1000)
        self.assertEqual(tail[4], realaddr + vsize)
        self.assertLessEqual(tail[0], tail[2])
        tail_raw = rom.off(tail[3])
        original = 0x827000
        old_vsize = 0x9d1c3
        expected = bytearray(self.source[original:original + old_vsize])
        hook = builder.ENTRY_VA - realaddr
        expected[hook:hook + 4] = self.result[raw + hook:raw + hook + 4]
        actual = self.result[raw:raw + vsize] + self.result[tail_raw:tail_raw + old_vsize - vsize]
        self.assertEqual(expected, actual)
        cave = tail_raw + builder.CAVE_VA - tail[4]
        self.assertEqual(self.result[cave:cave + len(self.payload)], self.payload)
        self.assertLessEqual(len(self.result) - len(self.source), 0x4000)

    def test_wrapper_trampoline_and_return_target(self):
        # Decode the wrapper's BL independently; only the copied two-instruction
        # prologue may precede the branch back into untouched original code.
        call = struct.unpack_from("<I", self.payload, 12)[0]
        self.assertEqual(call >> 24, 0xeb)
        displacement = call & 0xffffff
        if displacement & 0x800000:
            displacement -= 1 << 24
        trampoline = 12 + 8 + displacement * 4
        self.assertEqual(self.payload[trampoline:trampoline + 8], builder.PROLOGUE)
        target = builder.branch_target(builder.CAVE_VA + trampoline + 8,
                                       self.payload[trampoline + 8:trampoline + 12])
        self.assertEqual(target, builder.ENTRY_VA + 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
