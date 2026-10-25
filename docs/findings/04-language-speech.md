# language-speech — findings

Scope: SPEECH/JP, fonts, UI strings and encodings, the language/region question, CDDB, and date/time strings.
All work was read-only against `~/nissan/sdcard/mnt/p1` and `nissan-sd-485-1972-00.img`.
Carved outputs and scripts are in `~/nissan/work/language-speech/` (scripts in `scripts/`).

Confidence tags: **[confirmed]** = verified from bytes; **[likely]** = strong inference; **[guess]** = speculation.

---

## TL;DR

1. **SPEECH/JP is a Nuance speech stack, plus Clarion recorded prompts.** [confirmed]
   - `TTS/TJP00300.TTS`: Nuance Vocalizer 5.2.3 Japanese text-to-speech (TTS), voice "Nbk", female, outputs 22050 Hz 16-bit PCM. The voice is synthesized; it is not a set of recorded clips.
   - `VR/`: Nuance VoCon voice-recognition grammars, with 268 command IDs and per-prefecture POI/address grammars.
   - `GID/SJP00300.GID`: about 2,071 recorded guidance clips and 14,421 phrase playlists. A few clips are raw 16-bit PCM (22050 Hz plays correctly). Most use an **unidentified proprietary codec**, so ffmpeg cannot decode them as-is.
2. **The UI language is driven by the head-unit firmware, not by the SD card's p1 data.** [likely]
   - p1 has no fonts and no UI string tables.
   - The UI strings are in the **unpartitioned lead area (sectors 1–888,832)**: a Japanese Windows Embedded Compact 7 OS plus the Clarion/Nissan app.
   - The firmware is a **global platform**. It has a language selector (`SET_LANGUAGE_SELECT_LANGUAGE_LIST`, `SK_SCT_ENGLISH_NAM_CLICK`, `SK_SCT_ENGLISH_EUR_KM_CLICK` …), SiriusXM / miles / US-address voice commands, and loads speech from `D2/SPEECH/VR/%s`.
   - p1 only ships `SPEECH/JP`, so no English voice data is on the card.
3. **Region markers:** the map DB declares `SYSTEM_AREA='J4'`, `SYSTEM_LANG='日本語'`, `SYSTEM_CHARACTER_CODE='SHIFT JIS'`, `SYSTEM_DATA_PROVIDER='HITACHI'`, map version `15-16年度版地図1` / `20150401`. Gracenote is `eCDDB [JP]` rev 6572. [confirmed]
4. **Clock-relevant finds** (details in §7):
   - The firmware has `SET_CLOCK_SETTING_MENU`, `SET_CLOCK_TIMEZONE_SETTING_MENU` and `SET_CLOCK_SUMMERTIME_SETTING_MENU` screens.
   - It has GPS code `GPS:SetTimeToSystem` / `GPS:SetTimeZoneFromSystem`.
   - It has a **LEAF EV-timer module that pushes clock corrections to the car's VCM (vehicle control module)**: `VCM時刻修正要求`, `bUpdateVcmClock_Flg`, `recommend_watch_adjust_vcm`, `curr_hour_vcm`.
   - `DBDIR/BHOLIDB` contains a **Japanese public-holiday calendar for 2015–2034 only**.
5. **The car is very likely a Nissan LEAF.** Evidence: the TTS user rule "Leaf to Home"; EV voice commands (charging stations, energy flow); the EvTimer, 100V/200V/6kW charge-time and "エアコン優先/充電優先" strings in the firmware. [likely]

---

## 1. SPEECH/JP (249 files, 160 MB)

### 1.1 Common container format (TTS, GID, AGM) [confirmed]
These three files share a little-endian archive format:

```
0x00  16 bytes ASCII   "0000506120150216"   -> 8-digit id/version + build date YYYYMMDD
0x10  u32  total file size
0x14  u32  end of directory / first data offset
0x18  u32  (unknown; e.g. 0x4efb40 in TTS)
0x1C  u32  entry count N
0x20  N x 24-byte entries: char name[12] (8.3), u32 offset, u32 padded_size (4-aligned), u32 real_size
```
Member `*0010.MAP` is a UTF-16LE list of `original-filename, container-member-name` pairs.

