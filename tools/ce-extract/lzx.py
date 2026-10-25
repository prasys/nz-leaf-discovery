"""Pure-Python LZX decoder (stdlib only), modelled on libmspack's lzxd.c.

Decodes one self-contained LZX stream: the Intel E8 header bit, then
verbatim / aligned-offset / uncompressed blocks until `out_len` bytes are
produced. Huffman state and R0-R2 start fresh for every call, which is what
Windows CE's romimage LZX codec does for each 4 KiB page (see cecompress.py).
"""

MIN_MATCH = 2
NUM_CHARS = 256
PRETREE_NUM = 20
ALIGNED_NUM = 8
LENGTH_NUM = 249
TABLE_BITS = 10

BLOCKTYPE_VERBATIM = 1
BLOCKTYPE_ALIGNED = 2
BLOCKTYPE_UNCOMPRESSED = 3

_EXTRA_BITS = []
_j = 0
for _i in range(0, 52, 2):
    _EXTRA_BITS += [_j, _j]
    if _i != 0 and _j < 17:
        _j += 1
_POSITION_BASE = []
_j = 0
for _i in range(52):
    _POSITION_BASE.append(_j)
    _j += 1 << _EXTRA_BITS[_i]

POSITION_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}


class LZXError(Exception):
    pass


class _Bits:
    """MSB-first bit reader over 16-bit little-endian words."""

    __slots__ = ("d", "p", "buf", "n")

    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos
        self.buf = 0
        self.n = 0

    def _fill(self, need):
        d = self.d
        while self.n < need:
            p = self.p
            # past the end: feed zeros, like lzxd does
            w = d[p] | (d[p + 1] << 8) if p + 1 < len(d) else (d[p] if p < len(d) else 0)
            self.p = p + 2
            self.buf = (self.buf << 16) | w
            self.n += 16

    def read(self, k):
        if k == 0:
            return 0
        if self.n < k:
            self._fill(k)
        self.n -= k
        v = self.buf >> self.n
        self.buf &= (1 << self.n) - 1
        return v

    def peek(self, k):
        if self.n < k:
            self._fill(k)
        return self.buf >> (self.n - k)

    def skip(self, k):
        self.n -= k
        self.buf &= (1 << self.n) - 1

    def align16(self):
        # drop the remaining bits of the current 16-bit word
        self.skip(self.n % 16)


class _Huff:
    """Canonical Huffman decoder: a TABLE_BITS lookup plus a slow path."""

    __slots__ = ("table", "long", "maxlen")

    def __init__(self, lens):
        maxlen = max(lens) if lens else 0
        self.maxlen = maxlen
        self.table = None
        self.long = {}
        if maxlen == 0:
            return
        if maxlen > 16:
            raise LZXError("code length > 16")
        code = 0
        codes = []
        for L in range(1, maxlen + 1):
            for sym, l in enumerate(lens):
                if l == L:
                    codes.append((sym, L, code))
                    code += 1
            code <<= 1
        if code > (1 << (maxlen + 1)):
            raise LZXError("over-subscribed Huffman table")
        tb = TABLE_BITS
        table = [None] * (1 << tb)
        for sym, L, c in codes:
            if L <= tb:
                start = c << (tb - L)
                ent = (sym, L)
                for k in range(start, start + (1 << (tb - L))):
                    table[k] = ent
            else:
                self.long[(L, c)] = sym
        self.table = table

    def decode(self, br):
        if self.table is None:
            raise LZXError("decode from empty Huffman table")
        ent = self.table[br.peek(TABLE_BITS)]
        if ent is not None:
            br.skip(ent[1])
            return ent[0]
        for L in range(TABLE_BITS + 1, self.maxlen + 1):
            sym = self.long.get((L, br.peek(L)))
            if sym is not None:
                br.skip(L)
                return sym
        raise LZXError("invalid Huffman code")


