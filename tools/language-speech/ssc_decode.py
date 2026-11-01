#!/usr/bin/env python3
"""Static Python port of Speech.exe's mono SSC decoder; never executes firmware.

Run with python3 -I. Codebooks/window are read as data from the hash-pinned,
E8-corrected PE produced by extract_speech.py. Output stays outside the repo.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gid_catalog import Gid, span

SPEECH_SHA256 = "5a43580038282eeea0a4862ae83cc78a8b040cf6415bce9f01b78463a10c92a6"


def i32(x):
    return ((x + 0x80000000) & 0xffffffff) - 0x80000000


def mul(a, b):
    # FUN_001cf9ac: signed 64-bit product, rounded high word.
    return i32((a * b + 0x80000000) >> 32)


class Bits:
    def __init__(self, data):
        self.data, self.position = data, 0

    def read(self, n):
        if not 0 <= n <= 32 or self.position + n > len(self.data) * 8:
            raise ValueError(f"truncated/invalid SSC bitstream at bit {self.position}")
        value = 0
        for _ in range(n):
            value = (value << 1) | ((self.data[self.position >> 3] >> (7-(self.position & 7))) & 1)
            self.position += 1
        return value


class Tables:
    def __init__(self, data):
        if hashlib.sha256(data).hexdigest() != SPEECH_SHA256:
            raise ValueError("Speech.exe hash mismatch; use extract_speech.py")
        def read(va, size):
            # All codebooks are in this pinned PE's first section.
            return span(data, va - 0x11000 + 0x400, size)
        self.bands = struct.unpack("<16I", read(0x6abd0, 64))
        self.radix = (0, 3, 3, 9, 8, 13, 17)
        self.bias = (0, 1, 0, 4, 0, 0, 0)
        self.codes = {}
        for mode, delta in enumerate((0, 0x148, 0x290, 0x3d8, 0x4e0, 0), 1):
            address = 0x6c050 if mode == 6 else 0x6b8c8 + delta
            size = 6 if mode == 6 else 4
            codes = {}
            for j in range(1024):
                row = read(address + j*size, size)
                symbol, length, code = struct.unpack("<3H" if mode == 6 else "<BBH", row)
                if length >= 20:
                    break
                if not 1 <= length < 20 or code >= 1 << length or (length, code) in codes:
                    raise ValueError("invalid SSC codebook")
                codes[length, code] = symbol
            else:
                raise ValueError("unterminated SSC codebook")
            self.codes[mode] = codes
        self.rotation = struct.unpack("<128i", read(0x6c920, 512))
        self.twiddle = struct.unpack("<128i", read(0x6c720, 512))
        self.window = struct.unpack("<128i", read(0x6cb20, 512))

    def symbol(self, bits, mode):
        code = 0
        for length in range(1, 20):
            code = code * 2 + bits.read(1)
            symbol = self.codes[mode].get((length, code))
            if symbol is not None:
                return symbol
        raise ValueError("invalid SSC Huffman code")


def coefficients(bits, tables):
    # FUN_001d02f8: 15 allocation modes, entropy-coded vectors, scale factors.
    modes = []
    for band in range(15):
        mode = bits.read(3)
        if mode == 7:
            if band == 0:
                return None  # end marker
            if band == 1:
                return []  # zero block: flush overlap
            raise ValueError("SSC marker in invalid band")
        modes.append(mode)
    values = [0] * 128
    for band, mode in enumerate(modes):
        if mode == 0:
            continue
        group = 4 if mode < 3 else 2
        radix, bias = tables.radix[mode], tables.bias[mode]
        for start in range(tables.bands[band], tables.bands[band+1], group):
            value = tables.symbol(bits, mode)
            vector = [0] * group
            for j in range(group-1, -1, -1):
                vector[j] = value % radix - bias
                value //= radix
            if value:
                raise ValueError("SSC vector outside radix")
            if mode in (2, 4, 5, 6):
                vector = [-x if x and bits.read(1) else x for x in vector]
            if mode == 6:
                for j, x in enumerate(vector):
                    if abs(x) == 16:
                        width = 4
                        while bits.read(1):
                            width += 1
                            if width > 31:
                                raise ValueError("SSC escape exceeds 32 bits")
                        magnitude = (1 << width) + bits.read(width)
                        vector[j] = -magnitude if x < 0 else magnitude
            values[start:start+group] = vector
    scale = bits.read(5)
    scales = [scale]
    for _ in range(14):
        scale += bits.read(3) - 5
        scale = ((scale + 128) & 255) - 128
        scales.append(scale)
    for band, scale in enumerate(scales):
        for j in range(tables.bands[band], tables.bands[band+1]):
            x = values[j]
            if abs(x) > 1:
                x = (1 if x > 0 else -1) * (abs(x)*2 - 2)
            # ARM register shift counts >=32 produce zero, including negative s8.
            values[j] = i32(x << (scale + 10)) if 0 <= scale < 32 else 0
    return values


def rotate(a, rotation):
    for j in range(0, 128, 2):
        x, y, c, s = a[j], a[j+1], rotation[j], rotation[j+1]
        a[j] = i32(mul(x, c) - mul(y, s))
        a[j+1] = i32(mul(y, c) + mul(x, s))


def transform(a, overlap, tables):
    # FUN_001d0bfc, FUN_001cfce8, FUN_001d0830: 128-sample lapped transform.
    for j in range(0, 128, 2):
        a[j] = i32(-a[j])
    a[1::2] = a[1::2][::-1]
    rotate(a, tables.rotation)
    for j in range(64):
        reverse = int(f"{j:06b}"[::-1], 2)
        if j < reverse:
            a[2*j:2*j+2], a[2*reverse:2*reverse+2] = a[2*reverse:2*reverse+2], a[2*j:2*j+2]
    for j in range(0, 128, 4):
        x, y, u, v = a[j:j+4]
        a[j:j+4] = [i32(x+u), i32(y+v), i32(x-u), i32(y-v)]
    for stage in range(1, 6):
        half = 1 << stage
        for j in range(half):
            c = tables.twiddle[j * (128 >> stage)]
            s = -tables.twiddle[j * (128 >> stage)+1]
            for left in range(2*j, 128, half*4):
                right = left + half*2
                x, y = a[left] >> 1, a[left+1] >> 1
                if j == 0:
                    u, v = a[right] >> 1, a[right+1] >> 1
                else:
                    u = i32(mul(a[right], c) - mul(a[right+1], s))
                    v = i32(mul(a[right+1], c) + mul(a[right], s))
                a[left], a[left+1] = i32(x+u), i32(y+v)
                a[right], a[right+1] = i32(x-u), i32(y-v)
    rotate(a, tables.rotation)
    window = tables.window
    output, pending = [], []
    clip = lambda x: max(-32768, min(32767, x))
    for j in range(32):
        output.extend([clip(overlap[2*j] + mul(-a[64+2*j], window[2*j])),
                       clip(overlap[2*j+1] + mul(-a[63-2*j], window[2*j+1]))])
    for j in range(32):
        output.extend([clip(overlap[64+2*j] + mul(a[1+2*j], window[64+2*j])),
                       clip(overlap[65+2*j] + mul(a[126-2*j], window[65+2*j]))])
    for j in range(32):
        pending.extend([mul(a[65+2*j], window[127-2*j]), mul(a[62-2*j], window[126-2*j])])
    for j in range(32):
        pending.extend([mul(a[2*j], window[63-2*j]), mul(a[127-2*j], window[62-2*j])])
    return output, pending


def decode(data, tables):
    bits, overlap, pcm = Bits(data), [0] * 128, bytearray()
    blocks = 0
    while True:
        values = coefficients(bits, tables)
        if values is None:
            break
        if values:
            samples, overlap = transform(values, overlap, tables)
        else:
            samples, overlap = [max(-32768, min(32767, x)) for x in overlap], [0]*128
        pcm.extend(struct.pack("<128h", *samples))
        blocks += 1
        if blocks > 100000:
            raise ValueError("SSC clip exceeds block limit")
    if len(data)*8 - bits.position > 7:
        raise ValueError("unexpected bytes following SSC end marker")
    return bytes(pcm)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gid", type=Path)
    ap.add_argument("speech_exe", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--clips", help="comma-separated zero-based clip indices; default all")
    ap.add_argument("--rate", type=int, help="override the descriptor rate for listening experiments")
    args = ap.parse_args()
    if not args.output.resolve().is_relative_to(Path.home()/"nissan/work/language-speech"):
        ap.error("output must be under ~/nissan/work/language-speech/")
    gid, tables = Gid(args.gid.read_bytes()), Tables(args.speech_exe.read_bytes())
    selected = [int(s) for s in args.clips.split(",")] if args.clips else range(len(gid.clips))
    args.output.mkdir(parents=True, exist_ok=True)
    for i in selected:
        c = gid.clips[i]
        source = span(gid.data, c.offset, c.size)
        if c.format == bytes.fromhex("02040102"):
            pcm = decode(source, tables)
        elif c.format in (bytes.fromhex("02010102"), bytes.fromhex("02010101")):
            # Raw silence entries can have an odd byte length; retain complete samples.
            pcm = source[:len(source) & ~1]
        else:
            print(f"skip clip {i}: unsupported format {c.format.hex()}", file=sys.stderr)
            continue
        rate = args.rate or {1: 11025, 2: 22050}[c.format[3]]
        target = args.output / f"clip{i:04d}.wav"
        if target.exists():
            raise ValueError(f"refusing to overwrite {target}")
        with wave.open(str(target), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        print(f"{i}\t{c.offset:#x}\t{len(pcm)//2}\t{len(pcm)/2/rate:.6f}\t{hashlib.sha256(pcm).hexdigest()}", flush=True)


if __name__ == "__main__":
    main()