| File | Header id/date | Entries | Notes |
|---|---|---|---|
| `TTS/TJP00300.TTS` (52.5 MB) | 00005061 / 2015-02-16 | 16 | Nuance Vocalizer |
| `GID/SJP00300.GID` (37.9 MB) | 00005075 / 2015-07-17 | 1 (`SJP00000.GID`) | Recorded prompts |
| `VR/VJP00300.AGM` (1.29 MB) | 00005075 / 2015-07-17 | 53 | VoCon grammars |

Extraction: `scripts/extract.py <container> <outdir>`. Outputs are in `work/language-speech/{tts,gid,agm}/`.

### 1.2 TTS — Nuance Vocalizer (RealSpeak lineage) [confirmed]
Member map from `TJP00010.MAP`:

| Member | Original name |
|---|---|
| TJP01000.DAT | `lid.dat` (starts `FF FE 00 00 "SCANSOFTSYS_DCT"`) |
| TJP02000.DAT | `clc_jpj_cfg3.dat` (byte-identical to `G2P/clc_jpj_cfg3_v1_0_2.dat`; md5 64dd085a…) |
| TJP02001.DAT | `pp_jpj.dat` |
| TJP03000.DAT | `rby_ling_jpj_dic.dat` |
| TJP04000.HDR | `vauto_pipeline_jpj_nbk_22_dri80_1175mrf22.hdr` (plain XML) |
| TJP05000–05006.DAT | `rby_synth_nbk_22_dri80_1175mrf22_{ddt,did,dur,exd,f0,httsr,tbl}.dat` (voice DB, ~37.9 MB in ddt) |
| TJP00600.USR | `UserDictInfo_JPN_JPJ.dcb` (car-name user dictionary: CARAVAN, CUBE, ELGRAND, FUGA, GT-R, JUKE, LAFESTA, LATIO, LEAF, MARCH, MOCO, MURANO, NISSAN, NOTE, OTTI, ROOX, SERENA, SKYLINE, SYLPHY, TEANA, VANETTE, WINGROAD, X-TRAIL …) |
| TJP00700.USR | `UserRuleset_JPN_JPJ.txt` (plain text regex rules) |

Key fields from the `.HDR` XML:
```
BROKERSTRING pipeline/Japanese/nbk/22/dri80_1175mrf22/text/pcm
language Japanese, langcode JPJ, langid 32, langversion 5.2.3.12116
voice Nbk, voiceversion 5.2.3.12320, gender Female
frequencyhz 22050, audiooutputmimetype audio/L16;rate=22050, nativetypeofchar utf-16
```

`UserRuleset_JPN_JPJ.txt` rewrites English model names to katakana, e.g. `/\bLeaf to Home\b/ --> "リーフトゥーホーム"`, plus FAIRLADY Z, SKYLINE COUPE/CROSSOVER and Zero Emission.

The engine and voice DB are proprietary Nuance formats. There is nothing to "play" here: audio is synthesized at runtime from UTF-16 text supplied by the firmware.

