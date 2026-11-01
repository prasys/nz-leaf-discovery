#!/usr/bin/env python3
"""English-only ElevenLabs requests. Run with python3 -I.

The key is read in-process from ELEVENLABS_API_KEY or the file named by
ELEVENLABS_ENV_FILE; it is never printed, saved or logged. No card/ROM/audio
input. No response headers, raw voice objects, error bodies, request headers,
or credentials are printed/saved. Only public voice metadata and the locked
English set may be written. POST is a paid generation request; samples first,
render only after the owner chooses a voice.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from greeting import ROOT, SAMPLE, locked_text, output_path

MODEL = "eleven_multilingual_v2"   # Penny builds; --model picks another ElevenLabs model


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirect refused")


def api_key():
    """Load the key in-process from the environment or the owner's env file.

    The file path comes from ELEVENLABS_ENV_FILE. Nothing from the file is
    printed, saved, copied or logged; only the key value is returned.
    """
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    env_file = os.environ.get("ELEVENLABS_ENV_FILE")
    if not env_file:
        raise ValueError("ELEVENLABS_API_KEY is absent; configure the environment, never paste/log the key")
    try:
        lines = Path(env_file).expanduser().read_text().splitlines()
    except OSError:
        raise ValueError("ELEVENLABS_ENV_FILE is unreadable; never paste/log the key") from None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if separator and name.strip() == "ELEVENLABS_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                return value
    raise ValueError("ELEVENLABS_API_KEY is absent; configure ELEVENLABS_ENV_FILE, never paste/log the key")


def request(path, body=None):
    key = api_key()
    if not path.startswith(("/v1/", "/v2/")):
        raise ValueError("invalid API path")
    req = urllib.request.Request("https://api.elevenlabs.io" + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=90) as response:
            data = response.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024:
                raise ValueError("API response exceeds limit")
            return data
    except urllib.error.HTTPError as e:
        # Never include the response body, request object or exception repr.
        raise ValueError(f"ElevenLabs HTTP {e.code}; response body omitted") from None
    except urllib.error.URLError:
        raise ValueError("ElevenLabs connection failed; details omitted") from None


def save_json(path, data, clip_set="greeting"):
    path = output_path(path, clip_set)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def public_voices(accent):
    query = urllib.parse.urlencode({"language": "en", "accent": accent, "page_size": 30,
                                   "include_custom_rates": "false", "page": 0})
    raw = json.loads(request("/v1/shared-voices?" + query))
    # This endpoint is the public library, never account/private cloned voices.
    allowed = ("voice_id", "public_owner_id", "name", "accent", "gender", "age", "description", "category")
    return [{k: v.get(k, "") for k in allowed} for v in raw.get("voices", [])]


def default_voices():
    # Explicitly excludes account-created/private voices and their sample data.
    raw = json.loads(request("/v2/voices?voice_type=default&page_size=100"))
    return [{"voice_id":v["voice_id"],"name":v.get("name",""),
             "accent":v.get("labels",{}).get("accent",""),
             "gender":v.get("labels",{}).get("gender",""),"category":"default"}
            for v in raw.get("voices",[])]


def synthesize(text, voice, clip_set="greeting", model=MODEL):
    if not re.fullmatch(r"[A-Za-z0-9]{10,64}", voice):
        raise ValueError("invalid public voice ID")
    if not re.fullmatch(r"eleven_[a-z0-9_]{2,40}", model):
        raise ValueError("invalid ElevenLabs model ID")
    allowed = set(locked_text(clip_set).values())
    if clip_set == "greeting":
        allowed.add(SAMPLE)
    if text not in allowed:
        raise ValueError("only the locked English text for this clip set may be sent")
    settings = {"stability": 0.65, "similarity_boost": 0.75,
                "style": 0, "use_speaker_boost": True, "speed": 1.0}
    if model != MODEL:
        # Only the default model is tested; newer models (e.g. v3) lack speaker boost.
        del settings["use_speaker_boost"]
    body = {"text": text, "model_id": model, "seed": 57, "voice_settings": settings}
    pcm = request(f"/v1/text-to-speech/{voice}?output_format=pcm_22050", body)
    if not pcm or len(pcm) % 2 or pcm[:4] in (b"RIFF", b'{"de'):
        raise ValueError("expected nonempty raw s16 PCM from API")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        w.writeframes(pcm)
    return out.getvalue(), {"text": text, "voice_id": voice, "model_id": model,
                            "output_format": "pcm_22050", "seed": 57,
                            "voice_settings": body["voice_settings"],
                            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
                            "frames": len(pcm)//2}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    voices = sub.add_parser("voices", help="list public-library choices; no generation")
    voices.add_argument("--accent", default="new zealand")
    voices.add_argument("--defaults",action="store_true",help="list public default voices as neutral alternatives")
    voices.add_argument("--output", type=Path, required=True)
    add = sub.add_parser("add-voice",help="make a chosen public-library sample voice available for TTS")
    add.add_argument("--catalog",type=Path,required=True)
    add.add_argument("--voice",required=True)
    samples = sub.add_parser("samples", help="generate 2–3 short English comparison samples")
    samples.add_argument("--voice", action="append", required=True)
    samples.add_argument("--output", type=Path, required=True)
    samples.add_argument("--resume",action="store_true",help="reuse verified completed samples; never overwrite")
    samples.add_argument("--model",default=MODEL,help=f"ElevenLabs model ID (default {MODEL})")
    render = sub.add_parser("render", help="generate full locked set in the owner-selected voice")
    render.add_argument("--voice", required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--clip-set", choices=("greeting", "ev"), default="greeting")
    render.add_argument("--resume",action="store_true",help="reuse verified completed clips; never overwrite")
    render.add_argument("--model",default=MODEL,help=f"ElevenLabs model ID (default {MODEL})")
    args = ap.parse_args()
    clip_set = getattr(args, "clip_set", "greeting")
    try:
        locked_text(clip_set)
        if args.command == "add-voice":
            catalog = json.loads(output_path(args.catalog).read_text())
            if catalog.get("source") != "public library":
                raise ValueError("public library catalogue required")
            v = next(v for v in catalog["voices"] if v["voice_id"] == args.voice)
            if not re.fullmatch(r"[A-Za-z0-9]{10,64}",args.voice) or not re.fullmatch(r"[a-f0-9]{64}",v["public_owner_id"]):
                raise ValueError("invalid public-library voice/owner ID")
            request(f"/v1/voices/add/{v['public_owner_id']}/{args.voice}",{"new_name":v["name"]})
            print("Public-library voice added for English sample generation")
            return
        out = output_path(args.output, clip_set)
        if args.command == "voices":
            choices = default_voices() if args.defaults else public_voices(args.accent)
            save_json(out, {"source": "public defaults" if args.defaults else "public library",
                            "accent_filter": "defaults" if args.defaults else args.accent,"voices": choices}, clip_set)
            print(f"{len(choices)} public voice choices saved to {out}")
            return
        if args.command == "samples" and (not 2 <= len(args.voice) <= 3 or len(set(args.voice)) != len(args.voice)):
            raise ValueError("supply 2–3 distinct voice IDs")
        api_key()
        out.mkdir(parents=True, exist_ok=args.resume)
        jobs = [(f"option-{i}", SAMPLE, v) for i, v in enumerate(args.voice, 1)] if args.command == "samples" else [
            (f"clip{i:04d}", text, args.voice) for i, text in locked_text(clip_set).items()]
        for name, text, voice in jobs:
            wavpath,metapath = out/(name+".wav"),out/(name+".json")
            if args.resume and (wavpath.exists() or metapath.exists()):
                meta = json.loads(metapath.read_text())
                if (meta.get("text") != text or meta.get("voice_id") != voice or
                        meta.get("model_id") != args.model or meta.get("wav_sha256") != hashlib.sha256(wavpath.read_bytes()).hexdigest()):
                    raise ValueError("existing generation differs; use a fresh directory")
                print(f"verified existing {name}.wav; no API request",flush=True)
                continue
            data, meta = synthesize(text, voice, clip_set, args.model)
            with wavpath.open("xb") as f:
                f.write(data)
            meta["wav_sha256"] = hashlib.sha256(data).hexdigest()
            save_json(metapath, meta, clip_set)
            print(f"saved {name}.wav ({meta['frames']/22050:.3f}s)", flush=True)
    except (OSError, ValueError, KeyError, StopIteration) as e:
        # Our ValueErrors contain no request/response headers or credentials.
        ap.exit(1, f"Generation/listing stopped: {e}\n")


if __name__ == "__main__":
    main()
