#!/usr/bin/env python3 -I
"""Host reference for a proposed NZ HMI clock; never reads or writes firmware.

Uses the mainland NZ rule in force since 2008, extrapolated to the input year.
--verify compares it with the host's independent Pacific/Auckland tzdata.
"""
import argparse
import calendar
from datetime import datetime, timedelta, timezone
import json

UTC = timezone.utc
HOUR = 360000  # OBJDLL uses hundredths of a second, not seconds.


def transition(year, month, last):
    """Both transitions are at 02:00 NZST == 14:00 UTC the previous day."""
    day = calendar.monthrange(year, month)[1] if last else 1
    date = datetime(year, month, day, 2, tzinfo=timezone(timedelta(hours=12)))
    distance = (date.weekday() - 6) % 7 if last else (6 - date.weekday()) % 7
    date += timedelta(days=-distance if last else distance)
    return date.astimezone(UTC)


def nz_hours(instant):
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("An explicit UTC offset is required")
    instant = instant.astimezone(UTC)
    if instant.year < 2008:
        raise ValueError("This model supports the rules from 2008 onwards")
    end = transition(instant.year, 4, False)
    start = transition(instant.year, 9, True)
    return 12 if end <= instant < start else 13


def verify():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("Pacific/Auckland")
    count = 0
    # Daily samples plus seconds either side of every transition, 2008–2037.
    samples = []
    for year in range(2008, 2038):
        date = datetime(year, 1, 1, tzinfo=UTC)
        while date.year == year:
            samples.append(date)
            date += timedelta(days=1)
        for month, last in ((4, False), (9, True)):
            boundary = transition(year, month, last)
            samples.extend(boundary + timedelta(seconds=n) for n in (-1, 0, 1))
    for instant in samples:
        expected = int(instant.astimezone(zone).utcoffset().total_seconds())
        actual = nz_hours(instant) * 3600
        if actual != expected:
            raise AssertionError((instant.isoformat(), actual, expected))
        count += 1
    print(f"Verified {count} UTC instants against Pacific/Auckland (2008–2037)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("utc", nargs="?", help="ISO timestamp with Z or explicit offset")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify()
    if args.utc:
        try:
            instant = datetime.fromisoformat(args.utc.replace("Z", "+00:00"))
            hours = nz_hours(instant)
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps({
            "utc": instant.astimezone(UTC).isoformat(),
            "nz_local": instant.astimezone(timezone(timedelta(hours=hours))).isoformat(),
            "proposed_zone_centiseconds": 12 * HOUR,
            "proposed_dst_centiseconds": (hours - 12) * HOUR,
            "extra_hours_over_jst": hours - 9,
        }, indent=2))
    elif not args.verify:
        parser.error("provide a UTC timestamp or --verify")


if __name__ == "__main__":
    main()
