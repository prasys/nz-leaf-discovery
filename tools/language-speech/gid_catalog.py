#!/usr/bin/env python3
"""Read-only, bounds-checked GID inventory. Run with python3 -I.

Accepts SJP00000.GID or its SJP00300.GID wrapper. Offsets in reports are
member-relative unless explicitly named container_offset. No names/phonebooks
are read. The archive contains no textual transcript.
"""
import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct


def span(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"GID range outside file: {offset:#x}+{size:#x}")
    return data[offset:offset + size]


@dataclass(frozen=True)
class Clip:
    index: int
    descriptor: int
    format: bytes
    offset: int
    padded_size: int
    size: int


class Gid:
    def __init__(self, data):
        self.container_offset = 0
        if data[:16].isdigit():
            total, first, _, count = struct.unpack("<4I", span(data, 16, 16))
            if count != 1 or total != len(data) or first != 56:
                raise ValueError("not the supported one-member GID archive")
            entry = span(data, 32, 24)
            if entry[:12].rstrip(b"\0 ") != b"SJP00000.GID":
                raise ValueError("unexpected archive member")
            start, padded, size = struct.unpack_from("<3I", entry, 12)
            if start < first or size > padded:
                raise ValueError("invalid member extent")
            self.container_offset = start
            data = span(data, start, size)
        self.data = data
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.header = struct.unpack("<9I", span(data, 0, 36))
        count, playlist_start = self.header[:2]
        if not 2 <= count <= 100000 or 64 + 4 * count > playlist_start:
            raise ValueError("invalid phrase boundary count")
        self.boundaries = struct.unpack(f"<{count}I", span(data, 64, 4 * count))
        if self.boundaries[0] != playlist_start or any(
            a > b or a % 4 or b % 4 for a, b in zip(self.boundaries, self.boundaries[1:])
        ):
            raise ValueError("invalid phrase boundaries")
        self.clip_header = playlist_start + self.header[2]
        if (self.clip_header % 32 or self.boundaries[-1] > self.clip_header
                or any(x < playlist_start for x in self.boundaries)):
            raise ValueError("invalid playlist extent")
        n, desc_bytes, audio_bytes, _, alignment = struct.unpack(
            "<5I", span(data, self.clip_header, 20))
        if (not 1 <= n <= 100000 or alignment != 4 or desc_bytes < 32 + n * 16
                or self.clip_header + desc_bytes + audio_bytes != len(data)):
            raise ValueError("invalid clip directory")
        self.clips = []
        first_desc = self.clip_header + 32
        span(data, first_desc, n * 16)
        for i in range(n):
            desc = first_desc + i * 16
            fmt, offset, padded, size = struct.unpack("<4sIII", span(data, desc, 16))
            if size > padded or offset < first_desc + n * 16 or offset % 4 or padded % 4:
                raise ValueError("invalid clip extent/alignment")
            span(data, offset, padded)
            self.clips.append(Clip(i, desc, fmt, offset, padded, size))
        self.by_descriptor = {c.descriptor: c for c in self.clips}
        for i in range(len(self.boundaries) - 1):
            self.playlist(i)

    def playlist(self, index):
        if not 0 <= index < len(self.boundaries) - 1:
            raise ValueError("phrase outside boundary table")
        start, end = self.boundaries[index:index + 2]
        words = struct.unpack(f"<{(end-start)//4}I", span(self.data, start, end-start))
        for value in words:
            if not value & 0x80000000 and value not in self.by_descriptor:
                raise ValueError(f"unknown clip descriptor {value:#x}")
        return words

    def tokens(self, index):
        return [f"silence:{v & 0x7fffffff}ms" if v & 0x80000000
                else f"clip:{self.by_descriptor[v].index}" for v in self.playlist(index)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gid", type=Path)
    ap.add_argument("--clips", type=Path)
    ap.add_argument("--phrases", type=Path)
    args = ap.parse_args()
    gid = Gid(args.gid.read_bytes())
    for path in (args.clips, args.phrases):
        if path and path.resolve() == args.gid.resolve():
            ap.error("output must differ from input")
        if path and (path.suffix.lower()==".img" or path.resolve().is_relative_to(
                Path.home()/"nissan/sdcard")):
            ap.error("refusing output to an image/originals directory")
    if args.clips:
        with args.clips.open("w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["clip", "descriptor_offset", "format", "audio_offset", "padded_size", "size"])
            for c in gid.clips:
                w.writerow([c.index, hex(c.descriptor), c.format.hex(), hex(c.offset), c.padded_size, c.size])
    if args.phrases:
        with args.phrases.open("w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["phrase_id", "boundary_offset", "playlist_offset", "tokens"])
            for i in range(len(gid.boundaries) - 1):
                w.writerow([hex(i), hex(64 + i*4), hex(gid.boundaries[i]), " ".join(gid.tokens(i))])
    nonempty = sum(bool(gid.playlist(i)) for i in range(len(gid.boundaries) - 1))
    print(json.dumps({"member_sha256": gid.sha256, "container_offset": gid.container_offset,
                      "member_size": len(gid.data), "boundary_count": len(gid.boundaries),
                      "phrase_slots": len(gid.boundaries)-1, "nonempty_phrases": nonempty,
                      "clips": len(gid.clips), "formats": dict(Counter(c.format.hex() for c in gid.clips)),
                      "clip_header": hex(gid.clip_header)}, indent=2))


if __name__ == "__main__":
    main()
