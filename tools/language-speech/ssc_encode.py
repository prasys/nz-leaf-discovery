#!/usr/bin/env python3
"""Experimental mono SSC encoder, written here; never executes firmware.

Analysis follows Speech.exe!0x1d0f44 (window/folding) and !0x1d09e8
(conjugate butterfly). Entropy packing inverts the proven decoder's codebooks.
Quantisation/rate selection is our simple policy, not the stock psychoacoustic
encoder. Local round-trip checks are required; car acceptance remains untested.
"""
import math
import struct

from ssc_decode import i32, mul, decode


class Writer:
    def __init__(self):
        self.buffer = 0
        self.count = 0
        self.data = bytearray()

    def put(self, value, width):
        if width < 0 or value < 0 or value >= 1 << width:
            raise ValueError("invalid SSC output bits")
        self.buffer = (self.buffer << width) | value
        self.count += width
        while self.count >= 8:
            self.count -= 8
            self.data.append((self.buffer >> self.count) & 255)
        self.buffer &= (1 << self.count) - 1

    def finish(self):
        self.put(7, 3)
        if self.count:
            self.put(0, 8-self.count)
        return bytes(self.data)


def conjugate_rotate(a, rotation):
    for j in range(0, 128, 2):
        x, y, c, s = a[j], a[j+1], rotation[j], rotation[j+1]
        a[j] = i32(mul(x, c) + mul(y, s))
        a[j+1] = i32(mul(y, c) - mul(x, s))


def analysis(current, previous, tables):
    temp = [0] * 256
    for j in range(128):
        temp[j] = mul(previous[j], tables.window[j])
        temp[255-j] = mul(current[127-j], tables.window[j])
    a = [0] * 128
    for j in range(32):
        a[2*j] = temp[192+2*j] + temp[191-2*j]
        a[2*j+1] = temp[64+2*j] - temp[63-2*j]
        a[64+2*j] = temp[127-2*j] - temp[2*j]
        a[65+2*j] = temp[255-2*j] + temp[128+2*j]
    conjugate_rotate(a, tables.rotation)
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
            s = tables.twiddle[j * (128 >> stage)+1]
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
    conjugate_rotate(a, tables.rotation)
    result = [0] * 128
    for j in range(64):
        result[2*j] = -a[2*j]
        result[127-2*j] = a[2*j+1]
    return result


def quantise(values, tables, coarse):
    scales, quant = [], []
    for first, last in zip(tables.bands, tables.bands[1:]):
        band = values[first:last]
        peak = max(map(abs, band), default=0)
        scale = max(0, peak.bit_length()-5+coarse)
        if scales:
            scale = max(scales[-1]-5, min(scales[-1]+2, scale))
        scale = min(31, scale)
        scales.append(scale)
        for v in band:
            magnitude = abs(v) / (1 << scale)
            q = round(magnitude) if magnitude < 1.5 else round(magnitude/2)+1
            quant.append(-q if v < 0 else q)
    return scales, quant


def block_bits(scales, quant, tables, inverse):
    w = Writer()
    modes = []
    for first, last in zip(tables.bands, tables.bands[1:]):
        peak = max(map(abs, quant[first:last]), default=0)
        mode = next((m for m, limit in enumerate((0,1,2,4,7,12,0x7fffffff)) if peak <= limit), None)
        modes.append(mode)
        w.put(mode, 3)
    for band, mode in enumerate(modes):
        if not mode:
            continue
        group = 4 if mode < 3 else 2
        radix, bias = tables.radix[mode], tables.bias[mode]
        for first in range(tables.bands[band], tables.bands[band+1], group):
            values = quant[first:first+group]
            unsigned = mode in (2,4,5,6)
            symbol = 0
            for v in values:
                digit = abs(v) if unsigned else v + bias
                if mode == 6:
                    digit = min(16, digit)
                symbol = symbol * radix + digit
            length, code = inverse[mode][symbol]
            w.put(code, length)
            if unsigned:
                for v in values:
                    if v:
                        w.put(int(v < 0), 1)
            if mode == 6:
                for v in values:
                    if abs(v) >= 16:
                        width = abs(v).bit_length()-1
                        for _ in range(width-4):
                            w.put(1, 1)
                        w.put(0, 1)
                        w.put(abs(v)-(1 << width), width)
    w.put(scales[0], 5)
    for previous, current in zip(scales, scales[1:]):
        w.put(current-previous+5, 3)
    return w


def encode(samples, tables, coarse=-2):
    if not -2 <= coarse <= 8 or not samples or any(not -32768 <= x <= 32767 for x in samples):
        raise ValueError("invalid SSC PCM/quantisation")
    inverse = {mode: {symbol: pair for pair, symbol in codes.items()} for mode, codes in tables.codes.items()}
    output = Writer()
    previous = [0]*128
    # Encoder/synthesis lapping adds 128 samples of delay; flush the final block.
    padded = list(samples) + [0] * ((-len(samples)) % 128 + 128)
    for pos in range(0, len(padded), 128):
        current = padded[pos:pos+128]
        values = analysis(current, previous, tables)
        previous = current
        scales, quant = quantise(values, tables, coarse)
        block = block_bits(scales, quant, tables, inverse)
        for byte in block.data:
            output.put(byte, 8)
        output.put(block.buffer, block.count)
    result = output.finish()
    observed = decode(result, tables)
    expected = len(padded)
    if len(observed)//2 != expected:
        raise ValueError("SSC self-decode frame count mismatch")
    return result


def snr(samples, decoded):
    """Compare after the analysis bank's 128-sample delay, not by file length."""
    out = struct.unpack(f"<{len(decoded)//2}h", decoded)
    aligned = out[128:128+len(samples)]
    if len(aligned) != len(samples):
        raise ValueError("round-trip too short")
    signal = sum(x*x for x in samples)
    error = sum((x-y)**2 for x,y in zip(samples, aligned))
    return 10*math.log10(signal/max(1,error)) if signal else 0