### 1.3 VR — Nuance VoCon [confirmed]
- `G2P/acmod4_900_jpj_gen_car_f16_v1_0_1.dat`: VoCon acoustic model (Japanese, car environment, 16 kHz front end). It is byte-identical to AGM member `RJP00100.ACM` (md5 44bd9775…).
- `G2P/clc_jpj_cfg3_v1_0_2.dat`: Nuance grapheme-to-phoneme (G2P) / front-end package. It contains embedded XML `<NUANCE><VERSION>NUAN_1.0…` and an `NVAR … pipeline` tag.
- `G2P/{AlbumTitle,ArtistFromSingleAlmum,SingleTitle}1994-2013.dcb`: pronunciation dictionaries for music titles from 1994–2013 (magic `FA DE 5C 14`, the same as the TTS user dict). They are used for voice commands like "play artist …".
- `VR/VJP00300.AGM`: 52 `.lcf` grammar contexts (magic `3C 28 D6 35 …`) plus `scene.tbl`. Grammar names include `sn_root`, `sn_audi_*`, `sn_phon_*`, `sn_navi_*` (including `state`, `street`, `house_number` from the global template), `sn_info_*`, `sn_zemi_*` (Japanese railway/ZEMI), `sn_voicetag` and `sn_recmode`.
- `scene.tbl` (`RJP0102F.AGM`): maps grammar to `command#HUL_ASR_*`. There are 268 unique command IDs, saved to `work/language-speech/vr_commands.txt`. Notable IDs:
  - Global/US: `AUD_WID_PLAY_SXM`, `INF_WID_SXM_*`, `NAV_WID_1MILE`, `NAV_WID_FULL_ADDRESS_H_S_C_S`, `NAV_WID_SELECT_STATE`, `AUD_WID_PLAY_NISSANCONNECT_APP`.
  - Japan: `NAV_WID_JPN_ADDRESS_TOBAN`, `NAV_WID_JPN_PREFECTURE_POI_NAME`, `INF_WID_VICS_BEACON_INFORMATION`, `INF_WID_VICS_FM_INFORMATION`.
  - EV: `EMI_WID_QUICK_CHARGING_STATIONS`, `INF_WID_ENERGY_FLOW`, `EMI_WID_DRIVING_RANGE`.
  - **None relate to the clock, time or language.**
- `VR/VDE/` (Voice Destination Entry):
  - `JPN_JPJ_POI_001..047.tbl` and `JPN_JPJ_VDE_001..047.tbl`: one per prefecture (47 = all Japanese prefectures).
  - `poiname-oneshot-N-odl.lcf` and `vde-oneshot-N-type{1,2}-odl.lcf`: per-prefecture grammars.
  - `toban_{top,banchi,go}.lcf`: address-number grammars (番地/号).
  - `JPN_JPJ_CAT_TXT.tbl`: plain UTF-8, length-prefixed POI category names (e.g. `ゴルフ場・ゴルフ練習場`, `温泉・お風呂`, `時計・アクセサリー`).

### 1.4 GID — recorded guidance prompts [confirmed structure; codec unknown]
Inside `SJP00000.GID` (offsets relative to the member, which starts at file offset 0x38):
```
0x00  u32[9] = 14421, 0xE1A0, 22400, 65536, 44000, 10, 22, 44, 30   (meaning of most fields unknown)
0x38  u32[14421]  phrase-id -> offset into playlist area (0xE1A0..0x13904)
0xE1A0 playlist area: sequence of u32 per phrase:
        bit31 set   -> silence of (value & 0x7FFFFFFF) ms   (seen: 50, 100, 200, 300, 400, 700)
        bit31 clear -> offset of a 16-byte clip descriptor
0x13920 u32 clip_count = 2071 (0x817), u32 0x81A0, u32 audio_bytes?=37769024, ...
0x13940 clip descriptors, 16 bytes each:
        u8[4] format, u32 offset, u32 padded_size, u32 size
        format 02 01 01 02 = raw PCM s16le mono (17 clips: chimes/tones; 22050 Hz looks right)
        format 02 01 01 01 = 1 clip (variant; probably PCM)
        format 02 04 01 02 = compressed (2053 clips, ~37.1 MB)
```
- The PCM clips were written as WAV (22050 Hz assumed) to `work/language-speech/gidclips/clipNNNN_pcm.wav`. ffprobe reads them fine. For example, clip 3 is a 1.2 s chime with harmonics at ~1.9/4.4/7.4 kHz (spectrogram in `spec/`). Clips 1391–1397 are silence of increasing length.
- Compressed clips (`clipNNNN_02040102.bin`) are a bit-packed stream:
  - Bytes are not frame-aligned; the strongest byte autocorrelation is at lag 3, from long `…b6 db 6d…` / `…49 24 92…` runs (period-3 bit patterns, probably silence/zero codewords).
  - Clips usually start with `1C xx` or `1D xx`.
  - Decoding as G.726 (2/3/4-bit, LE/BE) produced noise, so it is not G.726.
  - [guess] It may be Nuance/Clarion proprietary, possibly the same "MRF"-family coder that the TTS voice uses internally (`coder 1175mrf22`).
  - **Conclusion:** ffmpeg/sox cannot play these without reversing the codec, which probably requires the decoder from the firmware.
