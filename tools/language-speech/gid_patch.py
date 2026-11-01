#!/usr/bin/env python3
"""Same-length, allowlisted GID patch validation; pure functions, no device I/O.

The allowlist is the greeting set plus the EV alert set. A greeting build must
start from stock; the EV v2 build must start from the pinned Penny v1.1 build.
Given the stock GID as `stock`, an EV build may instead start from stock or
from any greeting-only build of it (an owner's own voice).
"""
import hashlib
import struct

from gid_catalog import Gid
from greeting import CLIP_SETS

OUTER_SHA = "6733c2b261f79f12ab469d97fc93228bb5508fdc5f1f2ab15be6b3bb1796800c"
V1_SHA = "7e007bfb5c40f0039dc30fc1749ce91d819352bf5275c317cfb83cca075af0c1"
V11_SHA = "0a80b63701918d323230f39188fa0d8fb6570242b659a7bfbf3d93a0ff994ed4"

# clip set -> pinned bases accepted by patch(). "all" is validation-only.
ALLOWED_BASES = {
    "greeting": {OUTER_SHA},
    "ev": {V11_SHA},
    "all": {OUTER_SHA},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allowed_clips(clip_set):
    if clip_set == "all":
        return tuple(sorted(set(CLIP_SETS["greeting"]) | set(CLIP_SETS["ev"])))
    return CLIP_SETS[clip_set]


def check_base(base, clip_set, stock=None):
    """Pinned base, or (EV only) stock or a greeting-only build of the given stock."""
    if sha(base) in ALLOWED_BASES[clip_set]:
        return
    if clip_set == "ev" and stock is not None and sha(stock) == OUTER_SHA:
        if base == stock:
            return
        validate(stock, base, "greeting")
        return
    raise ValueError(f"{clip_set} base GID hash mismatch")


def patch(base, replacements, clip_set="greeting", stock=None):
    """Change only the selected clip descriptors/audio, keeping every other byte."""
    if clip_set not in CLIP_SETS:
        raise ValueError("patch requires the greeting or ev clip set")
    check_base(base, clip_set, stock)
    clips = allowed_clips(clip_set)
    if set(replacements) != set(clips):
        raise ValueError(f"exactly the {len(clips)} {clip_set} clips are required")
    gid = Gid(base)
    result = bytearray(base)
    base_offset = gid.container_offset
    for i, (fmt, audio) in replacements.items():
        c = gid.clips[i]
        if fmt not in (bytes.fromhex("02010102"), bytes.fromhex("02040102")):
            raise ValueError("only mono PCM16/SSC at 22050 Hz is supported")
        if not audio or len(audio) > c.padded_size or (fmt[1] == 1 and len(audio) % 2):
            raise ValueError(f"clip {i}: slot overflow/empty/incomplete PCM")
        struct.pack_into("<4sIII", result, base_offset+c.descriptor, fmt, c.offset, c.padded_size, len(audio))
        start = base_offset+c.offset
        result[start:start+c.padded_size] = audio + bytes(c.padded_size-len(audio))
    result = bytes(result)
    validate(base, result, clip_set, stock)
    return result


def validate(base, build, clip_set="all", stock=None):
    """Refuse any change outside the named clip set or its pinned base."""
    if clip_set not in ALLOWED_BASES:
        raise ValueError("unknown validation clip set")
    if clip_set == "ev" and stock is not None:
        check_base(base, clip_set, stock)
    elif sha(base) not in ALLOWED_BASES[clip_set]:
        raise ValueError(f"{clip_set} baseline GID hash mismatch")
    if len(build) != len(base):
        raise ValueError("pinned baseline and same-size GID required")
    before, after = Gid(base), Gid(build)
    if after.container_offset != before.container_offset or len(after.clips) != len(before.clips):
        raise ValueError("GID structure changed")
    base_offset = before.container_offset
    allowed = []
    for i in allowed_clips(clip_set):
        a, b = before.clips[i], after.clips[i]
        if (b.offset, b.padded_size) != (a.offset, a.padded_size):
            raise ValueError("clip allocation changed")
        if b.format not in (bytes.fromhex("02010102"), bytes.fromhex("02040102")):
            raise ValueError("unexpected clip format")
        if not b.size or b.size > b.padded_size or (b.format[1] == 1 and b.size % 2):
            raise ValueError("invalid audio length")
        allowed.extend([(base_offset+a.descriptor, base_offset+a.descriptor+16),
                        (base_offset+a.offset, base_offset+a.offset+a.padded_size)])
    pos = 0
    for first, last in sorted(allowed):
        if first < pos:
            raise ValueError("overlapping patch ranges")
        if base[pos:first] != build[pos:first]:
            raise ValueError("change outside the allowlisted clip extents/descriptors")
        pos = last
    if base[pos:] != build[pos:]:
        raise ValueError("change after allowlisted clip extents")
