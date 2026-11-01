#!/usr/bin/env python3
"""Fit one locked clip set and build a same-size out-of-tree GID.

Run with python3 -I. --clip-set greeting uses the stock base; --clip-set ev
uses the pinned Penny v1.1 base. --budget-only needs no English audio or
credentials. Full preparation verifies English-only generation receipts, trims
quiet ends, normalises loudness when asked, tries PCM then SSC, and allows
pitch-preserving atempo up to 1.12 only. Any overflow/low-quality result
prevents creation of a patched GID. No device I/O.
"""
import argparse
import csv
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from greeting import CLIP_SETS, locked_text, output_path
from gid_catalog import Gid
from gid_patch import OUTER_SHA, sha, patch
from ssc_decode import Tables, decode
from ssc_encode import encode, snr

FIELDS = ["clip", "member_audio_offset", "descriptor_offset", "slot_bytes", "pcm_max_seconds",
          "en_nz", "wav_sha256", "input_seconds", "input_frames", "trimmed_frames", "speed",
          "format", "encoded_bytes", "spare_bytes", "coarse", "roundtrip_snr_db", "status", "notes"]


def pcm(samples):
    return struct.pack(f"<{len(samples)}h", *samples)


def wav_bytes(audio):
    out = io.BytesIO()
    with wave.open(out,"wb") as w:
        w.setparams((1,2,22050,0,"NONE","not compressed"))
        w.writeframes(audio)
    return out.getvalue()


def quiet_trim(samples):
    peak = max(map(abs,samples),default=0)
    if peak < 100:
        raise ValueError("empty/near-silent generated prompt")
    threshold = max(40,peak*0.005)
    # Inspect 5ms RMS windows, keeping 20ms context at both ends.
    active = [i for i in range(0,len(samples),110)
              if sum(x*x for x in samples[i:i+110])/len(samples[i:i+110]) > threshold**2]
    if not active:
        raise ValueError("no active speech detected")
    first,last = max(0,active[0]-441), min(len(samples),active[-1]+110+441)
    return samples[first:last], first, len(samples)-last


def tempo(samples, speed):
    if speed == 1:
        return samples
    cmd = ["ffmpeg","-hide_banner","-loglevel","error","-f","s16le","-ar","22050","-ac","1",
           "-i","pipe:0","-af",f"atempo={speed}","-f","s16le","-ar","22050","-ac","1","pipe:1"]
    result = subprocess.run(cmd,input=pcm(samples),capture_output=True,check=True)
    return list(struct.unpack(f"<{len(result.stdout)//2}h",result.stdout))


def normalise(samples, rms_dbfs, peak_dbfs):
    """Scale to the stock clips' level (14 §10.4): target RMS, never above the peak cap."""
    if rms_dbfs is None:
        return samples, 0.0
    rms = math.sqrt(sum(x*x for x in samples)/len(samples))
    peak = max(map(abs,samples))
    gain = min(32768*10**(rms_dbfs/20)/rms, 32768*10**(peak_dbfs/20)/peak)
    return [max(-32768,min(32767,round(x*gain))) for x in samples], 20*math.log10(gain)


def fit(samples, budget, tables, level=(None,None)):
    trimmed, head, tail = quiet_trim(samples)
    trimmed, gain_db = normalise(trimmed, *level)
    smallest = None
    for speed in (1.0,1.04,1.08,1.12):
        current = tempo(trimmed,speed)
        if len(current)*2 <= budget:
            return pcm(current), bytes.fromhex("02010102"), current, {
                "speed":speed,"coarse":"","roundtrip_snr_db":"lossless",
                "trim_head_frames":head,"trim_tail_frames":tail,"trimmed_frames":len(trimmed),"gain_db":round(gain_db,2)}
        for coarse in (-2,-1,0,1):
            audio = encode(current,tables,coarse)
            observed = decode(audio,tables)
            score = snr(current,observed)
            candidate = (audio,bytes.fromhex("02040102"),current,{
                "speed":speed,"coarse":coarse,"roundtrip_snr_db":round(score,3),
                "trim_head_frames":head,"trim_tail_frames":tail,"trimmed_frames":len(trimmed),"gain_db":round(gain_db,2)})
            if smallest is None or len(audio) < len(smallest[0]):
                smallest = candidate
            if len(audio) <= budget and score >= 20:
                return candidate
    return smallest


