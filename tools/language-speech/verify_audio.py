#!/usr/bin/env python3
"""Verify all public GID WAVs and optionally bundle them deterministically.

No decoder execution oracle is implied: this checks complete coverage, rates,
PCM bytes, SSC block counts, reproducibility against a second export and hashes.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import wave
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gid_catalog import Gid
from build_voice_table import GID_SHA256


def read_wav(path):
    with wave.open(str(path)) as w:
        if (w.getnchannels(),w.getsampwidth(),w.getcomptype())!=(1,2,"NONE"):
            raise ValueError(f"unexpected WAV format: {path.name}")
        return w.getframerate(),w.getnframes(),w.readframes(w.getnframes())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gid",type=Path)
    ap.add_argument("decoded",type=Path)
    ap.add_argument("--compare",type=Path)
    ap.add_argument("--bundle",type=Path)
    args=ap.parse_args()
    gid=Gid(args.gid.read_bytes())
    if gid.sha256!=GID_SHA256:raise ValueError("public GID hash mismatch")
    names={f"clip{i:04d}.wav" for i in range(len(gid.clips))}
    if {p.name for p in args.decoded.glob("*.wav")}!=names:
        raise ValueError("WAV coverage differs from complete GID clip directory")
    if args.bundle and (not args.bundle.resolve().is_relative_to(Path.home()/"nissan/work/language-speech")
                        or args.bundle.suffix!=".zip"):
        ap.error("bundle must be a ZIP under ~/nissan/work/language-speech/")
    manifest=io.StringIO()
    writer=csv.writer(manifest,delimiter="\t",lineterminator="\n")
    writer.writerow(["clip","rate","frames","pcm_sha256","wav_sha256"])
    rates=Counter();frames=Counter();pcm_count=ssc_count=0
    for c in gid.clips:
        p=args.decoded/f"clip{c.index:04d}.wav"
        rate,n,audio=read_wav(p)
        expected_rate={1:11025,2:22050}[c.format[3]]
        if rate!=expected_rate or len(audio)!=n*2:raise ValueError(f"bad WAV rate/length {c.index}")
        if c.format[1]==1:
            original=gid.data[c.offset:c.offset+c.size]
            if audio!=original[:len(original)&~1]:raise ValueError(f"PCM mismatch {c.index}")
            pcm_count+=1
        else:
            if n%128:raise ValueError(f"SSC not a multiple of 128 samples {c.index}")
            ssc_count+=1
        if args.compare and read_wav(args.compare/p.name)!=(rate,n,audio):
            raise ValueError(f"repeat decode differs {c.index}")
        writer.writerow([c.index,rate,n,hashlib.sha256(audio).hexdigest(),hashlib.sha256(p.read_bytes()).hexdigest()])
        rates[rate]+=1;frames[rate]+=n
    report={"clips":len(gid.clips),"ssc_clips":ssc_count,"pcm_clips":pcm_count,
            "rates":dict(rates),"seconds":sum(n/r for r,n in frames.items()),
            "repeat_pcm_equal":bool(args.compare),
            "manifest_sha256":hashlib.sha256(manifest.getvalue().encode()).hexdigest()}
    if args.bundle:
        with zipfile.ZipFile(args.bundle,"x",compression=zipfile.ZIP_STORED) as z:
            for name in sorted(names):
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.external_attr=0o644<<16
                z.writestr(info,(args.decoded/name).read_bytes())
            info=zipfile.ZipInfo("sha256s.tsv",date_time=(1980,1,1,0,0,0));info.external_attr=0o644<<16
            z.writestr(info,manifest.getvalue())
        report["bundle_sha256"]=hashlib.sha256(args.bundle.read_bytes()).hexdigest()
        report["bundle_bytes"]=args.bundle.stat().st_size
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
