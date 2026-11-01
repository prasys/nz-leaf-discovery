"""Pinned English clip sets and locked wording; no card data or private sources.

Greeting selection: NaviWelcomeCC!0x428b8e0c; greetings !0x428b8774.
EV alerts: InfoBarCC!0x433eb060, NaviEvCC!0x42508fbc/0x42508fd8,
ScreenStateCC!0x418fd0a4 and Vehicle.exe!0x0003023c (findings 14 §10).
"""
import csv
import os
from pathlib import Path
import re

GREETING_CLIPS = tuple(range(764, 820))
EV_CLIPS = tuple(sorted((
    428, 429, 430, 431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441,
    442, 444, 548, 1297, 1298, 1299, 1300, 1301, 1302, 1320, 1322,
    1345, 1416, 1417, 1537, 1573, 1594, 1709, 1721, 1722, 1723, 1740,
    1743, 1744, 1745, 1746, 1840,
)))
CLIP_SETS = {"greeting": GREETING_CLIPS, "ev": EV_CLIPS}
# $NISSAN_ROOT/work (default ~/nissan/work) holds every out-of-tree artifact.
WORK = Path(os.environ.get("NISSAN_ROOT", Path.home() / "nissan")).expanduser() / "work"
ROOTS = {
    "greeting": WORK / "language-speech/en-greeting",
    "ev": WORK / "language-speech/en-ev",
}
ROOT = ROOTS["greeting"]
OVERRIDES = Path(__file__).resolve().parents[2] / "translations/voice-prompt-overrides.tsv"
MONTHS = "January February March April May June July August September October November December".split()
WEEKDAYS = "Sunday Monday Tuesday Wednesday Thursday Friday Saturday".split()
ORDINALS = ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
            "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth "
            "twenty-first twenty-second twenty-third twenty-fourth twenty-fifth twenty-sixth "
            "twenty-seventh twenty-eighth twenty-ninth thirtieth thirty-first").split()
ENGLISH = dict(enumerate(["Good morning.", "Hello.", "Good evening.", "Happy New Year."] +
                        MONTHS + [x + "." for x in ORDINALS] + [x + "." for x in WEEKDAYS] +
                        ["Drive safely.", "Don't drink and drive."], 764))
CLIPS = GREETING_CLIPS
# Comparison samples only: never part of the locked render set. "Kia ora" is a
# voice-choice line for the owner; there is no Kia ora clip slot in the greeting
# selector, so render must not emit it.
SAMPLE = "Good morning. Kia ora. January first. Monday. Drive safely."


# Printable English only: this text may be sent to a cloud TTS service.
OWN_TEXT = re.compile(r"[A-Za-z0-9 .,;:!?'\-]{1,120}")


def own_wording(path, clip_set):
    """An owner's own wording file (clip, en_nz), e.g. "Kia ora." for clip 765."""
    with Path(path).expanduser().open() as f:
        rows = {int(r["clip"]): r["en_nz"].strip() for r in csv.DictReader(f, delimiter="\t")}
    clips = CLIP_SETS[clip_set]
    for i in clips:
        if not OWN_TEXT.fullmatch(rows.get(i, "")):
            raise ValueError(f"clip {i}: own wording missing or not plain English")
    return {i: rows[i] for i in clips}


def locked_text(clip_set="greeting"):
    """Return the committed English for one clip set, refusing stale wording.

    VOICE_WORDING names an owner's own wording TSV that replaces the committed
    table for builds the owner pins themselves.
    """
    if clip_set not in CLIP_SETS:
        raise ValueError("unknown clip set")
    if os.environ.get("VOICE_WORDING"):
        return own_wording(os.environ["VOICE_WORDING"], clip_set)
    clips = CLIP_SETS[clip_set]
    with OVERRIDES.open() as f:
        rows = {int(r["clip"]): r for r in csv.DictReader(f, delimiter="\t")}
    expected = ENGLISH if clip_set == "greeting" else None
    for i in clips:
        if i not in rows:
            raise ValueError(f"clip {i}: no committed {clip_set} wording")
        row = rows[i]
        if not re.search(r"\[(?:confirmed|likely|guess)\]", row["notes"]):
            raise ValueError(f"clip {i}: wording must carry a confidence tag")
        if "wording locked" not in row["notes"]:
            raise ValueError(f"clip {i}: committed {clip_set} wording is not locked")
        if expected is not None and row["en_nz"] != expected[i]:
            raise ValueError(f"clip {i}: greeting wording does not match the pinned table")
    return {i: rows[i]["en_nz"] for i in clips}


def output_path(path, clip_set="greeting"):
    """Keep generated audio/artifacts under the selected set's work directory."""
    if clip_set not in ROOTS:
        raise ValueError("unknown clip set")
    path = Path(path).expanduser().resolve()
    if not path.is_relative_to(ROOTS[clip_set]):
        raise ValueError(f"{clip_set} audio/artifacts must stay under {ROOTS[clip_set]}/")
    return path
