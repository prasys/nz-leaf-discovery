"""Windows CE romimage compression ("CECompress") as found in the LEAF images.

Layout of one compressed object (a FILESentry body or an o32 section):

    +0          u24  uncompressed size S
    +3          u24  end offset of block 0  (relative to +0)
    ...         u24  end offset of block n-1, n = ceil(S / 0x1000)
    block k     starts where block k-1 ends (block 0 right after the table):
      +0  u32  header length (0x10)
      +4  u32  uncompressed block size (0x1000, last block shorter)
      +8  u32  compressed size C (includes the 4-byte magic)
      +12 u32  uncompressed block size again
      +16 C bytes: magic 5B 80 80 8D, then a raw LZX stream
                   (window 2^16, Intel E8 bit 0, fresh state per block)
"""

import lzx

BLOCK = 0x1000
MAGIC = b"\x5b\x80\x80\x8d"
WINDOW_BITS = 16


class CECompressError(Exception):
    pass


def u24(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def decompress(data, expect_size=None):
    """Decompress one CECompress object. Returns bytes."""
    size = u24(data, 0)
    if expect_size is not None and size != expect_size:
        raise CECompressError("size header %#x != expected %#x" % (size, expect_size))
    nblk = (size + BLOCK - 1) // BLOCK
    ends = [u24(data, 3 + 3 * k) for k in range(nblk)]
    pos = 3 + 3 * nblk
    out = bytearray()
    for k, end in enumerate(ends):
        hlen = int.from_bytes(data[pos:pos + 4], "little")
        raw = int.from_bytes(data[pos + 4:pos + 8], "little")
        comp = int.from_bytes(data[pos + 8:pos + 12], "little")
        want = min(BLOCK, size - len(out))
        if hlen != 0x10 or raw != want or pos + hlen + comp != end:
            raise CECompressError("block %d: bad header hlen=%#x raw=%#x comp=%#x pos=%#x end=%#x"
                                  % (k, hlen, raw, comp, pos, end))
        body = data[pos + hlen:end]
        if body[:4] != MAGIC:
            raise CECompressError("block %d: unknown codec magic %s" % (k, body[:4].hex()))
        blk, used = lzx.decompress(body, raw, WINDOW_BITS, 4)
        if used > len(body) + 2:
            raise CECompressError("block %d: LZX overran its input" % k)
        out += blk
        pos = end
    return bytes(out), pos
