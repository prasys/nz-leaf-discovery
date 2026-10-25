"""Host tests for clock.c: python3 -I tools/nz-clock/test_clock.py

Builds the C source into ~/nissan/work/nz-clock (outside the repo) and checks
it via ctypes against zoneinfo Pacific/Auckland.
"""
import ctypes
import os
import struct
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.expanduser(os.environ.get("NISSAN_ROOT", "~/nissan")), "work", "nz-clock")
AKL = ZoneInfo("Pacific/Auckland")
UTC = timezone.utc
HS = 360000  # hundredths of a second per hour


def build():
    os.makedirs(OUT, exist_ok=True)
    so = os.path.join(OUT, "libnzclock.so")
    subprocess.run(
        ["cc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
         "-ffreestanding", "-fno-builtin", "-o", so,
         os.path.join(HERE, "clock.c")], check=True)
    lib = ctypes.CDLL(so)
    lib.nz_apply.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.nz_apply.restype = ctypes.c_int
    return lib


LIB = build()


def mk(y=2026, mo=1, d=1, h=0, mi=0, s=0, valid=1, zone=3240000,
       ztype=0x3d, dst=0, user=0):
    b = bytearray(0x24)
    struct.pack_into("<HBBBBB", b, 0, y, mo, d, h, mi, s)
    struct.pack_into("<I", b, 8, valid)
    struct.pack_into("<i", b, 0x14, zone)
    struct.pack_into("<I", b, 0x18, ztype)
    struct.pack_into("<i", b, 0x1c, dst)
    struct.pack_into("<i", b, 0x20, user)
    return bytes(b)


def apply(obj, init=123456):
    t = ctypes.c_int(init)
    r = LIB.nz_apply(obj, ctypes.byref(t))
    return r, t.value


def expect(dt):
    return int(dt.astimezone(AKL).utcoffset().total_seconds()) * 100


def at(dt, **kw):
    return mk(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, **kw)


class Clock(unittest.TestCase):
    def check(self, dt, **kw):
        r, v = apply(at(dt, **kw))
        self.assertEqual((r, v), (1, expect(dt) + kw.get("user", 0)), dt)

    def test_daily_2008_2099(self):
        dt = datetime(2008, 1, 1, tzinfo=UTC)
        end = datetime(2100, 1, 1, tzinfo=UTC)
        n = 0
        while dt < end:
            for off in (0, 13 * 3600 + 59 * 60 + 59, 86399):
                self.check(dt + timedelta(seconds=off))
                n += 1
            dt += timedelta(days=1)
        self.assertGreater(n, 100000)

    def test_transition_edges(self):
        n = 0
        for y in range(2008, 2100):
            for mo in (3, 4, 9, 10):
                for dd in range(1, 32):
                    try:
                        base = datetime(y, mo, dd, 14, tzinfo=UTC)
                    except ValueError:
                        continue
                    for s in (-2, -1, 0, 1):
                        dt = base + timedelta(seconds=s)
                        self.check(dt)
                        n += 1
        self.assertGreater(n, 0)

    def test_known_edges(self):
        for s, v in (("2026-04-04T13:59:59", 4680000),
                     ("2026-04-04T14:00:00", 4320000),
                     ("2026-09-26T13:59:59", 4320000),
                     ("2026-09-26T14:00:00", 4680000)):
            dt = datetime.fromisoformat(s).replace(tzinfo=UTC)
            self.assertEqual(apply(at(dt)), (1, v), s)

    def test_rollovers(self):
        for dt in (datetime(2024, 2, 29, 23, 59, 59, tzinfo=UTC),
                   datetime(2100 - 1, 12, 31, 23, 59, 59, tzinfo=UTC),
                   datetime(2008, 1, 1, tzinfo=UTC),
                   datetime(2028, 2, 29, 12, tzinfo=UTC),
                   datetime(2096, 2, 29, 12, tzinfo=UTC)):
            self.check(dt)

    def test_user_offset_and_old_dst(self):
        summer = datetime(2026, 1, 15, 3, tzinfo=UTC)
        winter = datetime(2026, 7, 15, 3, tzinfo=UTC)
        for user in (0, 6000, -6000, 59 * 6000, -59 * 6000, 3 * HS, -12 * HS):
            for dst in (0, HS, 12345):
                self.check(summer, user=user, dst=dst)
                self.check(winter, user=user, dst=dst)
        self.assertEqual(apply(at(winter, user=30 * 6000, dst=HS)),
                         (1, 4320000 + 180000))

    def test_malformed_dates(self):
        bad = [mk(2026, 0, 1), mk(2026, 13, 1), mk(2026, 1, 0), mk(2026, 1, 32),
               mk(2026, 4, 31), mk(2026, 2, 29), mk(2100, 2, 29),
               mk(2026, 1, 1, 24), mk(2026, 1, 1, 0, 60), mk(2026, 1, 1, 0, 0, 60),
               mk(2007, 12, 31, 23, 59, 59), mk(2100, 1, 1), mk(0, 1, 1),
               mk(65535, 1, 1), mk(2026, 1, 1, 255, 255, 255)]
        for o in bad:
            self.assertEqual(apply(o), (0, 123456), o[:7].hex())

    def test_null(self):
        t = ctypes.c_int(7)
        self.assertEqual(LIB.nz_apply(None, ctypes.byref(t)), -2)
        self.assertEqual(t.value, 7)
        self.assertEqual(LIB.nz_apply(mk(), None), -2)
        self.assertEqual(LIB.nz_apply(None, None), -2)

    def test_non_jp_and_invalid_clock(self):
        for kw in (dict(ztype=0x3e), dict(ztype=0), dict(zone=0),
                   dict(zone=4320000), dict(zone=3240001),
                   dict(valid=0), dict(valid=2), dict(valid=0x80000001)):
            self.assertEqual(apply(mk(**kw)), (0, 123456), kw)
        self.assertEqual(apply(mk()), (1, 4680000))

    def test_overflow(self):
        big = 0x7fffffff
        self.assertEqual(apply(mk(user=big)), (0, 123456))
        self.assertEqual(apply(mk(user=big - 4680000 + 1)), (0, 123456))
        self.assertEqual(apply(mk(user=big - 4680000)), (1, big))
        self.assertEqual(apply(mk(user=-big - 1)), (1, 4680000 - big - 1))
        self.assertEqual(apply(mk(user=-big)), (1, 4680000 - big))


if __name__ == "__main__":
    unittest.main(verbosity=2)