- There is no text index on the card mapping phrase IDs to words. The firmware chooses phrase IDs.

### 1.5 DBDIR/BVOICE* — recorded name audio (798 MB) [likely]
- `BVOICEB/D/I` use the DBDIR page-DB format (`flhb` header; see §4).
- Data pages (for example at 0x100000) start with `XX 03 01 55` and contain the **same bit-pattern fingerprint** as the GID compressed clips (`6d b2 d9 2d`, `49 24 92 49`). Entropy is about 7.5.
- [likely] This is recorded audio of place/road/facility names in the same proprietary codec.

---

## 2. Fonts [confirmed absent on p1]
- No TTF/OTF/TTC/BDF/FNT files or font filenames anywhere on p1. The few `OTTO` / `ttcf` byte hits were inside image or compressed data, i.e. false positives.
- Fonts must be in the firmware (lead raw area / internal flash). The lead area has `timezones.dll`, `MLANG.dll` and similar WinCE components; a font search there was not done.

## 3. Text encodings seen on the card [confirmed]
| Where | Encoding | Endianness |
|---|---|---|
| Map DB (DBDIR) strings | **Shift-JIS** (declared `SYSTEM_CHARACTER_CODE='SHIFT JIS'`) | records are LE in the `flhb` page DB; the holiday table is **BE** |
| `ICNSC001.DAT` (POI icon categories/brands, e.g. ガソリンスタンド, エネオス, セブンイレブン) | Shift-JIS | **big-endian** u16 fields |
| `BICON001/BICON001.DAT` header | **UTF-16BE**: `CLARION`, `ZENRIN`, `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `DATA VERSION 15/04/01/01`, `V05.00.00`; followed by PNG icons | BE |
| `BTOLCB` (toll booths) | Shift-JIS text, e.g. `徴収時間午前８時から午後８時`, `通行料金は前払いです。` | – |
| Nuance SPEECH | UTF-16LE (MAP files, TTS native), UTF-8 (`CAT_TXT.tbl`), ASCII/UTF-8 (`UserRuleset`) | LE |
| CDDB | UTF-8 XML (`elists.inv`, `gnlists.db`) inside Gracenote `GNDB` containers | mixed |
| Firmware (lead raw area) | WinCE resources in UTF-16LE (Japanese); app debug strings in Shift-JIS; app identifiers in ASCII | LE |
| `CMP.LST` | ASCII list of `\SystemSD\REFER001\*.dat` paths (WinCE path style) | – |

## 4. DBDIR string-bearing files (language/region-relevant parts)
- Every DB file starts with `XX XX 01 55 "flhb" <u16 namelen> <NAME>`. Pages are 0x1000 bytes, and each page begins with the same 4-byte tag.
- `DBDIR/BALLDD` at 0xE000 is a key/value table. Record format: `02 C0 <klen> KEY <vlen> VALUE` (Shift-JIS). Decoder: `scripts/balld.py`.
  ```
  SYSTEM_FORMAT_VERSION='0100'  SYSTEM_MACHINE_TYPE='0000'  SYSTEM_APP_VERSION='0000'
  SYSTEM_AREA='J4'              SYSTEM_LANG='日本語'
  SYSTEM_LEVEL_01..07           SYSTEM_DATA_PROVIDER='HITACHI'
  SYSTEM_CHARACTER_CODE='SHIFT JIS'  SYSTEM_MAP_RANGE='3280:720:10080:6240'
  SYSTEM_MAP_VER='15-16年度版地図1'   SYSTEM_MAP_VER_NO='20150401'
  TABLE_DIVIDE='AREA_CLS3_CODE'
  ```
  `SYSTEM_AREA='J4'` and `SYSTEM_LANG` are the only explicit region/language codes on p1.
- `DBDIR/BHOLIDB` is the holiday calendar; see §7.3.
- A multi-encoding keyword scan of all of p1 is in `work/language-speech/kw_hits.txt`. Most 2–3 character hits inside large compressed `B*B` files are random; the meaningful ones are listed in this note.

## 5. Language: card vs firmware [likely]
Evidence that the **firmware drives the UI language** and can support several languages:
- Firmware identifiers (lead raw area, Shift-JIS/ASCII):
  - `SET_LANGUAGE_UNIT_SETTING_MENU`, `SET_LANGUAGE_SELECT_UNIT_MENU`, `SET_LANGUAGE_SELECT_LANGUAGE_LIST`, `SS_TMR_SET_LANGUAGE_LIST`
  - `SK_SCT_SELECT_LANGUAGE_CLICK`, `SK_SCT_ENGLISH_NAM_CLICK`, `SK_SCT_ENGLISH_EUR_MILE_CLICK`, `SK_SCT_ENGLISH_EUR_KM_CLICK`, `AUSTRALIAN_ENGLISH`
  - `NAVISET_CC_REQ_SET_LANGUAGE`, `NAVISET_CC_NTF_CHANGE_LANGUAGE`, `NAVISET_CC_NTF_MTR_CHANGE_LANGUAGE` / `…MTR_LANG_CONF…` (the meter/cluster language follows the head unit), `SPEECH_CC_NTF_COMPLETE_LANG_CHANGE`, `OBJ_Setting_readExpLanguage`, `ConfigLanguage`.
- Speech path template `D2/SPEECH/VR/%s` (Shift-JIS area at img byte 0x561d72b). Combined with the folder `SPEECH/JP` and the file prefixes `TJP/SJP/VJP/RJP`, this suggests a language code such as `JP` is substituted at runtime. [likely] Other markets would ship e.g. `SPEECH/EN…`.
- The WinCE OS is the **Japanese** build: Japanese menus, IME, "Windows Embedded Compact によって自動的に夏時間の調整が行われました。", "日付、時刻、タイムゾーンの設定を変更します。". Its WinCE locale tables also list other locales, which is normal.
- The p1 card contains **only Japanese** speech and Shift-JIS map data. There are no EN TTS/VR files, so even if the firmware offered English, voice guidance and recognition data for it are missing from this card.
- [guess] On the JP build the language menu is probably hidden or offers only 日本語. Whether the UI has English string resources in the app image is not yet confirmed (the app's UI text may be bitmaps or compressed).
- **Update [confirmed]:** the UI text on this card comes from a modified skin file on hidden p2 (`/SkinChange/002/substance.skn`), not from the firmware; see [11](11-skin-pipeline.md).

## 6. CDDB (Gracenote) [confirmed]
- `revinf.txt`: `Revision 6572 (build 1) of the eCDDB database[JP][Little Endian].`
- Build timestamps inside the file headers: `2014-11-21 03:08:10Z` (`elists.inv`, `emms.cgm`, `pstplgen.bml`) and `2014-11-21 03:08:02Z` (`emms.mdt`). Common header bytes `CA 55 E7 7E 00 00 04 44`.
- `GNDB` containers: `cddbplm.gcf`, `emms.cgx`, `emms.idx` (LE variant), `gnlists.db`.
- `elists.inv`: XML `<INVENTORY VERSION="2">`, `LFS_ID 749`, `CDS_ID 533C947281C8A982`, `REVISION LEVEL 11`, plus a list of "Various Artists" synonyms in many languages.
- `gnlists.db`: language list `eng` (ID 1, "English") and `jpn` (ID 44, **DEFAULT**, "Simplified Japanese"); genre hierarchy `jps` includes J-Pop, Enka, Kayoukyoku, Rakugo/Manzai, Traditional Okinawa and similar.
- `emms.mdt` (432 MB) is the music metadata store; `emms.idx` (76 MB) is its index.
- This is a Japanese-region embedded CDDB snapshot from late 2014, consistent with the 2015 map.

## 7. TIME / CLOCK / TIMEZONE / GPS / region — everything found
### 7.1 Firmware (lead raw area, sectors 1–888,832) [confirmed strings; behaviour is inference]
Image byte offsets are given so the raw-areas/firmware topic can follow up.

| Offset (img) | String | Meaning |
|---|---|---|
| 0x57ab6ec | `SET_CLOCK_SETTING_MENU` | Clock settings screen |
| 0x57ab6a8 | `SET_CLOCK_TIMEZONE_SETTING_MENU` | **Time-zone setting screen exists** |
| 0x57ab6c8 | `SET_CLOCK_SUMMERTIME_SETTING_MENU` | **Summer-time (DST) setting screen exists** |
| 0x5777528 / 0x577f98c / 0x577f9a4 | `SK_SCT_TIME_ZONE_CLICK`, `SK_SCT_CLOCK_SET_CLICK`, `SK_SCT_CLOCK_CLICK` | Soft-key handlers |
| 0x57a1fb8 | `POP_SLF_INFO_CLOCK_SETTING_UPDATING` | "Updating clock setting" pop-up |
| 0x576afa8 | `TIMEOUT_CLOCK_SETTING` | |
| 0x57a4c24.. | `POP_EV_INF_TUNITERROR_CLOCK_ERROR`, `…CLOCK_ADJUSTING`, `…CLOCK_ADJUST_COMPLETE`, `SK_SCT_POP_EV_INF_TUNITERROR_CLOCK_ERROR_TIME_REPAIR_CLICK` | Telematics/EV unit clock error and repair flow |
| 0x58485dc | `VCMの時刻修正要求` | "VCM time-correction request" |
| 0x5848a90 | `VCM時刻修正完了応答` | "VCM time-correction complete response" |
| 0x5848434.. | `MSG_EVTIMER_CC_CHGCURCLOCK_NOTIFY`, `MSG_EVTIMER_CC_CHG_CURCLOCK(_RESULT)`, `MSG_TYPE_VCAN_EVTIMER_REQ_SET_CLOCK`, `MSG_TYPE_VCAN_EVTIMER_ACK_SET_CLOCK` | Head unit → VCM clock set over CAN |
| 0x583c8e4 | `VCL_EvTimerBackUpInfo->bUpdateVcmClock_Flg : %d` | Backed-up flag: "update the VCM clock" |
| 0x5848d98 | `recommend_watch_adjust_vcm` | VCM signal "recommend clock adjust" |
| 0x5848e08.. | `curr_day_of_week_vcm`, `curr_hour_vcm`, `curr_min_vcm`, timer1/2 start/end hour/min, `5F9`/`5B3` CAN frames | VCM reports its own current time (CAN IDs 0x5F9 / 0x5B3) |
| 0x5849304 | `9:時刻修正フラグ設定`, `CLOCE MODIFY FLAG(0 OR 1)を入力してください` | Debug command to set the clock-correction flag |
| 0x5849330 | `11:OBJからのオフセット時間変化` / `OBJからのオフセット時間変化` | "Offset-time change from OBJ" (time offset event) |
| 0x1533e2cc | `GPS:SetTimeToSystem >> Invalid parameter(s)!` | **GPS time is written into the WinCE system clock** |
| 0x1533dab4 / 0x1533e7e4 | `GPS:SetTimeZoneFromSystem SetTimeZoneInformation ret = %d…`, `GPS:GpsInit SetTimeZoneFromSystem Failed !` | GPS init applies the system time zone |
| 0x5894a20 | `GPSTimer Create ERR %d` | |
| 0x146e4…–0x146e7… | WinCE exports `GetLocalTime`, `SetLocalTime`, `SetSystemTime`, `GetTimeZoneInformation(ID)`, `SetTimeZoneInformation(ByID)`, `SetTimeZoneBias`, `SetDaylightTime`, `GetTimeZoneList` | OS time APIs |
| 0x1756c1f0 / 0x170a3698 | `timezones.dll`, `(UTC-12:00) International Date Line West`, `(UTC-11:00) Coordinated Universal Time -11` … | Standard WinCE time-zone table (English names) |
| 0x24f3000 | `Windows Embedded Compact によって自動的に夏時間の調整が行われました。 現在の時間が正しいかどうか確かめてください。` | WinCE auto-DST notice (Japanese) |
| 0x2529016 | `自動的に夏時間の調整をする(&D)` | WinCE "auto adjust DST" checkbox |
| 0x575e668 | `SET_AUTO_ADJ_TIMER_SET_ENGINE` | [guess] auto-adjust timer setting |
| 0x58f3618 | `Clock display` | |
| 0x583c8xx | `VCL_EtcBackUpInfo->ImposeDispDate_Year/Month/Day`, `ExpirationDate_Year/Month/Day` | ETC card dates |
| 0x5849104 | `C:/WINCE500/5F9TIMER1DATA.txt`, `…TIMER2DATA.txt`, `5B3DATA.txt`, `CCDATA.txt` | Debug data files (WinCE 5.0 build paths) |
| 0x59014dc | `\SystemSD\ConfigurationWrite.cnf` | **Config file path on the system SD. Not present on p1.** (Relevant to the config-files topic.) |
| 0x15565928 | `0 : Default, 1 : UserSD, 2 : USB, 3 : SystemSD, 4 : SystemSD2` | Storage IDs; this card is "SystemSD" |

[likely] Interpretation for the clock problem: the head unit has a full clock menu (manual set, time zone, summer time). The system time comes from GPS (`SetTimeToSystem`) adjusted by the WinCE time zone. The EvTimer module then forwards corrections to the LEAF's VCM, the car's clock for charge/climate timers. A wrong displayed time could therefore come from:
(a) the time-zone/DST setting;
(b) GPS week-number rollover in the GPS module (common on 2015-era units after the April 2019 rollover) [guess, not verified];
(c) the VCM clock or sync flag.
Which source wins is not determined.

### 7.2 Other dates on the card
- `DBDIR/SPOOL/EDABORT1` and `EDABORT2` have FAT mtimes **2024-10-16 17:42:16 / 17:42:20**. They were written by the head unit, so that is presumably the unit's local clock at the time. 56-byte content: `"EDDBABORT  "`, then values including `0x696ED7DC` and `0x697057DC`. Those differ by exactly 0x18000, so they are probably not epoch timestamps. [guess: counters/addresses] Worth comparing with the actual date of that event if the owner knows it.
- `DBDIR/EDMMAP` mtime `2006-01-01 12:00:12`, which looks like a default/unset-RTC timestamp written by the device. The other DB files are dated 2015-03-11.
- CDDB build dates are 2014-11-21Z, map `20150401`, BICON `DATA VERSION 15/04/01/01`, speech containers 2015-02-16 / 2015-07-17.

### 7.3 Holiday calendar `DBDIR/BHOLIDB` [confirmed]
- At file offset 0x28000 (page tag `98 06 01 55`). Big-endian:
  `3C03 0900 019C | u16 nYears=20 | nYears x {u16 year, u16 index, u16 count} | u16 entries[]`.
- Each entry = `month<<12 | day<<7 | type` (type: 4=元日, 8=成人の日, 12=建国記念の日, 16=春分, 20=みどり, 24=憲法記念日, 28=こどもの日, 32=海の日, 36=敬老, 40=秋分, 44=体育の日, 48=文化の日, 52=勤労感謝, 56=天皇誕生日, 60=昭和の日, 64=振替/国民の休日).
- Decoder: `scripts/holid.py`. Full decode: `work/language-speech/holidays.txt`.
- Covers **2015–2034 only**.
- Generated in 2015, so it is **stale for later law changes**:
  - 天皇誕生日 stays 12/23 for all years (it moved to 2/23 from 2020).
  - The 2019 enthronement holidays (4/30–5/2) are missing.
  - The 2020/2021 Olympic holiday moves are missing.
- There is also a data bug: 2031 lists `05/05` twice (type 28 and type 64). The substitute holiday should be 05/06.
- [likely] Purpose: time-dependent routing and regulations ("weekday/holiday" restrictions, traffic prediction). The holiday table does **not** set the clock, but it shows the navigation software consumes the date.

### 7.4 Date/time text in the map data
`BTOLCB` toll booth notes such as `徴収時間午前８時から午後８時`. POI names with 時計 (watch shops). No 年月日 / JST format strings exist on p1 itself.

---

## Open questions
1. What is the GID/BVOICE compressed codec (format tag `02 04 01 02`)? Find its decoder in the firmware. Look near `MSG_SPEECH_GUIDE_OUTPUT` (img 0x588a66a) and the SpeechCC library (`SPEECHCCLibW`, img 0x56ab928).
2. What do the GID header fields (22400, 65536, 44000, 10, 22, 44, 30) mean, and what is the exact sample rate? 22050 is assumed from the TTS and the PCM clips.
3. Does the JP firmware build actually show `SET_LANGUAGE_SELECT_LANGUAGE_LIST`, and does it contain English UI resources? (The app UI text may be bitmaps.)
4. Is `SET_CLOCK_TIMEZONE_SETTING_MENU` / `SET_CLOCK_SUMMERTIME_SETTING_MENU` reachable on the JP build (a hidden or service menu)?
5. Where is the time zone persisted: WinCE registry hive, `\SystemSD\ConfigurationWrite.cnf`, or backup SRAM (`VCL_Backup_getVirtualAddress`, "VSRAM")?
6. Is the GPS receiver affected by GPS week-number rollover?
7. What do the `EDABORT*` content fields mean, and is the 2024-10-16 mtime the real date?

## Suggested next steps
1. **Firmware/raw-areas topic:** decompress or locate the app executable in sectors 1–888,832. The strings around img 0x5700000–0x5900000 are the Nissan/Clarion app (Shift-JIS debug + ASCII IDs). Trace `GPS:SetTimeToSystem`, `SET_CLOCK_*` and `bUpdateVcmClock_Flg` cross-references. Grep for the registry path of the time zone (`HKLM\Time`, `TimeZoneInformation`).
2. Check whether `\SystemSD\ConfigurationWrite.cnf` is a file the unit reads at boot (config-files topic). It is a possible non-invasive switch for settings. **Do not create it on the real card without a full backup and a careful decision.**
3. For the owner: in the unit's 設定 → 時計 (clock) menu, look for タイムゾーン / サマータイム options and a GPS auto-adjust toggle, since the strings show these screens exist. Also check whether the LEAF meter clock follows the head unit. The firmware pushes time to the VCM, so a bad head-unit time may propagate to the charge timers.
4. To hear the voice prompts, reverse the `02 04 01 02` codec (start with the firmware SpeechCC decoder). The PCM chimes are already playable: `afplay ~/nissan/work/language-speech/gidclips/clip0003_pcm.wav`.
5. Optional: search the lead area for font resources (`.ttf` in WinCE `\Windows\Fonts`, e.g. MS Gothic/MS UI Gothic or the Clarion bitmap fonts) to settle the font question.

## Artifacts (all under `~/nissan/work/language-speech/`)
- `tts/`, `agm/`, `gid/`: extracted container members.
- `gidclips/`: 2,071 carved clips (`*_pcm.wav` playable; `*_02040102.bin` compressed) plus `index.tsv` (idx, format, offset, size).
- `spec/`: spectrogram PNGs of PCM clips. `trial/`: failed G.726 decode attempts.
- `vr_commands.txt`, `holidays.txt`, `kw_hits.txt`.
- `raw_lead_strings.txt`: Shift-JIS and UTF-16LE strings from img sectors 1–888,832, each with its image byte offset (50 MB).
- `scripts/`: `arc.py`, `extract.py`, `gid.py`, `gidclips.py`, `period.py`, `kw.py`, `small.py`, `balld.py`, `holid.py`, `imgscan.py`, `u16ctx.py`, `sjisctx.py`, `rawstrings.py`.