def _read_lens(br, lens, first, last):
    pre = _Huff([br.read(4) for _ in range(PRETREE_NUM)])
    x = first
    while x < last:
        z = pre.decode(br)
        if z == 17:
            y = br.read(4) + 4
            for _ in range(y):
                lens[x] = 0
                x += 1
        elif z == 18:
            y = br.read(5) + 20
            for _ in range(y):
                lens[x] = 0
                x += 1
        elif z == 19:
            y = br.read(1) + 4
            z = pre.decode(br)
            z = lens[x] - z
            if z < 0:
                z += 17
            for _ in range(y):
                lens[x] = z
                x += 1
        else:
            z = lens[x] - z
            if z < 0:
                z += 17
            lens[x] = z
            x += 1


def _e8_untranslate(out, filesize):
    n = len(out)
    i = 0
    while i < n - 10:
        if out[i] == 0xE8:
            cur = i
            v = int.from_bytes(out[i + 1:i + 5], "little", signed=True)
            if -cur <= v < filesize:
                v = v - cur if v >= 0 else v + filesize
                out[i + 1:i + 5] = (v & 0xFFFFFFFF).to_bytes(4, "little")
            i += 5
        else:
            i += 1


def decompress(data, out_len, window_bits=17, pos=0):
    """Decode `out_len` bytes from an LZX stream starting at data[pos]."""
    slots = POSITION_SLOTS[window_bits]
    main_num = NUM_CHARS + slots * 8
    br = _Bits(data, pos)
    out = bytearray()
    r0 = r1 = r2 = 1
    main_lens = [0] * main_num
    len_lens = [0] * LENGTH_NUM
    e8_size = 0
    if br.read(1):
        e8_size = (br.read(16) << 16) | br.read(16)
    while len(out) < out_len:
        btype = br.read(3)
        blen = (br.read(16) << 8) | br.read(8)
        if blen == 0:
            raise LZXError("zero-length block")
        end = min(len(out) + blen, out_len)
        if btype == BLOCKTYPE_UNCOMPRESSED:
            if br.n == 0:
                br._fill(16)
            br.align16()
            # the reader may have buffered whole words beyond the alignment point
            p = br.p - br.n // 8
            br.buf = br.n = 0
            r0, r1, r2 = (int.from_bytes(data[p + 4 * k:p + 4 * k + 4], "little") for k in range(3))
            p += 12
            take = end - len(out)
            out += data[p:p + take]
            p += blen + (blen & 1)
            br.p = p
            continue
        if btype not in (BLOCKTYPE_VERBATIM, BLOCKTYPE_ALIGNED):
            raise LZXError("bad block type %d" % btype)
        aligned = None
        if btype == BLOCKTYPE_ALIGNED:
            aligned = _Huff([br.read(3) for _ in range(ALIGNED_NUM)])
        _read_lens(br, main_lens, 0, NUM_CHARS)
        _read_lens(br, main_lens, NUM_CHARS, main_num)
        main = _Huff(main_lens)
        _read_lens(br, len_lens, 0, LENGTH_NUM)
        length = _Huff(len_lens) if any(len_lens) else None
        while len(out) < end:
            sym = main.decode(br)
            if sym < NUM_CHARS:
                out.append(sym)
                continue
            sym -= NUM_CHARS
            mlen = sym & 7
            if mlen == 7:
                if length is None:
                    raise LZXError("length tree empty")
                mlen += length.decode(br)
            mlen += MIN_MATCH
            slot = sym >> 3
            if slot == 0:
                off = r0
            elif slot == 1:
                off = r1
                r1 = r0
                r0 = off
            elif slot == 2:
                off = r2
                r2 = r0
                r0 = off
            else:
                extra = _EXTRA_BITS[slot]
                off = _POSITION_BASE[slot] - 2
                if aligned is not None and extra >= 3:
                    if extra > 3:
                        off += br.read(extra - 3) << 3
                    off += aligned.decode(br)
                else:
                    off += br.read(extra)
                r2 = r1
                r1 = r0
                r0 = off
            src = len(out) - off
            if src < 0:
                raise LZXError("match before start of window (off=%d at %d)" % (off, len(out)))
            if off >= mlen:
                out += out[src:src + mlen]
            else:
                for k in range(mlen):
                    out.append(out[src + k])
    del out[out_len:]
    if e8_size:
        _e8_untranslate(out, e8_size)
    return bytes(out), br.p