def read_generated(directory, i, text):
    p = directory/f"clip{i:04d}.wav"
    data = p.read_bytes()
    meta = json.loads(p.with_suffix(".json").read_text())
    if (meta.get("text") != text or meta.get("wav_sha256") != sha(data) or
            meta.get("output_format") != "pcm_22050"):
        raise ValueError(f"clip {i}: English generation receipt/hash mismatch")
    with wave.open(io.BytesIO(data),"rb") as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype()) != (1,2,22050,"NONE"):
            raise ValueError("expected mono PCM16 22050 Hz")
        raw = w.readframes(w.getnframes())
    if meta.get("pcm_sha256") != sha(raw) or meta.get("frames") != len(raw)//2:
        raise ValueError("generation PCM hash/length mismatch")
    return list(struct.unpack(f"<{len(raw)//2}h",raw)),meta["voice_id"],meta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gid",type=Path)
    ap.add_argument("--speech-exe",type=Path)
    ap.add_argument("--audio",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--budget-only",action="store_true")
    ap.add_argument("--clip-set",choices=("greeting","ev"),default="greeting",
                    help="greeting (stock base) or ev (Penny v1.1 base)")
    ap.add_argument("--stock-gid",type=Path,
                    help="ev only: the stock GID, so the base may be stock or your own greeting build")
    ap.add_argument("--rms-dbfs",type=float,help="normalise each clip to this RMS (stock median about -16)")
    ap.add_argument("--peak-dbfs",type=float,default=-2.0,help="peak cap used with --rms-dbfs")
    args = ap.parse_args()
    try:
        base = args.gid.read_bytes()
        base_sha = sha(base)
        stock = args.stock_gid.read_bytes() if args.stock_gid else None
        gid,texts = Gid(base),locked_text(args.clip_set)
        clips = CLIP_SETS[args.clip_set]
        out = output_path(args.output,args.clip_set)
        if out.exists():
            raise ValueError("use a fresh output directory")
        tables = None
        inputs = {}
        if not args.budget_only:
            if args.audio is None or args.speech_exe is None:
                raise ValueError("--audio and --speech-exe are required for fitting")
            directory = output_path(args.audio,args.clip_set)
            inputs = {i:read_generated(directory,i,texts[i]) for i in clips}
            if len({meta[1] for meta in inputs.values()}) != 1:
                raise ValueError("full greeting set must use one chosen voice")
            tables = Tables(args.speech_exe.read_bytes())
        out.mkdir(parents=True,exist_ok=False)
        rows,replacements,previews = [],{},{}
        for i in clips:
            c = gid.clips[i]
            row = dict.fromkeys(FIELDS,"")
            row.update(clip=i,member_audio_offset=hex(c.offset),descriptor_offset=hex(c.descriptor),
                       slot_bytes=c.padded_size,pcm_max_seconds=f"{c.padded_size/44100:.6f}",en_nz=texts[i],
                       status="PENDING_VOICE_SELECTION",notes="[confirmed] GID descriptor/allocation; no English audio generated yet")
            if not args.budget_only:
                samples,_,receipt = inputs[i]
                # Louder audio costs bits: step a clip down 1 dB at a time until it fits.
                targets = [None] if args.rms_dbfs is None else [args.rms_dbfs-k for k in range(15)]
                for target in targets:
                    audio,fmt,current,meta = fit(samples,c.padded_size,tables,(target,args.peak_dbfs))
                    score = meta["roundtrip_snr_db"]
                    fits = len(audio) <= c.padded_size and (score == "lossless" or score >= 20)
                    if fits:
                        break
                row.update(wav_sha256=receipt["wav_sha256"],
                           input_seconds=f"{len(samples)/22050:.3f}",
                           input_frames=len(samples),format=fmt.hex(),encoded_bytes=len(audio),
                           spare_bytes=c.padded_size-len(audio),status="FIT" if fits else "OVERFLOW_OR_QUALITY_FAIL",
                           **{k:meta[k] for k in ("trimmed_frames","speed","coarse","roundtrip_snr_db")})
                row["notes"] = (f"[confirmed] local encode/self-decode; trimmed head={meta['trim_head_frames']} "
                                f"tail={meta['trim_tail_frames']} frames; gain {meta['gain_db']} dB; [likely] quality needs listening; car playback untested")
                # Preserve every encoded candidate and a decoder-preview WAV for review.
                (out/f"clip{i:04d}.bin").write_bytes(audio)
                preview = audio if fmt[1] == 1 else decode(audio,tables)
                (out/f"clip{i:04d}.wav").write_bytes(wav_bytes(preview))
                if fits:
                    replacements[i] = (fmt,audio)
                    previews[i] = preview
            rows.append(row)
        with (out/"fits.tsv").open("x",newline="") as f:
            w = csv.DictWriter(f,fieldnames=FIELDS,delimiter="\t",lineterminator="\n")
            w.writeheader();w.writerows(rows)
        report = {"clip_set":args.clip_set,"stock_gid_sha256":OUTER_SHA,
                  "base_gid_sha256":base_sha,"clips":len(rows),"fits":len(replacements),
                  "status":"BUDGET_ONLY_PENDING_VOICE" if args.budget_only else "REFUSED_OVERFLOW_OR_QUALITY",
                  "fit_table_sha256":sha((out/"fits.tsv").read_bytes()),
                  "max_speed":1.12,"min_local_snr_db":20,"rms_dbfs":args.rms_dbfs,"peak_dbfs":args.peak_dbfs}
        if len(replacements) == len(clips):
            build = patch(base,replacements,args.clip_set,stock)
            with (out/"SJP00300.GID").open("xb") as f:
                f.write(build)
            report.update(status="BUILT_HARDWARE_UNTESTED",build_sha256=sha(build),bytes=len(build),
                          voice_id=next(iter(inputs.values()))[1])
            # Host listening example preserves the actual token order and pauses.
            examples = {"greeting":(0xb0e,0xb14,0xb20,0xb40,0xb47),
                        "ev":(0xfdd,0xfdc,0x0366,0x0367)}
            sequence = bytearray()
            for phrase in examples[args.clip_set]:
                for token in gid.playlist(phrase):
                    if token & 0x80000000:
                        sequence.extend(bytes(round((token & 0x7fffffff)*22050/1000)*2))
                    else:
                        sequence.extend(previews[gid.by_descriptor[token].index])
            example = wav_bytes(sequence)
            example_name = "welcome-example.wav" if args.clip_set == "greeting" else "ev-example.wav"
            (out/example_name).write_bytes(example)
            report["example_wav_sha256"] = sha(example)
            report["example_wav"] = example_name
            report["example_phrases"] = [f"{x:#x}" for x in examples[args.clip_set]]
        (out/"build-report.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
        if not args.budget_only and len(replacements) != len(clips):
            ap.exit(1,"No GID built: review overflows/quality failures in fits.tsv\n")
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:
        ap.exit(1,f"Voice preparation refused: {e}\n")


if __name__ == "__main__":
    main()
