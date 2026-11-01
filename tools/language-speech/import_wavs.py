#!/usr/bin/env python3
"""Bring your own voice: import clip audio from any TTS engine or a microphone.

Run with python3 -I. Input is a directory with one file per clip, named
clipNNNN.<ext> (wav, mp3, flac, aiff, m4a, ogg; anything ffmpeg reads), in
the order `clip_pack.py list` prints. Each file is converted to mono PCM16
22050 Hz and saved with the same generation receipt eleven_greeting.py writes,
so prepare_greeting.py fits and builds it exactly like an ElevenLabs render.
`--label` names the engine and voice (e.g. "piper:en_GB-alba-medium"); it is
recorded as the receipt's voice_id. No network, card or device I/O.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from greeting import CLIP_SETS, locked_text, output_path

EXTS = (".wav", ".mp3", ".flac", ".aiff", ".aif", ".m4a", ".ogg")


def source_for(directory, clip):
    found = [p for p in (directory/f"clip{clip:04d}{e}" for e in EXTS) if p.exists()]
    if len(found) != 1:
        raise ValueError(f"clip {clip}: expected exactly one clip{clip:04d}.<ext> in {directory}")
    return found[0]


def to_pcm(path):
    """Decode with ffmpeg to raw mono s16le 22050 Hz."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-ac", "1", "-ar", "22050", "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"]
    pcm = subprocess.run(cmd, capture_output=True, check=True).stdout
    if len(pcm) < 2205*2:
        raise ValueError(f"{path.name}: shorter than 0.1 s after decoding")
    return pcm


def receipt(text, label, pcm, source_sha):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        w.writeframes(pcm)
    data = out.getvalue()
    return data, {"text": text, "voice_id": label, "model_id": label, "output_format": "pcm_22050",
                  "source": "imported", "source_sha256": source_sha,
                  "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "frames": len(pcm)//2,
                  "wav_sha256": hashlib.sha256(data).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clip-set", choices=tuple(CLIP_SETS), default="greeting")
    ap.add_argument("--input", type=Path, required=True, help="directory of clipNNNN.<ext> files")
    ap.add_argument("--output", type=Path, required=True,
                    help="new render directory under $NISSAN_ROOT/work/language-speech/en-<set>/")
    ap.add_argument("--label", required=True, help='engine:voice, e.g. "piper:en_GB-alba-medium"')
    args = ap.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9_.:+-]{3,80}", args.label):
            raise ValueError("label: 3-80 characters of A-Z a-z 0-9 _ . : + -")
        texts = locked_text(args.clip_set)
        src = args.input.expanduser().resolve()
        sources = {i: source_for(src, i) for i in CLIP_SETS[args.clip_set]}
        out = output_path(args.output, args.clip_set)
        out.mkdir(parents=True, exist_ok=False)
        for i, path in sources.items():
            data, meta = receipt(texts[i], args.label, to_pcm(path), hashlib.sha256(path.read_bytes()).hexdigest())
            with (out/f"clip{i:04d}.wav").open("xb") as f:
                f.write(data)
            with (out/f"clip{i:04d}.json").open("x") as f:
                f.write(json.dumps(meta, indent=2)+"\n")
            print(f"imported clip{i:04d} ({meta['frames']/22050:.3f}s) {texts[i]}", flush=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        ap.exit(1, f"Import refused: {e}\n")


if __name__ == "__main__":
    main()
