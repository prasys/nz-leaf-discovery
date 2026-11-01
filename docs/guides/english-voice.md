# English voice for your own LEAF Clarion unit

This guide puts English voice prompts on the nav unit of a JDM Nissan LEAF: the
start-up greeting (good morning, the date, "Drive safely.") and 41 EV alerts
(low battery, charging stations, open doors, parking brake, the energy monitor). You can use our ready-made NZ
English voice, choose your own wording and voice, or bring audio from any
text-to-speech engine or your own microphone.

The technical background is in [findings 14](../findings/14-voice-prompts.md).

## What you are changing

The unit's recorded prompts live in one file on the SD card,
`SPEECH/JP/GID/SJP00300.GID` (2,071 clips). The tools replace only the 56
greeting clips (764–819) and the 41 EV alert clips, **in place and at the same
size**. Every other byte of the file and of the card stays as it was. Each new
clip has to fit the space the original Japanese clip used, so very long wording
won't fit.

## Before you start

1. **The right unit.** This was built on a 30 kWh JDM LEAF with the Clarion
   nav unit on firmware 066 (`G314JLNI.066` / `G214JLNI.066`). Other firmware
   may have a different GID; the tools check for that and stop.
2. **A computer with an SD card reader.** The writer is tested on macOS. The
   build steps are plain Python and also run on Linux.
3. **Python 3** (3.10 or newer). No extra Python packages are needed.
4. **ffmpeg** for paths B and C (`brew install ffmpeg`). It converts imported
   audio, and the builder uses it to speed up a clip that doesn't quite fit.
   Path A doesn't need it.
5. **A spare SD card** big enough for a full backup image is a good idea for
   a clone test, though not required.
6. A working folder. Everything the tools make (images, audio, builds,
   receipts) goes under `$NISSAN_ROOT/work`. The default is `~/nissan`:

   ```sh
   export NISSAN_ROOT="$HOME/nissan"
   mkdir -p "$NISSAN_ROOT/work/language-speech"
   git clone https://github.com/prasys/nz-leaf-discovery.git
   cd nz-leaf-discovery
   ```

Never put the card image, the GID or any audio into the git repo. They hold
Nissan/Clarion data and personal data from your car.

## Step 1: back up the whole card

Take the card out of the car. Follow [BACKUPS.md](../BACKUPS.md) §2. In short:

```sh
diskutil list                                  # find the card: diskN, e.g. disk4
diskutil info -plist disk4 | grep -A1 TotalSize   # note the exact size in bytes
diskutil unmountDisk disk4
sudo python3 -I tools/nz-clock/backup_card.py --device disk4 \
  --work-root "$NISSAN_ROOT/work" --expect-bytes <TotalSize>
```

Pick the disk **by its exact size**, never by its name, and make sure it is not
your computer's own disk. The backup ends in `backup-report.json` with
`"status": "VERIFIED_READ_ONLY_CARD_BACKUP"` and a `sha256`. Copy the backup
somewhere off the computer as well.

## Step 2: get the stock GID out of your backup

```sh
B="$NISSAN_ROOT/work/nz-clock/backups/<stamp>"
python3 -I tools/language-speech/clip_pack.py extract-gid \
  --image "$B/card-before-patch.img" \
  --output "$NISSAN_ROOT/work/language-speech/SJP00300.GID"
```

It must say `"is_pinned_stock": true` (sha256 `6733c2b2…`). **If it says false,
stop.** Your unit has different audio and our clip numbers may not match. Open
an issue with the sha256 and your firmware version.

## Step 3: choose a path

| Path | You need | Result |
|---|---|---|
| **A. Our NZ English voice** (Penny) | nothing extra | the exact builds that play in our car |
| **B. Your own wording or voice on ElevenLabs** | an ElevenLabs account and key, ffmpeg | your voice and words |
| **C. Any other TTS engine or your own recordings** | ffmpeg | anything you can save as audio |

See all clips and their wording, and how long each one may roughly be:

```sh
python3 -I tools/language-speech/clip_pack.py list --clip-set greeting
python3 -I tools/language-speech/clip_pack.py list --clip-set ev
```

`approx_ssc_seconds` is a rough limit after the tool trims silence. The real
limit depends on the audio; the build step tells you exactly which clips don't
fit.

