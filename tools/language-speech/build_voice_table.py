#!/usr/bin/env python3
"""Build an explicitly uncertain NZ English inventory from public GID ASR drafts.

Run with python3 -I. No private/name audio is accepted. All clip/playlist offsets
come from the pinned GID. Text is a draft, not proof of playback/reachability.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gid_catalog import Gid

GID_SHA256 = "3defd994ac5537c16b0debbf080b39d6068135d1e81d2bda373c4bf4ba0456db"
FIELDS = ["id/offset", "category", "jp_text", "en_nz", "notes"]
MONTHS = "January February March April May June July August September October November December".split()
WEEKDAYS = "Sunday Monday Tuesday Wednesday Thursday Friday Saturday".split()


def read_asr(path, complete=True):
    rows = list(csv.DictReader(io.StringIO(path.read_text(errors="replace")), delimiter="\t"))
    result = {}
    for row in rows:
        i = int(row["clip"])
        if i in result or not 0 <= i < 2071:
            raise ValueError("duplicate or invalid ASR clip")
        result[i] = row
    if complete and set(result) != set(range(2071)):
        raise ValueError("ASR must cover all 2071 public GID clips")
    return result


def shorten_repetition(s):
    s = " ".join(s.split()).strip()
    for width in range(2, len(s)//2+1):
        piece = s[:width]
        count = 0
        pos = 0
        while s[pos:pos+width] == piece:
            count += 1
            pos += width
        if count >= 2 and (not s[pos:] or piece.startswith(s[pos:])):
            return piece.strip(), True
    return s, False


def nz(s):
    replacements = {
        "kilometers": "kilometres", "kilometer": "kilometre", "meters": "metres",
        "meter": "metre", "center": "centre", "color": "colour", "canceled": "cancelled",
        "canceling": "cancelling", "gasoline": "petrol", "parking lot": "car park",
        "cell phone": "mobile phone", "tire": "tyre", "tires": "tyres",
    }
    for old, new in replacements.items():
        s = re.sub(r"\b"+re.escape(old)+r"\b", lambda m: new.capitalize() if m[0][0].isupper() else new,
                   s, flags=re.I)
    return s


def redact_example_names(s):
    # Public GID dialogue includes a stock example person; do not put names in git.
    return re.sub(r"日産(?:太郎|タロウ|タロー)|ニッサンタロウ|にっさんたろう|Nissan\s*Tar(?:o|ou)",
                  "redacted", s, flags=re.I)


def known_welcome(i):
    if 764 <= i <= 767:
        return ("greeting", ["おはようございます", "こんにちは", "こんばんは", "あけましておめでとうございます"][i-764],
                ["Good morning.", "Hello.", "Good evening.", "Happy New Year."][i-764])
    if 768 <= i <= 779:
        return "date / month", f"{i-767}月", MONTHS[i-768]
    if 780 <= i <= 810:
        day = i-779
        suffix = "th" if 10 <= day % 100 <= 20 else {1:"st", 2:"nd", 3:"rd"}.get(day%10,"th")
        return "date / day", f"{day}日", f"{day}{suffix}"
    if 811 <= i <= 817:
        return "date / weekday", "日月火水木金土"[i-811]+"曜日です", WEEKDAYS[i-811]+"."
    if i == 818:
        return "safety / driving", "今日も安全運転でいきましょう", "Drive safely today."
    if i == 819:
        return "safety / alcohol", "お酒を飲んだら運転はやめましょう", "If you've been drinking, don't drive."
    return None


def category(i, jp, en):
    text = jp+" "+en
    if re.search(r"充電|電池|バッテリー|航続|電力|battery|charg(?:e|ing)|driving range", text, re.I):
        return "EV / charging / energy"
    if re.search(r"電話|ダイヤル|通話|ブルートゥース|ペアリング|携帯|phone|bluetooth|dial|hands.free",text,re.I):
        return "phone / Bluetooth"
    if re.search(r"警報|警告|危険|異常|シートベルト|ブレーキ|ドア|warning|door|seat belt|brake",text,re.I):
        return "safety / vehicle warning"
    if re.search(r"ETC|[IE]TC|料金|ゲート|toll|yen|fee",text,re.I) or 445 <= i <= 547:
        return "tolls / amounts / ETC"
    if 1172 <= i <= 1209 or re.search(r"時頃|時ごろ|分ごろ|時刻|午前|午後|arrival time|o'clock",text,re.I):
        return "time / ETA fragments"
    if re.search(r"天気|警報|晴れ|曇り|雨|雪|weather|forecast|rain|snow",text,re.I):
        return "weather / alerts"
    if re.search(r"渋滞|混雑|通行止|工事|交通|VICS|traffic|congestion|roadworks|closure",text,re.I):
        return "traffic / road restrictions"
    if re.search(r"音声認識|話して|発話|コマンド|認識|どうぞ|お話|選択|say|speak|command|recognition|repeat|select",text,re.I):
        return "voice recognition / dialogue"
    if re.search(r"曲|CD|ラジオ|アルバム|アーティスト|radio|album|artist|music|playback",text,re.I):
        return "audio / media"
    if re.search(r"センター|オペレータ|情報センター|CARWINGS|operator|information centre",text,re.I):
        return "information / operator / CARWINGS"
    if (127 <= i <= 372 or 557 <= i <= 572 or 606 <= i <= 743 or
            869 <= i <= 885 or 1023 <= i <= 1124 or
            re.search(r"自動車道|高速|線です|銀行|ディーラ|の$|expressway|motorway|bank|station",text,re.I)):
        return "navigation / public names / landmarks"
    if re.search(r"右|左|直進|分岐|目的地|経由|ルート|レーン|メートル|キロ|turn|route|destination|lane|metre|kilometre",text,re.I):
        return "navigation / guidance"
    if re.fullmatch(r"[\d,.万千百十円分時間年月日%・ ]+",jp) or re.fullmatch(r"[\d,. ]+",en):
        return "numbers / units / fragments"
    # Broad family only: adjacency is a clue, never a playback/use proof.
    families = [
        (8,126,"navigation / guidance fragment"),
        (379,400,"traffic / navigation fragment"),
        (401,407,"information / operator / CARWINGS"),
        (409,427,"phone / status fragment"),
        (428,444,"safety / vehicle fragment"),
        (551,605,"navigation / distance or timing fragment"),
        (745,763,"navigation / lane fragment"),
        (820,901,"navigation / guidance fragment"),
        (902,940,"weather / alert fragment"),
        (941,1013,"calendar / numbers / fragments"),
        (1014,1022,"tolls / ETC fragment"),
        (1125,1171,"navigation / distance fragment"),
        (1210,1212,"traffic / restriction fragment"),
        (1213,1287,"tolls / amounts / fragments"),
        (1288,1293,"navigation / waypoint fragment"),
        (1398,1608,"voice recognition / dialogue fragment"),
        (1609,1700,"voice recognition / media fragment"),
        (1701,1749,"voice recognition / information fragment"),
        (1750,2070,"voice recognition / help or command fragment"),
    ]
    for first,last,family in families:
        if first <= i <= last:return family
    return "unclassified / fragment"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gid", type=Path)
    ap.add_argument("japanese", type=Path)
    ap.add_argument("english", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--overrides", type=Path)
    ap.add_argument("--decoded", type=Path, help="verified WAV directory, for exact zero-audio detection")
    ap.add_argument("--japanese-review", type=Path, action="append", default=[], help="full-context retry TSV; repeatable, later rows win")
    ap.add_argument("--english-review", type=Path, action="append", default=[], help="full-context retry TSV; repeatable, later rows win")
    args = ap.parse_args()
    if args.decoded and not args.decoded.resolve().is_relative_to(Path.home()/"nissan/work/language-speech"):
        ap.error("decoded WAVs must be under ~/nissan/work/language-speech/")
    if args.output.suffix.lower()!=".tsv" or args.output.resolve().is_relative_to(Path.home()/"nissan/sdcard"):
        ap.error("output must be a TSV outside the originals directory")
    for p in (args.gid,args.japanese,args.english,args.overrides,*args.japanese_review,*args.english_review):
        if p and p.resolve()==args.output.resolve():ap.error("output must differ from inputs")
    gid = Gid(args.gid.read_bytes())
    if gid.sha256 != GID_SHA256:
        raise ValueError("public GID member hash mismatch; do not feed private/name audio")
    ja, en = read_asr(args.japanese), read_asr(args.english)
    reviewed=set()
    for original,paths in ((ja,args.japanese_review),(en,args.english_review)):
        for path in paths:
            retry=read_asr(path,complete=False)
            reviewed.update(retry)
            original.update(retry)
    overrides = {}
    if args.overrides:
        for row in csv.DictReader(args.overrides.open(), delimiter="\t"):
            i=int(row["clip"])
            if i in overrides or not 0<=i<2071:raise ValueError("duplicate/invalid override")
            if not re.search(r"\[(?:confirmed|likely|guess)\]",row["notes"]):raise ValueError("override needs confidence")
            overrides[i]=row
    clips = []
    sounds = {0,2,3,4,5,6,7,1294,1295,1305,1370,1371,1391,1392}
    for c in gid.clips:
        jp, rj = shorten_repetition(ja[c.index]["text"])
        english, re_ = shorten_repetition(en[c.index]["text"])
        english=nz(english)
        jp,english=redact_example_names(jp),redact_example_names(english)
        flags=[]
        if c.index in reviewed:flags.append("full-context ASR retry used")
        if rj or re_:flags.append("repeated ASR text collapsed")
        if any(int(r[c.index]["tokens"])>=int(r[c.index]["limit"]) for r in (ja,en)):
            flags.append("ASR token cap reached; may be truncated")
        if "\ufffd" in jp+english:flags.append("incomplete UTF-8 from capped model output")
        if float(ja[c.index]["mean_token_probability"])<0.7:flags.append("weak Japanese ASR; listen/review")
        if not jp:flags.append("no Japanese transcript; listen/review")
        cat=category(c.index,jp,english)
        notes="[guess] local ASR Japanese and independent English draft; category inferred from words or neighbouring clips; use unconfirmed"
        known=known_welcome(c.index)
        if known:
            cat,jp,english=known
            notes="[likely] wording normalised from ASR plus [confirmed] NaviWelcomeCC!0x428b8e0c selector/GID mapping"
            flags=[]
        if c.index in sounds or re.fullmatch(r"[（(\[]?(?:音楽|♪.*|チーン|ピンポーン|チャイム|ベル|ピンッ|ピーン)[）)\]]?",jp):
            cat,jp,english="non-speech / tone or music","",""
            notes="[likely] non-speech; no spoken translation; ASR tone hallucinations omitted"
            flags=[]
        source=gid.data[c.offset:c.offset+c.size]
        zero_audio=not any(source)
        if args.decoded:
            with wave.open(str(args.decoded/f"clip{c.index:04d}.wav"),"rb") as wav:
                zero_audio=not any(wav.readframes(wav.getnframes()))
        if zero_audio:
            cat,jp,english="non-speech / silence","",""
            notes="[confirmed] all-zero decoded PCM; no spoken translation"
            flags=[]
        if c.index in overrides:
            row=overrides[c.index]
            cat,jp,english,notes=(row[k] for k in ("category","jp_text","en_nz","notes"))
            flags=[]
        if flags:notes+="; "+"; ".join(flags)
        notes+=f"; descriptor={c.descriptor:#x}; format={c.format.hex()}; bytes={c.size}"
        clips.append([f"GID:clip{c.index:04d}@{c.offset:#x}",cat,jp,english,notes])
    rows=list(clips)
    for i in range(len(gid.boundaries)-1):
        words=gid.playlist(i)
        if not words:continue
        ids=[gid.by_descriptor[v].index for v in words if not v&0x80000000]
        cats=sorted({clips[j][1] for j in ids})
        cat="playlist / "+(" + ".join(cats) if cats else "silence")
        jp=" | ".join(clips[j][2] for j in ids if clips[j][2])
        english=" | ".join(clips[j][3] for j in ids if clips[j][3])
        notes="[confirmed] tokens="+" ".join(gid.tokens(i))
        if jp or english:notes+="; [guess] concatenation draft; | marks clip boundary; grammar/order need review"
        if "\ufffd" in jp+english:notes+="; incomplete UTF-8 inherited from capped ASR; see clip notes"
        if any("ASR token cap reached" in clips[j][4] for j in ids):
            notes+="; ASR token cap reached in referenced clip; see clip notes"
        rows.append([f"GID:phrase{i:#06x}@{gid.boundaries[i]:#x}",cat,jp,english,notes])
    rows.append(["TTS:TJP04000.HDR@0x61","dynamic TTS","","",
                 "[confirmed] Japanese Nbk pipeline/voice at +0x61/+0x189; dynamic runtime text has no finite clip transcript; private input redacted"])
    for name,offset,size,pages in [("BVOICEB",6774456832,798490624,194944),
                                  ("BVOICED",7572947456,2203648,538),("BVOICEI",7575175680,1171456,286)]:
        rows.append([f"DBDIR:{name}@image:{offset:#x}","name audio / redacted","redacted","redacted",
                     f"[confirmed] {size} bytes; {pages} pages (not name counts); [likely] recorded names; payload not read/transcribed"])
    with args.output.open("w",newline="") as f:
        w=csv.writer(f,delimiter="\t",lineterminator="\n")
        w.writerow(FIELDS);w.writerows(rows)
    print(json.dumps({"clips":len(clips),"nonempty_playlists":len(rows)-len(clips)-4,
                      "rows":len(rows),"clip_categories":dict(Counter(r[1] for r in clips)),
                      "table_sha256":hashlib.sha256(args.output.read_bytes()).hexdigest()},indent=2))


if __name__ == "__main__":main()
