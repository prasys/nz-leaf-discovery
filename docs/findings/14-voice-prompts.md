# Voice inventory, welcome/date selection, and the SSC codec

Refs [#14](https://github.com/prasys/nz-leaf-discovery/issues/14). Confidence: **[confirmed]** = bytes/static instructions or a
reproduced tool result; **[likely]** = interpretation or reviewed ASR wording;
**[guess]** = unreviewed transcription, translation, or category. Static reachability
does not prove a particular prompt plays in this car.

## 1. Result and limits

**[confirmed]** The public GID has 2,071 clips: 2,053 SSC-compressed, 17 PCM entries
with format `02010102`, and one PCM entry with `02010101`. The decoder is statically
linked into G214 `Speech.exe`, exported as `SSC_Decode` at VA `0x001d1494` and
`SSC_DecodeInit` at `0x001cfbec`. The Python port decodes recorded guidance without
executing firmware. Directory evidence: member `SJP00000.GID +0x13920`, descriptors
`+0x13940`, 16 bytes each. Validation details and limitations are in §5.

**[confirmed static]** The welcome path is recorded GID playback, selected in
`NaviWelcomeCC!0x428b8e0c`, submitted by `0x428b8680`. Its normal sequence is a
time-of-day greeting followed by **month, day and weekday**, then an optional
safe-driving/alcohol warning. There is no hour/minute selection in this function.

**[likely]** That date announcement explains the owner's report of a boot “time”
announcement. The owner has not yet confirmed this distinction. A separate spoken
clock-time path has **not** been established; do not describe the date selector as
an hour/minute announcer. Static selection and the decoded welcome clips (§3) are
the evidence, not a recording captured from the car.

**[guess]** `translations/voice-prompts.tsv` is a translation **draft**, not a
replacement payload. It inventories every clip and every nonempty GID playlist;
unreviewed Japanese/English comes from local Whisper inference. Notes identify
uncertain wording, repeated/capped output and category guesses. Short numbers,
names and concatenation fragments are particularly error-prone. A high model token
probability is not evidence that a transcript is correct. Empty/reserved phrase
slots have no spoken text and are enumerated by the catalogue tool rather than
expanded into translation rows.

**[confirmed inventory]** The TSV has 5,418 data rows: 2,071 clips, 3,343
nonempty playlists, one dynamic-TTS source and three redacted BVOICE metadata
entries. Row IDs include member audio/playlist offsets; descriptor offsets and
sizes are in notes. **[guess]** Broad fragment categories may use neighbouring
clips as context. Clip 1357 remains unclassified rather than inventing text.
Tone/silence rows have no translation. The committed overrides preserve a review
trail; language corrections from ASR are still explicitly uncertain, rather than
claimed as a native-speaker listening pass. The original broad draft had 154 override rows;
87 remaining clip rows flag a token cap, and eight contain explicitly flagged
incomplete UTF-8 from ASR. Clip 1357 has neither transcript nor translation.
These are concrete outstanding review items, so [#14](https://github.com/prasys/nz-leaf-discovery/issues/14) remains open (`Refs`).

**[confirmed]** No BVOICE or phonebook audio was decoded/transcribed. Their scope
is counts and offsets (§2). No card/car/device writes, firmware execution, sudo,
or original-image modifications were used. Outputs are under
`~/nissan/work/language-speech/`; the image is opened `rb` by the metadata walker.

## 2. Sources and categories

**[confirmed]** `speech_sources.py` finds 249 public files under `SPEECH/JP` using
the FAT32 directory rooted at LBA 888833. These first image offsets identify the
files; use the FAT chain, not an assumption of contiguous allocation, to read them:

| Public source | First image byte | Bytes | Evidence/use |
|---|---:|---:|---|
| `SPEECH/JP/GID/SJP00300.GID` | 13,346,210,304 | 37,882,424 | [confirmed] FAT entry; archive member starts at file `+0x38` |
| `SPEECH/JP/TTS/TJP00300.TTS` | 13,384,221,184 | 52,516,848 | [confirmed] FAT entry; Nuance TTS container |
| `SPEECH/JP/VR/VJP00300.AGM` | 13,436,846,592 | 1,285,820 | [confirmed] FAT entry; recognition grammars, not a second recorded prompt inventory |

**[confirmed]** Private/name-source metadata below comes only from directory/FAT
entries, not the payload. Page counts are file sizes divided by 4096, **not counts
of names or clips**. The number of BVOICE audio records remains unknown.

| Source | First image byte | Bytes / metadata count |
|---|---:|---|
| `DBDIR/BVOICEB` | 6,774,456,832 | [confirmed] 798,490,624 bytes; 194,944 pages; content redacted |
| `DBDIR/BVOICED` | 7,572,947,456 | [confirmed] 2,203,648 bytes; 538 pages; content redacted |
| `DBDIR/BVOICEI` | 7,575,175,680 | [confirmed] 1,171,456 bytes; 286 pages; content redacted |
| Hidden p2 `SPEECH` subtree | directory-entry bytes 15,342,207,488–15,351,120,576 | [confirmed] 21 generated-grammar files; zero files under a `VTG` directory in this snapshot; filenames/content withheld |

**[likely]** BVOICE uses related compressed name audio: the earlier fingerprint
was observed at BVOICE file `+0x100000` (04 §1.5). This investigation proves the
GID SSC decoder, not the BVOICE page/record wrapper. Zero `VTG` files under the
scanned speech subtree does not prove the absence of tags elsewhere in PRIVATE,
other stores, deleted records, or a later card snapshot.

**[likely/guess]** Public GID material spans the categories below. Clip numbers
are zero-based; the TSV gives each clip's exact audio/descriptor offsets and each
playlist's tokens. Categories inferred from speech are drafts, not firmware
enablement claims. Shared regional/vehicle prompts can be present but unused.

| Category | Example evidence | NZ English intent |
|---|---|---|
| Greeting | [likely text; confirmed selection] clips 764–767; `0x428b8e0c` | Good morning / Hello / Good evening / Happy New Year |
| Date | [likely text; confirmed selection] clips 768–817; phrase IDs `0xb14–0xb45` | Month, date and weekday |
| Time / ETA components | [guess wording/use; confirmed playlist references] clips 1172/1184/1196 at phrase IDs `0x29e/0x2bc/0x2db` | Recorded hours/minutes, often with “around”; presence does not establish a boot clock announcement |
| Safe driving / alcohol | [likely text; confirmed selection] clips 818–819, `0x428b8e0c` | Drive safely today / If you've been drinking, don't drive |
| Route guidance, distances, turns, lanes, destinations | [guess text/category] e.g. clips 11–75, 379–400, 745–763 | Turn directions, route changes, arrival and restrictions |
| Public landmark / road-name fragments | [guess text/category] e.g. clips 127–372, 557–572, 606–743 | Landmark and road names used to assemble directions; distinct from redacted BVOICE |
| Traffic / emergency information | [guess text/category] e.g. clips 62–72, 387–400 | Congestion, closures, roadworks and warnings |
| Phone / Bluetooth / operator | [guess text/category] e.g. clips 401–427 | Calling, hold, redial, pairing and connection status |
| Vehicle / toll / generic warnings | [guess text/category] e.g. clips 428–550 | Doors, ETC cards/gates, fees, parking brake and fuel warnings; presence is not proof of LEAF use |
| Voice-recognition dialogue | [guess text/category] ASR help, selection, retry and confirmation clips in the TSV | What can I say, select, confirm, retry; grammars themselves are input recognition data |
| EV / charging / energy | [guess text/category] charging and battery entries in the TSV | Charging stations, remaining range/charge and charging advice |
| Non-speech | [confirmed zero bytes] PCM clips 1393–1397; [likely tones/music] other entries marked non-speech in the TSV | No spoken translation |
| Dynamic TTS | [confirmed source] `TJP04000.HDR +0x61/+0x189/+0x2a7`; `Speech.exe` text/PCM pipeline | Runtime-supplied Japanese text; no finite clip transcript |

## 3. Boot greeting and the date announcement

**[confirmed static]** The welcome module's `.text` is raw in the G214 o32
listing (vbase `0x428b0000`), so the compressed-section E8 omission in §4 does
not alter this selector. The traced chain is:

| Step | Function / message | Evidence |
|---|---|---|
| Register welcome speech access | `0x428c4b1c` | [confirmed] calls `0x428c6d98` with mode `0x13`, callback message `0x86000010`, flags `2` |
| Window dispatch | `0x428c31c4` | [confirmed] message `0x1985` → `0x428b90e0`; message `0` → `0x428b9168` |
| System-state notification | `0x428b90e0` | [confirmed] subevent `0x265`; trace literal at `0x428b9164` points to `0x428b18d8`, `SS->WelcomeCC` |
| Speech readiness notification | `0x428b9168` | [confirmed] `wParam=0x13` (`SPEECH_MODE_WELCOME`), `lParam & 2` (`SPEECH_VALID_REC_INDEX`); trace strings `0x428b1980`, `0x428b1910` |
| Decide phrases once ready | `0x428b8e0c` | [confirmed] readiness/one-shot guards; reads `Guide2WelcomeMessage` and `Guide2SafeDrivingMessage`; enabled value `2` |
| Build recorded request | `0x428b8680` → `0x428c7210` → `0x428c6460` | [confirmed] AddRecord for each selected ID; type `2` at tag `0xf010200`, phrase ID at `0xf010201`; then ExecRequest |
| Read a GID phrase | `Speech.exe!0x00134b94` → `0x00134cb0` | [confirmed] adjacent boundaries; high bit = silence, otherwise a descriptor; codec byte `4` maps to decode kind `5` |
| Decode SSC | `Speech.exe!0x001249f8` → `SSC_DecodeInit` / `SSC_Decode` | [confirmed] mono, 128-sample blocks, PCM output submitted through `0x001223f0` |

**[confirmed static]** `0x428b8774` chooses greeting slots as follows. Text is
**[likely]**, independently recognised from decoded audio; selector ranges/IDs
are **[confirmed]** from the instructions and GID directory:

| Condition | Phrase | Clip / member audio offset | Japanese → NZ English |
|---|---|---|---|
| 05:00–10:59:59 | `0xb0e` | 764 / `0x994c98` | おはようございます → Good morning. |
| 11:00–17:29:59 | `0xb0f` | 765 / `0x997c50` | こんにちは → Hello. |
| 17:30–04:59:59 | `0xb10` | 766 / `0x999900` | こんばんは → Good evening. |
| First eligible Jan 1 greeting, taking precedence over the above | `0xb11` | 767 / `0x99b3a0` | あけましておめでとうございます → Happy New Year. |

**[confirmed static]** The date construction in `0x428b8e0c` is
`0xb13 + month`, `0xb1f + day`, `0xb3f + weekday_index` (Sunday = 0). GID
`0xb14–0xb1f` points to clips 768–779 (January–December), `0xb20–0xb3e` to
780–810 (1st–31st), and `0xb3f–0xb45` to 811–817 (Sunday–Saturday). The
corresponding zero-month/day slots are empty. It appends `0xb47` or `0xb48`
(clips 818/819) when the safe-driving option/period checks permit.

**[confirmed static]** Previous-announcement dates and time periods gate repeats
(`0x428b8774`, `0x428b8998`, `0x428b8aac`; persisted-date helpers at
`0x428c512c`, `0x428c5194`, `0x428c51fc`). Do not assume the complete sequence
is repeated on every ignition or re-entry.

**[confirmed static]** The selector reads `OBJ_Time_readGMT` and calls
`STD_Time_addBase(..., 0x317040)` at `0x428b8e0c`; the same fixed JST base is
documented in the clock analysis. It does not call the displayed-clock offset
getter here. **[likely]** Greeting/date choice can therefore remain on Japan
time despite the working skin-only NZ display fix. This finding changes none of
12 §0.2's assumptions: no stock setter, VSRAM, skin trailer, baseline or dormant
G214 probe was changed or activated.

**[confirmed scope]** The `MSG_SPEECH_GUIDE_OUTPUT` lead in 04 is a diagnostic
trace string (`DiagnosisCC.dll` file `+0x2660`, inner name at `+0x2684`). The
welcome path above is evidenced by its own speech-access registration/callbacks;
the diagnostic string alone neither identifies a decoder nor proves the boot
trigger. The top-level ignition/system-state producer of subevent `0x265` has
not been traced end to end.

## 4. Correct the extraction before reversing the codec

**[confirmed]** The old `cecompress.py` treats `5b 80 80 8d` as a separate magic
and calls the LZX decoder at `pos=4`. These bytes actually encode flag 1 and the
E8 translation size 12,000,000. The next bit, consumed as a new flag by the old
tool, is zero; block parsing happens to work but translation is omitted. Reading
the full stream at position zero fixes it. The LZX header/translation rule is
described by [Microsoft MS-PATCH §2.2.2](https://learn.microsoft.com/en-us/openspecs/exchange_server_protocols/ms-patch/e6c8366d-a8c3-4f34-aa5d-56f44f938a09).

**[confirmed]** Example from the old Speech PE: the ARM pop ends in byte `e8`
at VA `0x1cf7bf`; the literal at `0x1cf7c0` reads `0x6b38f`. Correct page-local
E8 reversal subtracts `0x7bf`, yielding `0x6abd0`, the aligned band boundary
table. The bogus `BLNE 0x39a6d4` at `0x1cf72c` becomes the local loop branch
after the same correction. Speech `.text` is CE-compressed at unpacked-ROM VA
`0x8aaeab18`, stored size 2,533,459 (G214 extraction listing).

**[confirmed]** `extract_speech.py` rebuilds only Speech.exe to a new output,
using the existing trusted ROM/PE helpers and full per-page LZX headers. The
corrected PE is 8,277,504 bytes, SHA256
`5a43580038282eeea0a4862ae83cc78a8b040cf6415bce9f01b78463a10c92a6`.
Existing extracted trees remain untouched. The general extractor fix and audit
of previous compressed-section analyses are tracked separately.

## 5. GID layout, decoder and validation

**[confirmed]** All offsets in this section are relative to the inner member;
add outer file `0x38`, then follow FAT extents for image coordinates. Source
SHA256s are in `binaries/MANIFEST.md`.

| Offset | Meaning |
|---|---|
| `+0x00` | [confirmed] 14,421 boundary entries; firmware reads adjacent entries at `0x134b94` |
| `+0x04` | [confirmed] playlist area start `0xe1a0` |
| `+0x08` | [confirmed] playlist region size `22400 = 0x5780`; **not a sample rate**; next header is `0xe1a0 + 0x5780 = 0x13920` (`0x1348d0`) |
| `+0x40` | [confirmed] boundary table; starts `0xe1a0,0xe1a0,0xe1a4,...`; last boundary `0x13904` at `+0xe190` |
| `+0xe1a0` | [confirmed] u32 playlist tokens: bit31 set = milliseconds of silence; otherwise a descriptor offset |
| `+0x13920` | [confirmed] 2,071 clips; descriptor-region size `0x81a0`; audio-region bytes `37,769,024`; alignment field `4` at `+0x13930` |
| `+0x13940` | [confirmed] 16-byte descriptors: format[4], audio offset, padded size, real size |
| `+0x1bac0` | [confirmed] first clip data; region end is member size `37,882,368` |

**[confirmed]** Adjacent boundaries yield 14,420 bounded phrase slots, 3,343
nonempty and 11,077 empty. The final boundary is a sentinel, not another
well-bounded playlist. Identical adjacent offsets mean an **empty slot**, not
multiple aliases of one playlist (`Speech.exe!0x134b94`). The parser validates
every referenced descriptor and every file extent.

**[confirmed static]** `0x134cb0` maps descriptor codec byte `1` to PCM kind `3`,
`2` to another decoder kind `1`, and `4` to SSC kind `5`. All compressed entries
on this card have byte `4`. Descriptor byte 3 value `2` maps to internal rate
enum `2`; `0x121444`'s RIFF reader maps 22,050 Hz to that same enum. Value `1`
maps to enum `0`, corresponding to 11,025 Hz. Thus clip 1295's `02010101` is
16-bit PCM at a different rate, not proof of 8-bit PCM. `0x120c9c`/`0x121f50`
also show conversion of that rate to the default output by two-for-one samples.

**[confirmed static]** SSC is a variable-rate, entropy-coded lapped transform
codec, not the failed G.726 interpretation. The implementation has:

- MSB-first bytes (`0x1cf2d8`), 128 output samples per mono call (`0x1d1494`).
- Fifteen 3-bit band modes; first-mode 7 ends the stream; second-mode 7 denotes
  a zero block (`0x1d02f8`).
- Bands at VA `0x6abd0`: `0,8,16,...,112,128`; scalar/vector Huffman tables at
  `0x6b8c8` and `0x6c050` (`0x1cf83c`).
- Signed/magnitude vectors with escape values, a 5-bit initial scale factor and
  fourteen 3-bit delta factors (`0x1d02f8`); inverse quantisation at `0x1cf6b8`.
- A fixed-point, 128-sample overlap transform (`0x1d0bfc`), rotations
  (`0x1cfce8`), butterfly stages (`0x1d0830`), rounded signed multiply
  (`0x1cf9ac`); twiddle/rotation/window data at `0x6c720/0x6c920/0x6cb20`.

**[confirmed scope]** `ssc_decode.py` ports the mono path and reads these tables
as data from the hash-pinned corrected PE. It does not emulate or call the ARM
exports. Stereo and the exported SSC encoder were not ported in the initial decoder
work. The later owner-authorised mono encoding implementation is described in §8. The acronym's
expansion/vendor ownership was not established; “SSC” is the firmware's symbol
name, not a claim that this is a documented standard or the TTS MRF coder.

**[confirmed validation]** All 2,053 compressed entries decode to an explicit
end marker, with no more than seven padding bits remaining. Synthetic tests
cover MSB order, truncation, illegal markers, silence, a transform zero block,
escape dequantisation, signed fixed-point rounding, archive/boundary/descriptor
validation and the E8 header. The final full run also emits all 18 PCM entries.

**[confirmed repeatability]** A second full export from the outer GID wrapper
matches every PCM sample of the first member-based export. `verify_audio.py`
checks all 2,071 files, 2,053 SSC frame counts, all 18 raw PCM payloads, and rates
(2,070 at 22,050 Hz; one at 11,025 Hz). Total clip duration is 3,603.996281 s.
The deterministic `public-gid-wavs.zip` contains only those public WAVs and their
individual PCM/WAV hashes; its SHA256 is pinned in `binaries/MANIFEST.md`.

**[confirmed timing]** A decoded SSC block lasts `128/22050 = 5.8049887 ms`.
Clip 764 has 23,424 samples (1.062313 s); clip 765 has 14,720 (0.667574 s);
clip 766 has 14,208 (0.644354 s). PCM clip 1294 has exactly 44,100 bytes =
22,050 samples = 1 s at the same rate. PCM clip 3 has 53,258 bytes = 26,629
samples = 1.207664 s. Playlist silences are milliseconds, independent of codec
frame timing. These checks establish rate/units and intelligible output; they
are **not** a sample-for-sample comparison with audio captured from the unit.

**[likely independent check]** Local Whisper recognises the four greetings,
the month/day/weekday series and both safety messages from decoded WAVs in the
order predicted by the firmware. There is no firmware-execution oracle; bit-exact
agreement with the original decoder has not been proved. Output-cap, spelling,
and translation review remain necessary, especially for tiny fragments.

**[confirmed correction to 04]** The earlier `+0x38` boundary-table location,
“14,421 playlists”, unknown GID codec, and claim that PCM 1391–1397 are all
silence are superseded here. The table starts `+0x40`, includes a final sentinel,
and SSC is decoded. PCM 1391/1392 have respectively 9,550/3,105 nonzero bytes;
only 1393–1397 are all-zero payloads. Those five silence payloads have odd
lengths; WAV export retains complete 16-bit samples and drops the incomplete
last byte. The original member bytes are preserved.

## 6. Reproduce without a card write

All commands below run trusted repo tools or installed analysis software. The
G214 ROM input is the already unpacked `~/nissan/work/ce-extract/G214JLNI.066.nb0`;
its SHA256 matches the `work/mtcp/g214-rom.bin` manifest entry. Use a fresh output
name/directory: the extractor/decoder refuse overwrites.

```sh
mkdir -p ~/nissan/work/language-speech/analysis
python3 -I tools/language-speech/speech_sources.py \
  --extract-gid ~/nissan/work/language-speech/SJP00300.GID \
  > ~/nissan/work/language-speech/analysis/sources.json
python3 -I tools/language-speech/extract_speech.py \
  ~/nissan/work/ce-extract/G214JLNI.066.nb0 \
  ~/nissan/work/language-speech/rom/Speech.exe
python3 -I tools/language-speech/gid_catalog.py \
  ~/nissan/work/language-speech/SJP00300.GID \
  --clips ~/nissan/work/language-speech/analysis/clips.tsv \
  --phrases ~/nissan/work/language-speech/analysis/phrases.tsv
python3 -I tools/language-speech/ssc_decode.py \
  ~/nissan/work/language-speech/SJP00300.GID \
  ~/nissan/work/language-speech/rom/Speech.exe \
  ~/nissan/work/language-speech/decoded-final \
  > ~/nissan/work/language-speech/analysis/decode-final.tsv
python3 -I tools/language-speech/test_speech.py
python3 -I tools/language-speech/verify_audio.py \
  ~/nissan/work/language-speech/SJP00300.GID \
  ~/nissan/work/language-speech/decoded-final \
  --bundle ~/nissan/work/language-speech/public-gid-wavs.zip
```

**[confirmed tooling]** This session used Ghidra 12.2, its automatic
`ARM:LE:32:v8/windows` PE selection, and installed OpenJDK for static exports.
Projects are `~/nissan/work/ghidra/voice57_{welcome,speech,speech_fixed}`. Exports
and logs stay in the language-speech analysis directory. `SpeechTrace.java`
exports selected functions, assembly, callers and callees; `SpeechRefs.java`
exports functions referencing a specified string/data address. For example:

```sh
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless \
  ~/nissan/work/ghidra voice57_speech_fixed -process Speech.exe -noanalysis \
  -scriptPath tools/language-speech -postScript SpeechTrace.java \
  ~/nissan/work/language-speech/analysis/codec-fixed.txt 3 \
  001d1494 001cfbec 001d02f8 001cf83c
```

**[confirmed tooling]** `brew install whisper-cpp` resolved to `whisper.cpp`
1.9.5 and installed libomp 23.1.4, ggml 0.28.0, openssl@4 4.1.0 and llama.cpp
0.8.0 as dependencies. No other packages were installed. The multilingual
`ggml-small.bin` model came from the
[upstream model repository](https://huggingface.co/ggerganov/whisper.cpp).
The installed Metal backend failed to compile on this M1 Max, so the local batch
tool loads CPU/BLAS backends explicitly. Paths below are Homebrew/macOS-specific:

```sh
c++ -std=c++17 -O2 -I/opt/homebrew/include \
  tools/language-speech/whisper_batch.cpp -L/opt/homebrew/lib \
  -lwhisper -lggml -o ~/nissan/work/language-speech/whisper-batch
VOICE_GGML_CPU=/opt/homebrew/opt/ggml/libexec/libggml-cpu-apple_m1.so \
VOICE_GGML_BLAS=/opt/homebrew/opt/ggml/libexec/libggml-blas.so \
  ~/nissan/work/language-speech/whisper-batch \
  ~/nissan/work/language-speech/models/ggml-small.bin \
  ~/nissan/work/language-speech/decoded-final \
  ~/nissan/work/language-speech/analysis/transcript-ja.tsv 0 2071
# Repeat with VOICE_TRANSLATE=1 and transcript-en.tsv for the English draft.
```

**[guess workflow]** The batch tool resamples public WAVs locally to 16 kHz,
uses a bounded token count to limit repetition, and records raw model token
probabilities. `build_voice_table.py` combines those drafts with reviewed
overrides, applies NZ spelling, and expands playlist references. Its output must
be reviewed by a Japanese speaker before use in a replacement build.

**[guess workflow]** Full-context retries were used for Japanese clips
`365,1444,1502,1538,1659,1674,1728,1876,1882,1884,1886,1918,1920`, then `1994`;
and English clips `1446,1494,1538,1590,1652,1742,1878,1918,1924,1925,1956,1994`.
Repeat the batch command with `VOICE_FULL_CONTEXT=1`, `VOICE_REVIEW_IDS` set to
the relevant comma-separated IDs, a fresh output TSV, and the same `0 2071`
range. Set `VOICE_TRANSLATE=1` for English. This reduces some repetition but does
not validate accuracy. The batch outputs stay outside git; the pinned public
WAV bundle permits independent listening/review.

```sh
python3 -I tools/language-speech/build_voice_table.py \
  ~/nissan/work/language-speech/SJP00300.GID \
  ~/nissan/work/language-speech/analysis/transcript-ja.tsv \
  ~/nissan/work/language-speech/analysis/transcript-en.tsv \
  translations/voice-prompts.tsv \
  --overrides translations/voice-prompt-overrides.tsv \
  --decoded ~/nissan/work/language-speech/decoded-final \
  --japanese-review ~/nissan/work/language-speech/analysis/review-ja.tsv \
  --japanese-review ~/nissan/work/language-speech/analysis/review-ja-extra.tsv \
  --english-review ~/nissan/work/language-speech/analysis/review-en.tsv
```

## 7. Initial replacement feasibility — description only (superseded in scope by §8)

**[confirmed layout]** Recorded welcome/date clips live in the p1 GID file, not
in the translated skin. A later writer must follow its FAT32 cluster chain and
pin the **live GID baseline** plus full-card backup and payload hashes. No GID
writer was built in the initial investigation; the owner later authorised the
scoped writer described in §8. GID outer `+0x10/+0x20` gives file/member extents; the inner
header, boundaries, descriptors and audio extents are described in §5.

**[likely]** A same-size experiment can retain the allocation and archive length,
replace one clip inside its existing padded extent, and update its codec/rate/size
descriptor as needed. The stock PCM path is supported (`0x134cb0`), so a valid
mono PCM replacement is a candidate without writing an SSC encoder. PCM usually
needs substantially more bytes; an English recording may exceed the old extent.
Padding, duration changes, playlist pauses and playback arbitration all need
validation. “Same size” is a constraint to check, not a guarantee of feasibility.

**[likely]** A larger rebuild would have to regenerate all affected descriptor
offsets/padded sizes, inner region lengths and outer member/file sizes; changing
playlist token counts also moves boundaries and the clip table. Growing a p1
file additionally changes FAT allocation and directory size. A conservative
first owner-run writer should avoid growth and refuse any mismatch.

**[confirmed scope]** The examined GID loader (`0x1348d0`, `0x134b94`, `0x134cb0`)
checks extents and maps formats; no checksum validation was found in those
functions. This is **not** proof that there is no validation elsewhere. The
skin trailer/checksum experiments and dormant G214 probe do not establish GID
acceptance. No file was changed on a card to test this.

**[confirmed source]** The installed TTS voice is Japanese Nbk, with a
`pipeline/Japanese/nbk/22/dri80_1175mrf22/text/pcm` broker string at
`TJP04000.HDR +0x4b`, voice at `+0x189`, and 22,050 Hz at `+0x2a7`.
The public speech directory has only JP data (249 entries; metadata inventory).
**[likely]** English TTS requires compatible, appropriately licensed English
voice/language data and engine configuration; a language menu or English voice
name in code is not an installed English voice. It would also require translating
the runtime text supplied to TTS. Switching a voice alone does not translate
Japanese sentences, and translating the skin does not replace these recordings.

**[confirmed owner input; likely generation workflow]** The owner has ElevenLabs
available for generating reviewed NZ English recordings. No ElevenLabs audio was
requested/generated/uploaded in this investigation. Use an authorised synthetic
voice, export lossless audio, then convert/resample to the verified mono PCM16
format/rate before checking duration and byte budget against the exact GID
extent (§5, `0x134cb0`). Preserve clip boundaries intentionally: independently
recorded fragments can join poorly. Do not upload private BVOICE/phonebook audio
or use it as voice-cloning input. Generation is a later preparation step; it
does not establish firmware acceptance or justify writing a card.

**[likely]** Natural NZ date ordering (weekday/day/month) needs sequencing changes
or deliberately chosen wording; the confirmed selector emits month/day/weekday
(`0x428b8e0c`). Likewise, translating spoken command examples does not install
English recognition grammar (`VJP00300.AGM`, source offset in §2). English VR
commands require a separate compatible recognition-language/grammar solution.
Retaining Japanese command words in English help may be an interim wording
choice after owner review. These constraints also apply to ElevenLabs recordings.

**[likely next validation]** For an eventual cloned-card experiment, first
review the transcript/English wording, choose one harmless short clip, verify its
playlist and extent, and prepare an owner-run preflight/apply workflow under
`docs/BACKUPS.md`. Do not call or activate the historical G214 clock probe. Exact
card writes, backup/rollback/receipt behaviour and fault-injection tests were
subsequently authorised for the start-up set only; see §8.

## 8. Owner-directed start-up replacement

### 8.1 Scope, wording and current gate

**[confirmed scope]** The next build is limited to the 56 clips selected by
`NaviWelcomeCC!0x428b8e0c`: 764–819, mapped in §3. No navigation, VR, toll or
phone clips are being translated/generated/patched in this follow-up. Existing
broader draft rows remain inventory history. A complete catalogue-reference
check finds no use of these 56 descriptors outside phrase IDs `0xb0e–0xb48`.
Greeting selection at `0x428b8774` reaches only four spoken greetings. Phrase
`0xb12` contains `silence:50ms`; it is not evidence of a “welcome home” recording.
No such extra greeting is invented or substituted for another clip.

**[likely wording; confirmed mapping]** `translations/voice-prompt-overrides.tsv`
now explicitly locks the English below, with source clip IDs and selector address
in each note. `greeting.py` enforces this exact allowlist before any generation.
The corresponding rows/playlist expansions in `voice-prompts.tsv` are refreshed.

| Clip(s) | Locked English |
|---|---|
| 764 / 765 / 766 / 767 | Good morning. / Hello. / Good evening. / Happy New Year. |
| 768–779 | January … December, spoken month names |
| 780–810 | first. … thirty-first., spoken ordinal words rather than ambiguous digit input |
| 811–817 | Sunday. … Saturday. |
| 818 | Drive safely. |
| 819 | Don't drink and drive. |

**[likely wording constraint]** Keep the confirmed month → day → weekday order
(`0x428b8e0c`), with existing 100/250/500 ms playlist pauses (§3/§5). Example:
“Good morning. January first. Monday. Drive safely.” Month-first is understandable
English; the trailing weekday is awkward compared with natural NZ
weekday/day/month order. Every date override explicitly flags this limitation.
Do not reverse IDs, alter the date-selector firmware or repurpose clip contents
to disguise the order. The greeting/date calculation still uses the fixed JST
base discussed in §3; this audio-only work does not fix that separate behaviour
or change findings 12's assumptions.

**[confirmed session state]** The key was supplied through the owner's
`ELEVENLABS_ENV_FILE` file and loaded in-process; it was never printed, copied
into the worktree or committed. Three public NZ-accent voices were sampled
(Brendan, Wikitoria Maree, Penny) and the owner chose **Penny – Warm
Antipodean** (`TRrl1hXRI8ISfQPDN0Bf`). The 56-clip English set was rendered,
fitted and recorded in `translations/greeting-slot-fits.tsv`; see §8.3. No voice
is cloned, no private/name audio is used, and no card or car write was attempted.
The earlier budget-only state (no key, `PENDING_VOICE_SELECTION` in every row) is
superseded by this result.

### 8.2 English-only API and sample workflow

**[confirmed tool behaviour]** `eleven_greeting.py` reads only locked English
from the committed overrides; it accepts no card, ROM, Japanese transcript,
private name audio, or audio-upload input. TTS requests contain that English
text plus model/voice settings. Authentication is read in process from
`ELEVENLABS_API_KEY`. Redirects are refused; HTTP error bodies/headers and request
headers are never printed/saved. Credentials are not included in generation
receipts. No automatic retry risks duplicate paid requests; `--resume` reuses
completed WAVs only after checking their receipt, voice, text and hash.

The implementation follows the official
[List shared voices](https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared),
[List voices](https://elevenlabs.io/docs/api-reference/voices/search), and
[Create speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
APIs. **[confirmed API configuration]** Requests ask for `pcm_22050`, model
`eleven_multilingual_v2`, seed 57, stability 0.65, similarity 0.75, style 0,
speaker boost on and speed 1.0. Returned raw PCM is wrapped as mono PCM16 WAV;
the seed is a best-effort service setting, not a promise of identical rerenders.

**[likely selection workflow]** First inspect public NZ-accent choices; if fewer
than 2–3 suitable accessible voices exist, compare public default voices with a
neutral delivery. Accent labels are provider metadata, not listening validation.
Do not inspect private account voice samples or clone a voice. If a public
library voice needs adding to the account before TTS, `add-voice` accepts only a
public-library catalogue entry. The following commands create only out-of-tree
metadata/audio; replace the voice-ID placeholders with the actual catalogue IDs:

```sh
python3 -I tools/language-speech/eleven_greeting.py voices \
  --accent 'new zealand' \
  --output ~/nissan/work/language-speech/en-greeting/voices-nz.json
python3 -I tools/language-speech/eleven_greeting.py voices --defaults \
  --output ~/nissan/work/language-speech/en-greeting/voices-default.json
# Only if a selected public-library voice needs adding:
python3 -I tools/language-speech/eleven_greeting.py add-voice \
  --catalog ~/nissan/work/language-speech/en-greeting/voices-nz.json \
  --voice <public-library-voice-id>
python3 -I tools/language-speech/eleven_greeting.py samples \
  --voice EKI2BOK1fZbXqctp4vgZ --voice kb3tldKFXsDhAalrgD0r \
  --voice TRrl1hXRI8ISfQPDN0Bf \
  --output ~/nissan/work/language-speech/en-greeting/samples-v1
# Owner chose Penny (option-3), so render only that voice:
python3 -I tools/language-speech/eleven_greeting.py render \
  --voice TRrl1hXRI8ISfQPDN0Bf \
  --output ~/nissan/work/language-speech/en-greeting/render-penny-v1
```

**[confirmed tool behaviour]** Samples all use the same short English sentence:
“Good morning. Kia ora. January first. Monday. Drive safely.” The "Kia ora" line
exists **only** in `greeting.SAMPLE` for voice comparison: the confirmed selector
has no Kia ora slot, so it is never part of `locked_text()` or the full render.
Output names are `option-1.wav` … `option-3.wav`, with per-file
text/settings/hash JSON receipts. The full render uses `clip0764.wav` …
`clip0819.wav` plus receipts. Every new English audio/encoded/preview artifact
stays under `~/nissan/work/language-speech/en-greeting/`. Once actual samples
exist, post
links and public voice descriptions in the Orca status for the owner to choose;
do not label an ungenerated option as ready.

### 8.3 Slot budgets, SSC encoding and same-size build

**[confirmed bytes]** Welcome audio is at member `0x994c98–0xa11b74` (end
exclusive); descriptor sizes are in `greeting-slot-fits.tsv`. The smallest slot
is 4,248 bytes (clip 782), the largest 23,692 (clip 819). At 22,050 Hz × 2 bytes,
PCM accommodates only 0.096327–0.537234 seconds. Trimming or a small speed change
cannot generally make a normal multi-word greeting fit as PCM. `0x134cb0` accepts
both PCM and SSC formats (§5), so the fitter uses PCM where possible and SSC
otherwise, keeping each existing offset and padded allocation.

**[confirmed static/local]** `ssc_encode.py` is new host Python code, not an
executed/emulated firmware binary. It ports the analysis window/folding from
`Speech.exe!0x1d0f44`, conjugate rotation `0x1cfd88` and butterfly `0x1d09e8`;
all tables are read as data from the same hash-pinned corrected PE (§4/§5).
Entropy packing inverts the decoded Huffman/vector/sign/escape rules
(`0x1cfe28`, `0x1d11c4`, `0x1cf83c`). Its band quantisation and rate selection
are our policy, not a claim of reproducing the original encoder's perceptual
allocation. Scale deltas stay in the decoder's -5…+2 range. Encoding adds and
flushes one 128-sample lapping block; SNR comparisons account for that delay.

**[confirmed local validation]** A 440 Hz synthetic sine round trip at the finest
setting measured approximately 36 dB SNR. All 56 original *public welcome* clips
were re-encoded locally in memory and self-decoded, with minimum 34.760 dB SNR
at that setting. None of those finest-setting re-encodes fit its original slot;
these are codec-validation results, **not English fits**. Only a JSON result was
saved (`en-greeting/codec-validation/original-welcome-roundtrip.json`); no card
content was sent to ElevenLabs. There is still no original firmware decoder
execution oracle or car playback proof.

**[confirmed fitting policy]** `prepare_greeting.py` validates all 56 generation
receipts and their text/voice/WAV/PCM hashes, requires a single voice, trims only
quiet ends with 20 ms context retained, tries PCM then SSC quantisation settings
-2, -1, 0, 1, and pitch-preserving speeds 1.00/1.04/1.08/1.12. It never truncates
spoken content or permits faster speech. Every SSC candidate is decoded locally;
a fit requires both encoded bytes ≤ the old padded slot and local SNR ≥ 20 dB.
SNR is a numerical guard, not proof of perceptual quality. A fit/overflow table
records raw/trimmed lengths, speed, codec, byte budget, spare/overflow bytes and
SNR. Any overflow or quality failure prevents GID output; review/shorten/regenerate
rather than silently increasing the limits. Listen to the **decoded** previews,
including concatenated dates, before considering a card test. A successful build
also emits `welcome-example.wav` using the real phrase tokens and pauses for
`0xb0e/0xb14/0xb20/0xb40/0xb47` (morning, January, first, Monday, safe driving).

```sh
# Already run: budgets only; no English audio required.
python3 -I tools/language-speech/prepare_greeting.py \
  ~/nissan/work/language-speech/SJP00300.GID --budget-only \
  --output ~/nissan/work/language-speech/en-greeting/budgets-v1
# After the owner selects a voice and the full English render exists:
python3 -I tools/language-speech/prepare_greeting.py \
  ~/nissan/work/language-speech/SJP00300.GID \
  --speech-exe ~/nissan/work/language-speech/rom/Speech.exe \
  --audio ~/nissan/work/language-speech/en-greeting/render-penny-v1 \
  --output ~/nissan/work/language-speech/en-greeting/build-penny
```

**[confirmed result]** Penny's render
(`~/nissan/work/language-speech/en-greeting/render-penny-v1`) was fitted with the
second command above (`--audio render-penny-v1 --output build-penny`). All **56
clips FIT** at speed 1.00, every one as SSC (`02040102`) with no PCM clip:
local SNR is 25.404 dB minimum (clip 776, 35 spare bytes) and 31.086 dB median.
A same-size candidate GID was built: 37,882,424 bytes, SHA256
`7e007bfb5c40f0039dc30fc1749ce91d819352bf5275c317cfb83cca075af0c1`, identical
across two runs; `welcome-example.wav` is
`a81c84a1a56976c387adb92d72316aa2e5fa3f899d0085d1a467c8b5cdcdcca0`. This is a
local encode/self-decode result, not car playback. A PCM-only projection (2.70 MB
against 511,630 bytes of slots) would have overflowed everywhere; SSC compression
is what brings the set inside the stock extents. `translations/greeting-slot-fits.tsv`
now carries this fit table, including the source WAV `wav_sha256` and
`input_seconds` columns added for the manifest.

**[confirmed build guard]** `gid_patch.py` requires the pinned stock outer GID
SHA256 (§5 / manifest), exactly clips 764–819, and same length. It permits changes
only to those descriptors' format/real length and their allocated audio bytes;
offsets and padded sizes stay fixed. All other header/playlist/audio bytes must
match stock. `prepare_greeting.py` outputs `SJP00300.GID`, per-clip encoded
bytes and decoded preview WAVs, `fits.tsv` and `build-report.json` only if all
clips fit. The owner listened to the Penny render (2026-10-31) and approved it,
so build `7e007bfb…75af0c1` (`build-penny-v1/SJP00300.GID`) is pinned in
`write_gid.py:BUILDS` and `binaries/MANIFEST.md`. No synthetic fixture is an
English payload or gets pinned as one.

### 8.4 Writer, exact commands and rollback (owner runs applies)

**[confirmed layout/tool policy]** `write_gid.py` follows the skin writer's
preflight/snapshot/verify/receipt model, with a p1 FAT32 walker. It pins the MBR
p1 start (LBA 888833), FAT32 geometry, both copies of every traversed FAT entry,
and the public path `SPEECH/JP/GID/SJP00300.GID`. This image's file occupies 579
contiguous 64 KiB clusters, 196677–197255; file start is **LBA 26066817 = byte
13,346,210,304**, length **37,882,424**. A moved, resized, fragmented, cyclic,
out-of-range or mirrored-FAT-inconsistent chain is refused. No FAT/directory,
firmware, settings, skin or other file is edited.

**[confirmed writer policy]** The live full-file hash must be stock or a pinned
English build; the payload must likewise be pinned. Backup receipt, read-only
mode, full size and **recomputed full-backup SHA256** must match the existing
`backup_card.py` pin (`b0bb50ec…38c7540`). The backup must contain the stock GID
with the pinned allocation/hash. `BUILDS` holds exactly one English build, Penny
v1 (§8.3), pinned after the owner's listening review.
The writer cannot apply a guessed/unreviewed hash supplied on its command line.

**[confirmed write boundary]** The file's last sector contains 56 file bytes and
456 bytes outside the file. Preflight reads that sector, but the writer trims
identical leading/trailing sectors and writes a single aligned changed window
**wholly inside the file**. It refuses any window reaching beyond the GID's end;
it never writes that final partial sector. Snapshot and receipt identify the
actual window. Before opening for writes it checks device identity/layout and
the entire live GID again; afterwards it fsyncs, reopens and verifies both the
written window and full GID/non-file tail. A caught write/read-back/interrupt
failure restores the saved window, fsyncs and verifies the full original GID;
a changed device identity prevents writing a rollback to the wrong device.

**[confirmed commands; offline preflight passed]** Run them from a checkout of
this branch (or main after merge). The read-only offline preflight against the
analysis image returned `READ_ONLY_PREFLIGHT_PASSED`: live = stock GID
`6733c2b2…`, build `7e007bfb…`, write window at byte 13,346,302,464,
10,466,304 bytes (descriptor table through clip 819; unchanged bytes inside the
window are rewritten identically). Find `diskN` with `diskutil list` and unmount
the card's volumes with `diskutil unmountDisk diskN` first; macOS mounts p1
automatically.
`diskN` is the owner's whole removable card identifier, which must be replaced
with the actual device after checking the card is in the reader and unmounted.
Only the owner runs device commands or sudo; no agent has run either apply.
The original analysis image is never a writable target (`--image` rejects
`--apply`). Use the pinned full-card backup described in `docs/BACKUPS.md`.

```sh
# Read-only offline preflight (passed 2026-10-31):
python3 -I tools/language-speech/write_gid.py \
  --image ~/nissan/sdcard/nissan-sd-485-1972-00.img \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1/SJP00300.GID \
  --work-root ~/nissan/work

# OWNER: read-only live preflight. Require READ_ONLY_PREFLIGHT_PASSED.
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1/SJP00300.GID \
  --work-root ~/nissan/work
# OWNER ONLY: apply the same pinned build.
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1/SJP00300.GID \
  --work-root ~/nissan/work --apply

# OWNER: rollback preflight, using the pinned original public GID.
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/SJP00300.GID \
  --work-root ~/nissan/work
# OWNER ONLY: rollback (restores GID only; keeps current skin/settings/firmware).
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/SJP00300.GID \
  --work-root ~/nissan/work --apply
```

**[confirmed receipt policy]** Each owner apply creates a new
`~/nissan/work/language-speech/en-greeting/writes/<UTC>/` directory containing
`gid-before-write.bin` (read-only, verified before writing) and a fsynced
`write-report.json`: identity, backup/build/live hashes, exact offset/window
length, snapshot hash, sync/read-back/rollback result. This snapshot covers the
changed sector window, not a full card; the full backup remains required.

**[confirmed tests]** `test_write_gid.py` passes 25 tests, including partial-write,
read-back, whole-file verification, fsync and interrupt failures; snapshot
failure; full-backup hash tampering; device swap; rollback failure; unpinned/live/already-applied refusals;
stock rollback; welcome-only scope and overflow guards; final partial-sector
refusal; and read-only real-image FAT validation. `test_greeting.py` passes 12
request-boundary/credential-redaction/codec/fitting checks. The nine existing
parser/decoder tests also pass. Device-write paths are tested on ordinary
temporary files only. Run:

```sh
python3 -I tools/language-speech/test_speech.py
python3 -I tools/language-speech/test_greeting.py
python3 -I tools/language-speech/test_write_gid.py
```

### 8.5 Card write record (owner-run, 2026-10-31)

**[confirmed receipt; untested in the car]** The owner ran the read-only preflight and then `--apply` on `disk8` (Built In SDXC Reader, 16,206,790,656 B). Preflight: live = stock GID `6733c2b2…`, build `7e007bfb…`, backup `b0bb50ec…`. Apply: `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`, fsync completed, 10,466,304 B at byte 13,346,302,464. Rollback snapshot `gid-before-write.bin` sha256 `b35dc6ad…24db0` (verified), written payload window `1fdf8937…0592d`. Receipt: `~/nissan/work/language-speech/en-greeting/writes/20261031T075202.801762Z/`. The card was ejected afterwards. Next: hear it in the car (§3 explains when it greets).

### 8.6 Build v1.1: loudness-matched clips

**[confirmed build; untested in the car]** The v1 clips were 10–20 dB quieter than stock (review, decoded RMS median −31.2 dBFS against about −16 for stock). `prepare_greeting.py --rms-dbfs -16 --peak-dbfs -2` now normalises each trimmed clip before encoding. Louder audio costs SSC bits, so a clip that would overflow its slot steps down 1 dB at a time (up to 14 dB) until it fits.

Result for build `0a80b637…94ed4` (`build-penny-v1.1c/`): all 56 clips fit. Decoded RMS is −25.1 / −17.3 / −16.1 dBFS (min / median / max) and peak is at most −1.4 dBFS. 48 clips play at normal speed; September, second, third, fourth, sixth, seventh, tenth and twentieth use the existing 1.08–1.12 tempo step and sit at −17.7 to −25.1 dBFS. Local SSC round-trip SNR: minimum 20.1 dB, median 35.2 dB. The listening example is `welcome-example.wav` (`956d331b…`). Offline preflight against the analysis image: `READ_ONLY_PREFLIGHT_PASSED`. The card currently holds v1, which is pinned, so the live preflight should report `"live": "Penny v1…"`.

```sh
cd nz-leaf-discovery
diskutil unmountDisk diskN
# OWNER: read-only preflight, then the same command with --apply
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1.1c/SJP00300.GID \
  --work-root ~/nissan/work
# Rollback: --build .../build-penny-v1/SJP00300.GID (v1) or ~/nissan/work/language-speech/SJP00300.GID (stock)
```

### 8.7 Car result for v1 (owner report, 2026-10-31)

**[confirmed, owner report; no recording captured]** The English Penny v1 greeting plays in the car. It was soft, and audible once the volume was turned up. This confirms the §9 verdict: the firmware decodes our SSC streams, and the earlier silence was the repeat gate. The low level matches the 10–20 dB shortfall measured in §9.4, and v1.1 (§8.6) is the loudness-matched follow-up, not yet written to the card.

### 8.8 v1.1 card write (owner-run, 2026-10-31)

**[confirmed receipt; car listening pending]** The live preflight on `disk8` reported live = Penny v1 `7e007bfb…` and build v1.1 `0a80b637…`, then `READ_ONLY_PREFLIGHT_PASSED`. The owner's `--apply` returned `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`: fsync completed, 10,456,064 B at byte 13,346,302,464. Rollback snapshot (the v1 bytes) sha256 `cf7bbe90…3db71f` (verified); payload window `a889ae44…a050`. Receipt: `~/nissan/work/language-speech/en-greeting/writes/20261031T093827.139997Z/`. The card was ejected. Rollback targets are v1 (`build-penny-v1/`) and stock.

## 9. Why the English start-up greeting can be silent

**Scope.** Static review only. No new GID was built, no writer was changed, no
card/car write, no firmware execution/emulation, and no sudo. The inputs were the
corrected `Speech.exe` (§4), the G214 HMI modules, the decompiled
`NaviWelcomeCC.dll` and `STDDLL.dll`, the stock GID and the pinned Penny v1 build
(`7e007bfb…75af0c1`, §8.3). The owner's nav voice still works, so the p1 GID is
found, its directory is accepted and stock SSC streams still decode and play.

### 9.1 Verdict first

**Verdict: A — the repeat rule [likely].** No firmware check found in the GID
reader, descriptor path or SSC decoder rejects our streams. The greeting selector
is a hard once-per-JST-period gate, and the date is nested **inside** the
greeting-allowed branch, so one greeting-gate hit suppresses the whole start-up
sequence. The owner's write landed at **16:52:02 JST** on 2026-10-31, inside the
day greeting period (11:00–17:29:59 JST); a normal drive earlier that JST day is
enough to explain the silence, and the gate is independent of the GID write. At
that time the selector would have emitted phrase IDs `0xb0f` (clip 765, "Hello"),
`0xb1d` (clip 777, October), `0xb3e` (clip 810, thirty-first) and `0xb45` (clip
817, Saturday), all replaced by the Penny build; the safety phrase `0xb47`/`0xb48`
was optional.
The alternative **B is not supported**: there is no failing check to name (9.3).
**C** remains possible only if the unit had not been used earlier in the day (so
the gate was clear), or if the `Guide2WelcomeMessage` setting is not 2, or if the
much quieter English clips were inaudible. The car test in 9.7 separates these.

### 9.2 End-to-end request chain and where our clips can drop out

The chain is recorded-phrase playback, not TTS. Addresses are module VAs; the
welcome module is `NaviWelcomeCC.dll` (image base `0x428b0000`) and the speech
engine is the corrected `Speech.exe` (§4).

| # | Step | Address / evidence | What can drop out |
|---|---|---|---|
| 1 | Register the welcome speech mode | `0x428c4b1c` → `0x428c6d98(obj, 0x13, 0x86000010, 2)`; mode/msg/flags stored at `+0x20/+0xb/+0xc`; readiness byte returned into `+0xc4` | Speech engine never becomes ready |
| 2 | Trigger the welcome | system-state subevent `0x265` at `0x428b90e0` (trace `SS->WelcomeCC`, `0x428b18d8`) or speech-ready `wParam=0x13`, `lParam&2` at `0x428b9168` (traces `0x428b1980`, `0x428b1910`) | No trigger, or trigger before the one-shot/readiness flags |
| 3 | Decide the phrases | `0x428b8e0c`: readiness flags `DAT_428b9088[2]/[3]`, one-shot `*DAT_428b9088`; reads `Guide2WelcomeMessage` (must be `2`), `Guide2SafeDrivingMessage`; `OBJ_Time_readGMT` + `STD_Time_addBase(0x317040)`; greeting `0x428b8774`; date `0x428b8998`; weekday; safety `0x428b8aac` | Setting not 2; gate hit; time/read error; one-shot already used |
| 4 | Persist the decision | `0x428c512c` (greeting time), `0x428c5194` (date), `0x428c51fc` (safety), `0x428c50f0` (first slot); record writer `0x428c4f84` | Persistence failure is silent (no log in the setter path) |
| 5 | Build the request | `0x428b8680` (max 5 records); `0x428c7210` AddRecord: tag `0xf010200=2` (recorded), `0xf010201=phrase ID`; `0x428c6460` ExecRequest; logs at `0x428b12a8`/`0x428b1308` | AddRecord/ExecRequest error; request count >5 |
| 6 | Speech queue walk | Speech.exe `0x12c62c`-family loop: `0xf010008` record count, `0xf070100+i` records, `0xf010200==2`, `0xf010201` phrase ID; `0x134c9c`→`0x134b94` phrase token count; `0x134cb0` per token | Empty phrase; out-of-range token; file-read error |
| 7 | GID phrase/playlist read | `0x134b94`: member +`0x40` boundary table, adjacent entries, `(end-start)/4` tokens; empty slot when equal; `0x1348d0` validates header extents, alignment and descriptor/audio regions; no hash | Corrupt boundary/descriptor/extent (not our build; same-size, same offsets) |
| 8 | Descriptor lookup | `0x134cb0`: token bit31 = silence `(ms)`; else descriptor at member base + token: `+0` format, `+4` audio offset, `+8` padded size, `+0xc` **real size**; codec byte `+1`: 1→PCM kind 3, 2→kind 1, 4→SSC kind 5; rate byte `+3`: 1→11 kHz, 2→22.05 kHz; reads `+0xc` bytes at `+4` | Wrong format/rate (ours is stock `02040102`); short file read logs `0x1f1`; padding is not used |
| 9 | SSC decode | `0x124b04` (vtable table at `0x14300`/`0x14328`) → `0x1249f8` → `SSC_DecodeInit 0x1cfbec`, `SSC_Decode 0x1d1494`, block parser `0x1d02f8`, dequant `0x1cf6b8`, transform `0x1d0bfc`; bit reader `0x1cf2d8`; Huffman `0x1cf83c` | Malformed mode/code/escape/scale; truncation; end marker |
| 10 | PCM submit | `0x1223f0(stream, pcm, 128)` per block; `0x122590` flush; same output path as nav | Queue/resampler failure; level too low to hear |

The nav voice working exercises steps 6–10 with stock SSC; the owner report proves
the file, directory and audio out are alive. Steps 3–5 are the welcome-only gates.

### 9.3 Question 1: decoder checks vs our encoder and decoder

The firmware's checks are now mapped one by one. Our build passes every one.

| Check | Firmware evidence | Our data |
|---|---|---|
| Real vs padded size | `0x134cb0` reads descriptor `+0xc` (real) for the file read and buffer size; `+8` (padded) is not used for playback | [confirmed] build keeps stock `+8` and sets `+0xc = len(encoded) ≤ padded` (§8.3) |
| Min/max clip length | No per-clip minimum/maximum in `0x134cb0`; `0x1cfbec` only requires `param_3 >= 1` (we pass `0x80`); `0x1d02f8` has no block/sample count field | [confirmed] ours 54–195 blocks; stock 9–17,182 |
| End marker / zero block | `0x1d02f8`: a `7` mode at band 0 returns `0xffffffff` (end), at band 1 sets `*param_4=1` (zero block), at band ≥2 returns `0xffffffff`; the caller `0x1249f8` stops on any nonzero | [confirmed] every stream ends with the 3-bit `111` marker; no `7` in the 15-mode list; no zero blocks used |
| Header bits / modes | 15 × 3-bit modes, one per band; modes 0–6 only | [confirmed] mode histogram 0–6; no 7 |
| Bit allocation / quantiser | Radix/bias per mode; sign bits for modes 2/4/5/6; escape only in mode 6 when |value| = 16; 5-bit initial scale + 14 × 3-bit deltas (delta −5…+2) | [confirmed] escapes present, widths 4–6 only; scales 0–6; deltas inside range |
| Huffman code validity | `0x1cf83c`: code length < 20, invalid/absent code returns `0xffffffff` | [confirmed] every symbol is emitted from the firmware's own table |
| First-block state | `0x1cfbec` zeroes the 128-sample overlap and state; first block may be normal or zero block | [confirmed] some English clips start with one all-zero **mode-0** block (6 zero bytes); legal |
| Checksums | None in the GID header/descriptor/audio path (`0x1348d0`, `0x134b94`, `0x134cb0`) | [confirmed] nothing to update |
| Error behaviour | `0x1249f8` returns the samples decoded so far and stops; `0x124b04` returns false if that count is 0; no retry loop; `0x122898` logs stream-state codes `0x100/0x107/0x112` if a log object exists | [confirmed static] a bad clip is silent and is not retried; a queue/submit failure (`0x122b70` returns 0) aborts the request loop, a decoder error does not |

**Where our Python port is more lenient than the firmware.** The comparison was
done for completeness; none of these differences can hide a firmware rejection of
our streams. The encoder is `tools/language-speech/ssc_encode.py`, called by
`prepare_greeting.py`; its policy choices (mode thresholds, scales 0–31, coarse
−2, no zero-block markers) all stay inside the decoder's accepted ranges.

- `ssc_decode.py` raises on truncation; the firmware returns `0xfffffff7` and
  stops. Stricter, not more lenient.
- It requires at most 7 trailing bits after the marker; the firmware never reads
  the padding. Stricter.
- It rejects a vector value left over after dividing by the radix; the firmware
  silently discards the remainder. Our encoder never emits such a symbol.
- It clamps scales to signed −128…127 and shifts only 0…31; the firmware uses
  the scale as an **unsigned byte** and ARM shift semantics. Our scales are 0–6,
  so the two agree.
- It treats a zero block by clamping the overlap and clearing it (`0x1cfc88`
  equivalent). Ours never uses zero blocks.
- It does not implement stereo or `SSC_DecodeSkip`; both are unused for mono GID
  playback.

**Conclusion for question 1:** no exact firmware check fails on our data. The
candidate checks are real/padded size (pass), length/counts (pass), end marker
(pass), mode/quantiser ranges (pass), first-block state (pass), checksums (none).

### 9.4 Question 2: statistical comparison with stock SSC

Every stock SSC clip (2,053) and all 56 English clips were parsed with the same
firmware-derived parser. Values are per clip over the descriptor's **real size**.

| Metric | Stock (n=2,053) | English build (n=56) | Flag |
|---|---|---|---|
| bytes per 128-sample block | median 62.46; p10–p90 54.44–68.37; max 84.37 | median 48.35; p10–p90 42.33–54.36; max 58.35 | [confirmed] ours is ~23 % lower bitrate |
| bytes per sample (real/duration) | median 0.488; p10–p90 0.425–0.534 | median 0.378; p10–p90 0.331–0.425 | [confirmed] valid, lower |
| trailing bits after end marker | 0–7 (median 4); no whole trailing byte | 0–7 (median 3); no whole trailing byte | [confirmed] same bound; our decoder's ≤7 rule matches stock |
| block bits | min 6 (zero block), median 538, max 1,035 | min 92 (all-zero mode-0 block), median 404, max 869 | [confirmed] ours never uses a 6-bit zero block |
| zero-block markers (mode 7 at band 1) | 33,294 in 1,591 clips | 0 | [confirmed] stock uses them for silence; ours encodes silence as mode-0 blocks (legal) |
| escape codes | 4,911,737 in 1,971 clips; widths 4–10 | 21,557 in all 56; widths 4–6 | [confirmed] subset, legal |
| initial/accumulated scale range | 0–7 | 0–6 | [confirmed] inside the 5-bit/±delta range |
| leading zero bytes | max 2; only clips 244 (2), 326 (1), 885 (1), 1187 (2) | up to 6; 764/771/773/774/779/788/797/804/810/815 = 6, 766/777/792/799/803/805/807/812 = 5 | **stock never does this**; benign (one all-zero block, ~20 ms of retained trim context) |
| real size / padded size | each stock clip fits its padded extent | all 56 fit; spare 35–14,442 bytes | [confirmed] no overflow |

**The two stock-never features are the 6-byte zero prefix and the absence of
zero-block markers.** Neither is rejected by `0x1d02f8`: an all-zero 15-mode list
is a normal mode-0 block (45 mode bits + 47 scale bits = 92 bits), and the zeros
are decoded by the normal `0x1cf6b8`/`0x1d0bfc` path. Stock's max 6-bit block is
its zero-block shortcut, not a requirement.

**Level check (not a codec check).** The decoded English previews are much
quieter than the stock clips: clip 764 stock RMS −15.8 dBFS / peak −2.8 dBFS vs
English RMS −30.4 dBFS / peak −17.8 dBFS; across the 56, English RMS is −37.1 to
−26.0 dBFS and peak −20.4 to −9.4 dBFS, while stock RMS is −18.8 to −13.3 dBFS
and peak −5.5 to −1.9 dBFS. That is roughly **10–20 dB quieter (up to ~24 dB)**,
because the render was not loudness-normalised.
It is audible at normal volume but can read as "silent" at low volume; a future
build should match the stock level (out of scope here; no build was made).

### 9.5 Question 3: the welcome repeat gate and where "last greeted" lives

**Selection logic.** `0x428b8774(current, persisted)` builds the current
time-of-day term and returns:

| Return | Meaning | Caller action |
|---|---|---|
| 0/1/2/3 | greeting allowed: morning/day/evening/New Year | append `0xb0e+ret`, save greeting time |
| 4 | persisted greeting is **after** the current term (future/clock moved back) | clear greeting+date, no request |
| 5 | persisted greeting is **inside** the current term (already greeted) | no request, no clear |
| 6 | invalid/read error | no request, no clear |

The term boundaries are built in `0x428b8774`: 05:00–10:59:59 (morning),
11:00–17:29:59 (day), 17:30–04:59:59 (evening; dates adjusted by
`STD_TimeDate_addDays`), plus the Jan 1 special. `STD_Time_compare` /
`STD_Time_containTerm` (STDDLL) confirm the code mapping: `0x3f3` = before the
term, `0x3f4` = after the term, `0x3ea` = inside the term. [confirmed static]

**The date is nested inside the greeting-allowed branch** (`0x428b8e0c`,
lines with `if (uVar2 < 4)`). Therefore a greeting-gate hit (return 5) means the
date is never even selected. A silent start-up is exactly what a single
greeting-gate hit produces; a date-only gate cannot cause total silence. The date
gate uses the same mapping in `0x428b8998`: before today → weekday (allowed),
inside today → return 8 (skip, no clear), after today → return 7 (clear both).

**Persistence.** The gate state is not in the GID, the skin, a file or the
registry. It is a 0x40-byte **OSM SRAM record**:

| Record offset | Content |
|---|---|
| `+0x00` | u32 header = `1` |
| `+0x04` | first 8-byte `STD_Time` struct (safe-driving/other; `FUN_428c4f08`/`0x428c50f0`) |
| `+0x0c` | greeting struct: last greeting time (`FUN_428c4f24` reads, `0x428c512c` writes; base +8) |
| `+0x14` | date struct: last date-announcement time (`FUN_428c4f44`/`0x428c5194`; base +0x10) |
| `+0x1c` | safety struct: last safe-driving time (`FUN_428c4f64`/`0x428c51fc`; base +0x18) |
| `+0x3e` | u16 magic `0xa356` |

The record is filled by `FUN_428c4f84` (copy base 0x20 bytes to buffer+4, set
header/magic, then `OSM_SramSet(0x4e)`), read at boot by `FUN_428c4fdc`
(`OSM_SramGet(0x4e, 0x40, &ptr, &size)`, `OSM_SramCheck(0x4e, &status)`, header
and magic check, copy back). In OSMDLL, IDs below `0xb6` use
`CApi_GetSramVirtualAddress` / `CApi_CommitSram`; 0x4e = 78 is in that range.
[confirmed static for the API and record format; the physical backing is the
same open question as [#6](https://github.com/prasys/nz-leaf-discovery/issues/6) — internal-NAND SRAM vs the SD VSRAM backup.]

**What `STD_Time_initPrm` writes.** [confirmed] It zeroes the 8-byte struct
(year/month/day/hour/minute/second); month 0 is the "never greeted" sentinel.
`FUN_428b8774` returns the greeting when the persisted month is 0, and
`FUN_428b8998` returns the weekday when the persisted month is 0. So a cleared
record makes the **next** start greet. The module clears the record only when the
record is missing/invalid (`FUN_428c4fdc`) or when the stored time is *after* the
current term (`FUN_428c5158`/`0x428c51c0`, return 4); a normal "already greeted"
hit (return 5) does **not** clear it.

**Can this card image tell us the last-greeted time?** Not for this card.
[confirmed search] The SD VSRAM band (sectors 790528–818431, including the
sys/nav/bt `SRST` copies) and a full 16 GB image scan were searched for a
0x40-byte record with header 1 and magic `0xa356`; the only two plausible OSM
records are in the bt area (settings offsets `0x3e26a8`/`0x4716a8`), and their
payload is BT timestamps in a different layout, not the four welcome structs.
Three other byte-pattern matches fall inside the p1 GID/TTS data and are
coincidental. The SD VSRAM copy is also stale (nav last-write 2026-10-23 06:31:28),
while the unit's primary SRAM is internal NAND. So the current gate state cannot
be read from `~/nissan/sdcard/nissan-sd-485-1972-00.img`; a fresh image might
capture the SD backup, but the primary is not on the card. Do not dump/clear SRAM
to find out; the car test is cheaper and safer.

**Exact NZ times.** The welcome module ignores the displayed-clock offset and uses
GMT + the fixed JST base (`0x428b8e0c`). In late October NZ is NZDT (UTC+13),
JST is UTC+9, so **NZ wall time = JST + 4 h**:

| JST event | NZDT (UTC+13) | What should play |
|---|---|---|
| 2026-10-31 16:52:02 (write) | 2026-10-31 20:52:02 | day slot (11:00–17:29:59 JST) |
| 17:30:00 | **21:30:00, 31 Oct** | evening greeting (`766`, "Good evening"); date still gated if already announced today |
| 00:00:00, 1 Nov | **05:00:00, 1 Nov** | new JST day (date gate clear), but still the evening greeting period; the date is emitted only if the evening greeting is allowed |
| 05:00:00, 1 Nov | **09:00:00, 1 Nov** | morning greeting (`764`) + date: new day and a fresh period, the cleanest full-sequence test |

If the unit is on NZST (UTC+12) instead, subtract 1 h (20:30 / 04:00 / 08:00).
The next greeting after a day-slot hit is therefore **21:30 NZDT**, not the next
ignition in the same slot; if the evening period was already used, the next is
**09:00 NZDT** (05:00 JST morning).

### 9.6 Question 4: the other gates

- **`Guide2WelcomeMessage` = 2** [confirmed static]: `0x428b8e0c` reads it into
  `local_28`; the entire greeting/date block runs only when it is `2`. If it is
  not 2 there is no request and no log. The owner can check the setting in the
  unit's menu; the GID write did not change it.
- **`Guide2SafeDrivingMessage` = 2** [confirmed static]: only adds phrases
  `0xb47`/`0xb48`; it cannot silence the greeting.
- **Speech mode `0x13` readiness** [confirmed static]: registered by
  `0x428c4b1c` → `0x428c6d98(..., 0x13, 0x86000010, 2)`; the readiness
  notification is `0x428b9168` (`wParam=0x13`, `lParam&2`). Nav working proves
  the speech engine and GID are ready; the welcome callback is a separate mode.
- **One-shot guard** [confirmed static]: `*DAT_428b9088` is set before the
  setting/time reads in `0x428b8e0c`; a failed first event is not retried by the
  second (system-state vs speech-ready) event in the same boot.
- **Retry/log on failure** [confirmed static]: AddRecord/ExecRequest failures log
  (`0x428b1308`, `0x428b12a8`). A decoder error is not retried and has no
  welcome-specific log; the stream state machine may log `0x100/0x107/0x112` via
  `0x122898` if a log object is present. A queue/submit failure (`0x122b70`
  returns 0) aborts the request loop; a decoder error does not.
- **Time/date validity** [confirmed static]: if `OBJ_Time_readGMT` or
  `STD_Time_addBase` fails, `0x428b8e0c` logs and returns without a request. The
  working clock makes this unlikely, but the welcome time is JST, not the
  displayed NZ time.
- **Request size** [confirmed static]: `0x428b8680` refuses more than 5 records;
  the selector emits at most greeting + month + day + weekday + safety = 5.

### 9.7 Cheapest car test and what each result means

**Test A vs B (no writes, one ignition cycle):** at or after **21:30 NZDT on
2026-10-31** (17:30 JST), start the car once at normal volume and listen for
**"Good evening."** This is a fresh JST greeting period, so a persisted day-slot
greeting is *before* the new term and the gate must allow it. The date may still
be skipped; that is expected and does not affect the test.

- **Greeting plays** → the GID is read, the English SSC stream decodes and the
  audio path works; the earlier silence was the repeat rule. **Verdict A.**
- **Still silent** → the repeat rule is not the cause. Then the remaining
  candidates are B (decoder/file) or C (setting/level). Check
  `Guide2WelcomeMessage` = 2 and the volume; if both are normal, B is the
  remaining suspect, but no exact check in 9.3 explains it, so treat it as C
  until a controlled clip test exists.

If 21:30 NZDT has already passed and the evening period was used, use the next
clean slot: **09:00 NZDT on 2026-11-01** (05:00 JST, new JST day + morning
period). Expect "Good morning." plus the date. On NZST the times are 20:30 and
08:00. Do not rebuild the GID or rewrite the card for this test.

**If a future build is made** (not this issue): loudness-normalise the English
clips to the stock RMS/peak, and consider trimming the retained leading silence
so the first block is not an all-zero block. Neither is required for decoder
acceptance.
## 10. EV voice alerts

### 10.1 Scope and trace

**[confirmed]** This follow-up re-records 41 public GID clips in the Penny voice
(`TRrl1hXRI8ISfQPDN0Bf`): 1297–1302 (battery/range), 1416/1417/1573/1594/
1721/1722/1723/1740/1743/1744 (charging), 1537/1709/1745/1746/1840 (EV energy)
and 428–442/444/548/1320/1322/1345 (vehicle/system alerts). They are all recorded
GID prompts. **No TTS request path was found in `EvNoticeCC`, `NaviEvCC` or
`InfoBarCC`**; those modules use the recorded speech-guide request classes.
The only dynamic TTS source remains `TJP04000.HDR +0x61` (Japanese Nbk, §7),
and no EV text producer for it was traced. Re-recording therefore cannot change
a TTS-sourced alert, because none of the selected alerts was shown to be TTS.

**[confirmed static]** Phrase IDs and playlists come from the pinned GID
inventory. Module addresses below are static selectors, not proof that a prompt
plays in this car. The EV notice path is:

| Step | Function / evidence |
|---|---|
| Notice dispatch | [confirmed] `InfoBarCC!FUN_433e8e84` @ `0x433e8e84` dispatches message `0x8709` to `FUN_433eb5a4` @ `0x433eb5a4` |
| Type selection | [confirmed] `FUN_433eb5a4` maps notice types 1/4, 2/5 and 3/6 to `FUN_433eb060` @ `0x433eb060` |
| Phrase selection | [confirmed] `FUN_433eb060` sets phrase `0xfde`/`0xfe8` (types 1/4), `0xfdc`/`0xfe6` (types 2/5) or `0xfdf`/`0xfe9` (types 3/6); the full form adds the `0x…dc/…de/…df` detail suffix, the short form uses `0x…e6/…e8/…e9` |
| EV manager | [confirmed] `NaviEvCC!FUN_42508fbc` @ `0x42508fbc` stores `0xfdd`; `FUN_42508fd8` @ `0x42508fd8` stores `0xfe9`. Both call `FUN_42508a20` @ `0x42508a20`, which passes the ID to `FUN_4250d244` and submits through `FUN_4250c494` |
| Notice state machine | [confirmed] `ScreenStateCC!FUN_418fd0a4` @ `0x418fd0a4` handles notice `0xfdd` by drawing dialog `0x22f`, and also loads `0xfdc`, `0xfde`, `0xfdf`, `0xfe6`, `0xfe8` and `0xfe9` |
| Door/vehicle IDs | [confirmed] `ScreenStateCC` instruction blocks load `0x035d`–`0x036f`; `Vehicle.exe!FUN_0003023c` @ `0x0003023c` handles event `0x35d` at `0x000305b8` and calls `FUN_00039d6c`, `FUN_000393f0`, `FUN_00033dbc`, `FUN_0003a534` and `FUN_00038758` |

| Clip(s) | Phrase / playlist order | Module selector | Confidence |
|---|---|---|---|
| 1297 | `0xfdc` = 1297 + 1301; `0xfe6` = 1297 | `InfoBarCC!0x433eb060` types 2/5 | [confirmed static] |
| 1298 + 1302 | `0xfdd` = 1298 + 1302 | `NaviEvCC!0x42508fbc`; `ScreenStateCC!0x418fd0a4` | [confirmed static] |
| 1299 | `0xfde` = 1299 + 1301; `0xfe8` = 1299 | `InfoBarCC!0x433eb060` types 1/4 | [confirmed static] |
| 1300 | `0xfdf` = 1300 + 1301; `0xfe9` = 1300 | `InfoBarCC!0x433eb060` types 3/6; `NaviEvCC!0x42508fd8` | [confirmed static] |
| 1301 | suffix of `0xfdc`/`0xfde`/`0xfdf` | same playlists | [confirmed] |
| 1416 | `0x178c` = 1416 | requester not traced; charging-search UI | [confirmed playlist; guess module] |
| 1417 | `0x178d` = 1417 | requester not traced; charging-search UI | [confirmed playlist; guess module] |
| 1573 | `0x1e5a`, `0x1e5d`, `0x2d66`, `0x2d69`, `0x2d8a`, `0x2d8d`, `0x34c4` | requester not traced; charging-search UI | [confirmed playlists; guess module] |
| 1594 | 26 playlists, e.g. `0x24cb`, `0x254f`, `0x2573`, `0x2597`, `0x2d8a`, `0x34e2` | requester not traced; charging-search UI | [confirmed playlists; guess module] |
| 1721 | `0x1e23` = 1721; `0x1e26` = 1721 | requester not traced; charging-search UI | [confirmed playlists; guess module] |
| 1722 + 1723 | `0x1e29` and `0x1e2c` = 1722 + silence 400 ms + 1723; `0x25af`/`0x25b2` = 1722 + 1744; `0x3080`/`0x3332` = 1722 | same | [confirmed playlists; guess module] |
| 1740 | `0x24ad`, `0x24b0`, `0x24b9`, `0x24bc`, `0x24cb`, `0x24ce`, `0x252b`, `0x252e`, `0x307d`, `0x332f` | same | [confirmed playlists; guess module] |
| 1743 | `0x25a9`, `0x25ac`, `0x25b5`, `0x25b8`, `0x25bb`, `0x25be` | same | [confirmed playlists; guess module] |
| 1744 | `0x25af`/`0x25b2` = 1722 + 1744; `0x2eca` = 1427 + 1744; `0x2fab` = 1744 | same | [confirmed playlists; guess module] |
| 1537 | `0x1c97` = 1537; `0x1c9a` = 1537 | requester not traced; EV route UI | [confirmed playlists; guess module] |
| 1709 | `0x1e8f` = 1709; `0x1e92` = 1709 | requester not traced; energy monitor UI | [confirmed playlists; guess module] |
| 1745 | `0x25c1` = 1745; `0x25c4` = 1745 | requester not traced; energy-economy UI | [confirmed playlists; guess module] |
| 1746 | `0x25c7` = 1746; `0x25ca` = 1746 | requester not traced; power-consumption-meter UI | [confirmed playlists; guess module] |
| 1840 | `0x31ee` = 1840; `0x33d4` = 1840 | requester not traced; energy monitor UI | [confirmed playlists; guess module] |
| 428–437 | `0x035c`–`0x0365`, one clip each | `ScreenStateCC` door-ID block; `Vehicle.exe!0x0003023c` event `0x35d` | [confirmed playlists; likely module] |
| 438 + 442 | `0x0366` = 438 + 442 | same | [confirmed] |
| 439 | `0x0367` = 439 | same | [confirmed] |
| 440 + 442 | `0x0368` = 440 + 442 | same | [confirmed] |
| 441 | `0x0369` = 441 | same | [confirmed] |
| 444 | `0x0370` = 444; clip 443 stays original Japanese | requester not traced; vehicle fault notice | [confirmed playlist; guess module] |
| 548 | `0x036c` = 548 | `ScreenStateCC` vehicle-ID block | [confirmed playlist; likely module] |
| 1320 | `0x1011` = tone 1308 + 1320 | `ScreenStateCC` vehicle-ID block | [confirmed playlist; likely module] |
| 1322 | `0x1013` = tone 1308 + 1322 | `ScreenStateCC` vehicle-ID block | [confirmed playlist; likely module] |
| 1345 | `0x103f` = 1345 | requester not traced; DSRC/vehicle fault | [confirmed playlist; guess module] |

**[confirmed]** Some in-scope clips sit in playlists with out-of-scope navigation
or voice-recognition fragments (1426, 1427, 1462, 1463, 1566, 1567, 1575, 1590,
1597, 1598, 1599, 1742). Those fragments are deliberately not translated here,
so those mixed playlists will remain partly Japanese. Clip 1308 is a tone and
has no spoken text.

### 10.2 Locked wording (owner review before rendering)

**[likely wording; confirmed mapping]** `translations/voice-prompt-overrides.tsv`
now locks the English below; every note carries the source phrase ID and the
selector address where traced. `voice-prompts.tsv` is regenerated from those
overrides.

| Clip | Locked English |
|---|---|
| 1297 | Battery charge is low. |
| 1298 | Battery charge is very low. |
| 1299 | Power output is limited. |
| 1300 | You may not reach your destination. |
| 1301 | You can check the details. |
| 1302 | Search for nearby charging stations? |
| 1416 / 1740 | Find charging stations. |
| 1417 | Update charging stations. |
| 1573 | Charging stations. |
| 1594 | Rapid charging stations. |
| 1721 / 1743 | Updating charging stations. |
| 1722 | Update charging stations. |
| 1723 | Search around your current location or destination? |
| 1744 | Updating charging stations near your current location or a waypoint. |
| 1537 | Finding an eco route. |
| 1709 | Displaying the energy monitor. |
| 1745 | Displaying energy economy information. |
| 1746 | Displaying the power consumption meter. |
| 1840 | Energy monitor. |
| 428 / 429 / 430 / 431 | Driver's side and / Passenger's side and / Rear right side and / Rear left side and |
| 432 | All doors and |
| 433 / 434 / 435 / 436 | Driver's side / Passenger's side / Rear right side / Rear left side |
| 437 | Door and |
| 438 | Door |
| 439 | The tailgate is open. |
| 440 | The boot |
| 441 | All doors are open. |
| 442 | is open. |
| 444 | A fault has been detected. |
| 548 | The parking brake is still on. |
| 1320 | Please check the parking brake. |
| 1322 | The gear is in reverse. |
| 1345 | A fault has been detected in the DSRC unit. |

**[likely]** With the fixed clip order these join as, for example,
“Battery charge is low. You can check the details.”,
“Battery charge is very low. Search for nearby charging stations?”,
“A fault has been detected.”, and
“Driver's side Door is open.” Door fragments are deliberately short and use
“side” before the shared “Door” + “is open.” clips. Clip 438's slot is only
5,500 bytes (0.125 s PCM), so “Door is” had to be split; this keeps the
fragment inside the stock allocation. Clip 443 is out of scope and untraced;
it keeps its original Japanese audio and descriptor, so phrase `0x0370` now
plays Japanese “`「いてしに」`” followed by the English fault sentence.

### 10.3 Render, fit and build v2 on v1.1

**[confirmed local build; hardware-untested]** The 41 locked clips were rendered
with Penny (`TRrl1hXRI8ISfQPDN0Bf`) into
`~/nissan/work/language-speech/en-ev/render-penny-v1/`, then fitted with
`prepare_greeting.py --clip-set ev`, using the pinned v1.1 GID
`0a80b637…94ed4` as the base and `--rms-dbfs -16 --peak-dbfs -2`.

Result: all **41 clips FIT** at speed 1.00, every one SSC (`02040102`), with no
PCM clip. Clips 438/440/442 were re-rendered once after the “Door is” split, and
1722/1745/1746 after the owner wording review; 443 was dropped. Local
round-trip SNR is 20.657 dB minimum and 35.075 dB median.
Spare bytes are 4 minimum (clip 438) to 32,907 maximum. Decoded level is
−24.11 / −18.45 / −16.09 dBFS RMS (min / median / max) and peak is at most
−1.87 dBFS. The per-clip table, including the stock clip's level for
comparison, is `translations/ev-slot-fits.tsv`.

The same-size v2 build is 37,882,424 bytes, SHA256
`4635b41235237f13492154b40fba35ec3cd9dc297b4752bd9a9dfe9a57c7b090`,
identical across two fresh runs. It is `~/nissan/work/language-speech/en-ev/
build-penny-v2d/SJP00300.GID`; the greeting region is byte-identical to v1.1.
The listening example `ev-example.wav` uses the real tokens for phrases
`0xfdd`, `0xfdc`, `0x0366` and `0x0367`, SHA256
`2ccd5bdfa7c84ac54561a4bc1351a64659c212187fc48a06a072b7de662bf0af`.

**[confirmed tool policy]** `greeting.py` now exposes two clip sets:
`greeting` (764–819, stock base) and `ev` (the 41 clips above, v1.1 base).
`eleven_greeting.py`, `prepare_greeting.py` and `gid_patch.py` take that set
instead of forking. `gid_patch.py` allows only the union of the greeting and EV
clip descriptors/audio; an EV build must start from v1.1, never v1.0 or stock.
`write_gid.py` pins v2 and accepts a live baseline of stock, v1 or v1.1; rollback
targets are v1.1, v1 and stock.

**[confirmed offline preflight]** Against the read-only analysis image
(`~/nissan/sdcard/nissan-sd-485-1972-00.img`) the preflight returned
`READ_ONLY_PREFLIGHT_PASSED`: live = stock GID `6733c2b2…`, build
`4635b412…b090`, write window at byte 13,346,297,344, 28,593,152 bytes. The
image is stock, so the owner's live card should instead report v1.1 or v1; both
are pinned. No card or device was written by this session.

### 10.4 Loudness reference

**[confirmed]** The stock public clips for this set have a decoded RMS median of
about −16 dBFS (per-clip values are in `translations/ev-slot-fits.tsv`). Penny v1
was 10–20 dB quieter, which is why the car greeting was soft. The v2 EV
render uses `--rms-dbfs -16 --peak-dbfs -2`; the fitter normalises each trimmed
clip before SSC encoding and steps a clip down 1 dB at a time only when the
louder audio would overflow its existing slot. That is why the final minimum
RMS is −24.11 dBFS for a few slot-constrained long prompts while the median is
−18.45 dBFS. This is a local encode/self-decode and listening result, not a car
measurement.

### 10.5 Owner preflight, apply and rollback commands

Run these from a checkout of this branch. Unmount the card's volumes first
(`diskutil unmountDisk diskN`; macOS mounts p1 automatically). `diskN` is the
owner's whole removable card, checked in the reader. Only the owner runs device
commands or sudo; no agent has run `--apply`.

```sh
# Read-only offline preflight (passed 2026-10-31 against the analysis image):
python3 -I tools/language-speech/write_gid.py \
  --image ~/nissan/sdcard/nissan-sd-485-1972-00.img \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-ev/build-penny-v2d/SJP00300.GID \
  --work-root ~/nissan/work

# OWNER: read-only live preflight. Require READ_ONLY_PREFLIGHT_PASSED and
# "live": "Penny v1.1…" (v1 or stock is also accepted).
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-ev/build-penny-v2d/SJP00300.GID \
  --work-root ~/nissan/work

# OWNER ONLY: apply the pinned v2 build.
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-ev/build-penny-v2d/SJP00300.GID \
  --work-root ~/nissan/work --apply

# OWNER: rollback preflight to v1.1, then v1, then stock (choose one).
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1.1c/SJP00300.GID \
  --work-root ~/nissan/work
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1/SJP00300.GID \
  --work-root ~/nissan/work
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/SJP00300.GID \
  --work-root ~/nissan/work

# OWNER ONLY: apply the chosen rollback (same --build path as its preflight).
# v1.1:
sudo python3 -I tools/language-speech/write_gid.py --device diskN \
  --backup ~/nissan/work/nz-clock/backups/20261024T073738Z/card-before-patch.img \
  --build ~/nissan/work/language-speech/en-greeting/build-penny-v1.1c/SJP00300.GID \
  --work-root ~/nissan/work --apply
# v1: replace the --build path with
#   ~/nissan/work/language-speech/en-greeting/build-penny-v1/SJP00300.GID
# stock: replace it with
#   ~/nissan/work/language-speech/SJP00300.GID
```

**[confirmed receipt policy]** Each apply still writes only the changed sector
window, saves `gid-before-write.bin`, fsyncs, reads back and verifies the full
GID. v2 apply receipts go under
`~/nissan/work/language-speech/en-ev/writes/<UTC>/`; greeting rollback receipts
use `~/nissan/work/language-speech/en-greeting/writes/<UTC>/`. The full-card
backup remains required. The final partial sector outside the GID file is never
written.

### 10.6 v2 card write (owner-run, 2026-10-31)

**[confirmed receipt; car listening pending]** The live preflight on `disk8` reported live = Penny v1.1 `0a80b637…` and build v2 `4635b412…`, then `READ_ONLY_PREFLIGHT_PASSED`. The owner's `--apply` returned `WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED`: fsync completed, 28,593,152 B at byte 13,346,297,344. Rollback snapshot (the v1.1 bytes) sha256 `1642c2ed…881e08` (verified); payload window `1a1d541d…eda8d`. Receipt: `~/nissan/work/language-speech/en-ev/writes/20261031T105615.464100Z/`. The card was ejected. Rollback targets are v1.1, v1 and stock (§10.5).

## 11. Tools for other owners

The step-by-step owner guide is [`docs/guides/english-voice.md`](../guides/english-voice.md). It needs no hashes from our card.

- **[confirmed]** `clip_pack.py build` rebuilds our pinned builds byte for byte from per-clip files: the stock GID `6733c2b2…` plus the 56 greeting `.bin` files from `build-penny-v1.1c/` gives `0a80b637…`, and that plus the 41 EV files from `build-penny-v2e/` gives `4635b412…` (2026-11-01). The packs (`clip_pack.py export`; 2.3 MB and 3.6 MB) therefore need no TTS account, ffmpeg or `Speech.exe`.
- **[confirmed]** Bring your own TTS: 56 macOS `say` clips imported with `import_wavs.py` fit only at `say -r 220`. At the default rate, clips 784/785/799 (fifth, sixth, twentieth) overflow and the builder refuses. At `-r 220` all 56 fit (`cc9181ae…`, unpinned test build, never written).
- **[confirmed]** `mtcp.py --card-image <img> --no-reference` followed by `extract_speech.py g214-rom.bin` reproduces `Speech.exe` `5a435800…` from the card image alone. `clip_pack.py extract-gid` finds the GID through the image's FAT32 (offset 13,346,210,304, 37,882,424 B) and gives the stock hash.
- **[confirmed offline]** `write_gid.py --pins` (FAT-discovered geometry, the owner's backup hash and build pins) passes the read-only image preflight with the same file offset as the pinned mode, and refuses a build that isn't in the pins.
- **[guess]** Other 066 units carry the same stock GID. Nobody else's card has been checked yet; the tools stop if the hash differs.