**Paths B and C: make your wording files first.** Make one file per clip set,
even if you keep our wording, because every later command reads them:

```sh
L="$NISSAN_ROOT/work/language-speech"
for set in greeting ev; do
  python3 -I tools/language-speech/clip_pack.py list --clip-set $set | cut -f1,2 > "$L/my-wording-$set.tsv"
done
```

To use your own words, edit the `en_nz` column and keep the clip numbers (for
example clip 765 `Hello.` → `Kia ora.`). Put `VOICE_WORDING` with the file
**for the set you're working on** in front of each command, as shown below,
rather than exporting it once. A greeting file can't be used for EV clips, and
the tool refuses if you try.

### Path A: our Penny voice packs

Download `penny-greeting-v1.1.zip`, `penny-ev-v2.zip` and `SHA256SUMS` from
the release [`voice-penny-v2`](https://github.com/prasys/nz-leaf-discovery/releases/tag/voice-penny-v2)
and check them with `shasum -a 256 -c SHA256SUMS`. They contain only our English clips (encoded
exactly as the unit plays them), preview WAVs to listen to, and a manifest.
The voice is ElevenLabs "Penny" (`eleven_multilingual_v2`), generated on a paid
ElevenLabs plan.

```sh
L="$NISSAN_ROOT/work/language-speech"
unzip penny-greeting-v1.1.zip -d "$L/packs"; unzip penny-ev-v2.zip -d "$L/packs"
python3 -I tools/language-speech/clip_pack.py build \
  --pack "$L/packs/penny-greeting-v1.1" --stock-gid "$L/SJP00300.GID" \
  --output "$L/en-greeting/build-penny-v1.1"
# Optional: the EV alerts go on top of the greeting build.
python3 -I tools/language-speech/clip_pack.py build \
  --pack "$L/packs/penny-ev-v2" --stock-gid "$L/SJP00300.GID" \
  --base "$L/en-greeting/build-penny-v1.1/SJP00300.GID" \
  --output "$L/en-ev/build-penny-v2"
```

The builds are byte-identical to ours: greeting `0a80b637…`, greeting plus EV
`4635b412…`. Those hashes are already pinned in the writer, so skip to step 5.

### Path B: your own wording or voice (ElevenLabs)

**Wording.** Use the wording files from step 3. Use plain English
letters and punctuation only. The greeting plays clips in a fixed order (greeting →
month → day → weekday → safety line), so each clip must still make sense in
that slot. You can't add new greetings (Christmas, birthdays): the unit only
picks among the existing ones.

**Key.** Put `ELEVENLABS_API_KEY=...` in a local file outside the repo and
point `ELEVENLABS_ENV_FILE` at it. The tool reads it in-process and never
prints or saves it.

**Voice.** List voices, render short samples of two or three, and listen:

```sh
export ELEVENLABS_ENV_FILE="$HOME/.config/elevenlabs.env"
python3 -I tools/language-speech/eleven_greeting.py voices --accent "new zealand" \
  --output "$L/en-greeting/voices.json"
# A public-library voice must be added to your account once before it can speak:
python3 -I tools/language-speech/eleven_greeting.py add-voice \
  --catalog "$L/en-greeting/voices.json" --voice <id>
python3 -I tools/language-speech/eleven_greeting.py samples --voice <id1> --voice <id2> \
  --output "$L/en-greeting/samples"
VOICE_WORDING="$L/my-wording-greeting.tsv" python3 -I tools/language-speech/eleven_greeting.py \
  render --voice <chosen id> --clip-set greeting --output "$L/en-greeting/render-mine"
VOICE_WORDING="$L/my-wording-ev.tsv" python3 -I tools/language-speech/eleven_greeting.py \
  render --voice <chosen id> --clip-set ev --output "$L/en-ev/render-mine"
```

`voices --defaults` lists ElevenLabs' default voices instead. `--model`
picks another ElevenLabs model. Only the default, `eleven_multilingual_v2`, has
been tested here. For any other model the tool drops `use_speaker_boost`, which
v3 doesn't support. Check ElevenLabs' current model list, settings and pricing
before a full render. A full render is 56 short requests for the greeting and
41 for the EV set.

Then go to step 4.

### Path C: any other TTS engine, or your own voice

Make one audio file per clip in a folder such as `~/my-clips/greeting` (`mkdir -p ~/my-clips/greeting ~/my-clips/ev`),
named `clip0764.wav`, `clip0765.wav` and so on, four digits
(wav, mp3, flac, aiff, m4a or ogg), saying exactly the clip's wording. Then
import them:

```sh
L="$NISSAN_ROOT/work/language-speech"
VOICE_WORDING="$L/my-wording-greeting.tsv" python3 -I tools/language-speech/import_wavs.py --clip-set greeting \
  --input ~/my-clips/greeting --output "$L/en-greeting/render-mine" --label "piper:en_GB-alba-medium"
VOICE_WORDING="$L/my-wording-ev.tsv" python3 -I tools/language-speech/import_wavs.py --clip-set ev \
  --input ~/my-clips/ev --output "$L/en-ev/render-mine" --label "piper:en_GB-alba-medium"
```

Keep greeting and EV files in separate folders. The import records the wording you give it. It can't
check what a recording actually says, so listen to each one.

The import converts to the unit's format (mono, 16-bit, 22,050 Hz) and writes
the same receipts an ElevenLabs render has. Examples of making the files:

```sh
# macOS built-in voices (free, offline). -r 220 speaks a little faster so every clip fits.
python3 -I tools/language-speech/clip_pack.py list --clip-set greeting | tail -n +2 |
while IFS=$'\t' read clip text _; do say -r 220 -o ~/my-clips/greeting/clip$(printf %04d $clip).aiff "$text"; done

# Piper (free, offline). Install it and download a voice (.onnx plus its .onnx.json)
# first: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md
python3 -I tools/language-speech/clip_pack.py list --clip-set greeting | tail -n +2 |
while IFS=$'\t' read clip text _; do
  echo "$text" | piper --model en_GB-alba-medium.onnx --output_file ~/my-clips/greeting/clip$(printf %04d $clip).wav
done
```

These loops read our wording. If you changed yours, loop over your file
instead (`tail -n +2 "$L/my-wording-greeting.tsv"`). For the EV set use
`--clip-set ev` (or `my-wording-ev.tsv`) and `~/my-clips/ev`.

Any engine works as long as it gives one audio file per clip: use the
engine's own tool or API example to save each clip, then run `import_wavs.py`.
Engines people can adapt (check each one's licence before sharing audio you
make with it):

| Engine | Runs | Notes |
|---|---|---|
| ElevenLabs (path B) | cloud, paid | what we used; NZ-accent voices in the public library |
| Azure AI Speech | cloud, paid | has `en-NZ` neural voices |
| OpenAI, Google Cloud TTS | cloud, paid | several English voices; check accents on offer |
| Piper | local, free | good quality, many voices, runs on a laptop or Raspberry Pi |
| macOS `say` | local, free | built in; tested here end to end with `-r 220` |
| Your own recordings | local | record each clip in a quiet room; keep them short |

Tips: keep each clip short and crisp with no long pauses. The builder trims
leading and trailing silence, levels the loudness, and can speed a clip up by
at most 12 %.

## Step 4: build (paths B and C)

The build needs the unit's SSC codec tables, which come from your own
firmware's `Speech.exe`. Extract it once from your backup image:

```sh
L="$NISSAN_ROOT/work/language-speech"
python3 -I tools/mtcp/mtcp.py --card-image "$B/card-before-patch.img" --no-reference \
  --out-dir "$NISSAN_ROOT/work/mtcp"
python3 -I tools/language-speech/extract_speech.py "$NISSAN_ROOT/work/mtcp/g214-rom.bin" "$L/rom/Speech.exe"
```

Then fit and build. **Always use these loudness settings.** Without them the
clips are 10–20 dB quieter than stock and sound silent in the car.

```sh
VOICE_WORDING="$L/my-wording-greeting.tsv" \
python3 -I tools/language-speech/prepare_greeting.py "$L/SJP00300.GID" \
  --speech-exe "$L/rom/Speech.exe" --audio "$L/en-greeting/render-mine" \
  --output "$L/en-greeting/build-mine" --rms-dbfs -16 --peak-dbfs -2
```

Read `fits.tsv` in the output. Every row must say `FIT`. If any say
`OVERFLOW_OR_QUALITY_FAIL`, shorten that clip's wording or speak it faster, then
render and build again into a new folder. When every clip fits, the folder has
`SJP00300.GID` and `welcome-example.wav`, a sample of what the car will play.
Listen to it.

For EV alerts, build on top of your greeting build and pass the stock GID too:

```sh
VOICE_WORDING="$L/my-wording-ev.tsv" \
python3 -I tools/language-speech/prepare_greeting.py "$L/en-greeting/build-mine/SJP00300.GID" \
  --stock-gid "$L/SJP00300.GID" --clip-set ev --speech-exe "$L/rom/Speech.exe" \
  --audio "$L/en-ev/render-mine" --output "$L/en-ev/build-mine" --rms-dbfs -16 --peak-dbfs -2
```

## Step 5: pin your backup and build

The writer refuses anything it hasn't been told to expect. Make a pins file
with **your** card size, **your** backup hash and (paths B and C) **your**
build hash:

```json
{
  "card_bytes": 16206790656,
  "backup_sha256": ["<sha256 from your backup-report.json>"],
  "builds": {
    "<greeting build_sha256>": "my greeting v1",
    "<EV build_sha256>": "my greeting v1 + EV v1"
  }
}
```

Save it as `$NISSAN_ROOT/work/language-speech/my-pins.json`. Pinning is your
own review step: pin a build only after you have listened to it. Keep **every**
build you might find on the card or roll back to in `builds`. The writer only
accepts a card whose current GID is stock or a pinned build, so if you drop the
greeting you wrote last month, it won't recognise the card later. For path A,
leave `builds` empty (`{}`); our two builds are already pinned.

## Step 6: write to the card

The writer checks everything first and changes nothing unless you add
`--apply`. It writes one sector-aligned window inside the GID file that covers
the changed clips. Bytes in that window outside those clips are written back
unchanged. It keeps a rollback copy of the window, reads it back to compare,
and leaves a JSON receipt.

```sh
diskutil list                       # find the card by its exact size again
diskutil unmountDisk disk4
sudo -k
# 1. Read-only check. Look for "READ_ONLY_PREFLIGHT_PASSED" and "live": "stock GID".
# sudo drops most environment variables, so pass NISSAN_ROOT through env.
sudo env NISSAN_ROOT="$NISSAN_ROOT" python3 -I tools/language-speech/write_gid.py --device disk4 \
  --backup "$B/card-before-patch.img" --build "<your SJP00300.GID>" \
  --work-root "$NISSAN_ROOT/work" --pins "$NISSAN_ROOT/work/language-speech/my-pins.json"
# 2. The same command with --apply added.
# 3. Check the receipt it prints: status WRITTEN_AND_BYTE_VERIFIED_HARDWARE_UNTESTED.
diskutil eject disk4
```

If the check says the GID moved, the live file is unknown, or the backup
doesn't match, **stop**. Nothing has been written.

## Step 7: test in the car

- **The greeting only plays once per period, on Japan time.** Periods start at
  05:00, 11:00 and 17:30 JST, which is 09:00, 15:00 and 21:30 in NZ summer
  time (08:00, 14:00, 20:30 in NZ winter). Elsewhere, convert from JST (UTC+9). If you turn the car on twice in
  the same period, the second start is silent. That is normal, not a broken
  build. Test at the start of a fresh period.
- The greeting and date follow Japan's date and time.
- If a clip plays but is quiet, rebuild with the loudness settings in step 4.
- EV alerts play when the car raises them (low battery, charging started,
  doors), so they can take a while to hear.

## Rollback

Run step 6 again with `--build` pointing at the previous build, or at
`$NISSAN_ROOT/work/language-speech/SJP00300.GID` for stock. The writer
accepts stock, or any pinned build, as the target. The full-card backup from
step 1 restores everything else ([BACKUPS.md](../BACKUPS.md) §6).

## Limits

- Only the 56 greeting clips and the 41 EV alert clips can be changed. Navigation
  guidance and the rest are still Japanese.
- The unit's speech engine for dynamic text (street names, voice recognition)
  is Japanese; recorded clips are all we can replace.
- Each clip has a fixed maximum size. You can't add clips or reorder the playlist.
- The greeting follows JST and Japanese holidays.
