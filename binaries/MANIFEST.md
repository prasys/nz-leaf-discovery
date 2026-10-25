# Binary manifest

Binaries are NOT stored in git (copyrighted firmware + personal data). They live under `$NISSAN_ROOT` (default `~/nissan`). Verify with `shasum -a 256 -c` against the list below.

| sha256 | bytes | path (relative to $NISSAN_ROOT) |
|---|---|---|
| `redacted` | 16206790656 | `sdcard/nissan-sd-485-1972-00.img` |
| `redacted` | 455082496 | `work/raw-areas/pre_s0-888832.bin` |
| `redacted` | 9043968 | `work/raw-areas/settings_800768-818431.bin` |
| `f1c22ed63f522fc3615b527e8e106d4b8b6fd8292ecb959bc7fc336b36819ce5` | 5556456 | `work/raw-areas/slot065536_G314JLNI.066.bin` |
| `3c90f444fc2a5ab5490ec07d4c8d011763d1bf7f6d2265bc80cfb6e20e41200b` | 30737408 | `work/raw-areas/slot157696_G214JLNI.066_MTCP.bin` |
| `d03c3fd0533ad983abb5ca7a311651ae4da07f45b796c5df6a848dae40b17d6d` | 26091608 | `work/raw-areas/slot667648_UP14XNNI.139_nk.nb0.bin` |
| `f34746890221b58b4ee284e422f1051d5b73923560bcdc5b0766e6daf47236aa` | 19382876 | `work/raw-areas/slot749568_PM13XKNI.039_nk.nb0.bin` |
| `ed965096644a8033c970b0b61118909feb295e4fc3385e219066507ba31efd76` | 3711488 | `work/raw-areas/slot790528_BASS_OIXXXVNI.004.bin` |
| `redacted` | 585728 | `work/raw-areas/sram_btA_807648-808791.bin` |
| `redacted` | 158720 | `work/raw-areas/sram_navA_807028-807337.bin` |
| `redacted` | 29696 | `work/raw-areas/sram_sysA_806912-806969.bin` |
| `8d7342dc897084f1909ac28cfedb1a112b1a25f89ac3f576bbb779534f08edf0` | 5588992 | `work/unit-and-clock/g314_region.bin` |
| `0d2a64c7f23ce2bd976b272105f86fac3a4b3e8b7e7e768f00e5015daa30d40a` | 21495296 | `work/mtcp/part-a.bin` |
| `89b8fb5855306312b63365ef2761345a915289f0a771d7e6a2e8556d43b29144` | 21046272 | `work/mtcp/part-b.bin` |
| `8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a` | 42541568 | `work/mtcp/g214-rom.bin` |
| `8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a` | 42541568 | `work/mtcp/reference-lz4.bin` (independent installed liblz4 output) |
| `ea5b5a34d912c3344e3157e453025734474d104046434537775f96c85ae06f4d` | 20025376 | `work/translation/substance.skn` (skin as found, p2 LBA 29925953) |
| `6a54198aa04e6c104c6dd5bdc86005f495dca979bda95549ac687da0821ebbb7` | 20025376 | `work/translation/build/substance.skn` (in-place build; pinned in `write_skin.py`) |
| `d220720b9f282703590cdafc52616269c2882777479f2eb9fae62bbf5e5826c4` | 20025376 | `work/translation/build-repack/substance.skn` (repacked build; pinned in `write_skin.py`) |
| `70f7fd7941e453529269fbcd5dd3823152479ea94359fc93477987b298a4ad68` | 47616 | `work/ce-extract/PM13XKNI.039/modules/navdrv.dll` (rebuilt PE, tools/ce-extract) |
| `093fdebe309e886cdcab49c1e4399e8ad9719a1dd7db2ab19d142272044b4a78` | 27136 | `work/ce-extract/PM13XKNI.039/modules/timezones.dll` |
| `09a2dce87861248fc898969b7014daf58e4a1662420013573726707759ed7069` | 88576 | `work/ce-extract/PM13XKNI.039/modules/VSramSD.dll` |
| `0c020079713e86b22231fc23d68f6ba28c93172659d394b2072c89ec8e9e3033` | 174592 | `work/ce-extract/PM13XKNI.039/modules/nk.exe` |
| `72e24990eedeef585744d87447401054a4eb0371ac802618989fdf841660a2f5` | 45056 | `work/ce-extract/PM13XKNI.039/files/boot.hv` |
| `9f815fb854857fc98be9f36503957c701fe3770508f745df04ab492f84d8be84` | 299008 | `work/ce-extract/PM13XKNI.039/files/default.hv` |
| `6b7d4d6b4ba3e072b040c3c9d80c0b646f6c00241b7e2b0ea7ade9db9906f906` | 28672 | `work/ce-extract/PM13XKNI.039/files/user.hv` |
| `721854fa5393d7ebc244687f27aeebb85eeb5d378f29f13cd9388083b5bbbb55` | 47616 | `work/ce-extract/UP14XNNI.139/modules/navdrv.dll` |
| `668de9a33c42db25adf698be8d86eecfade1e6d374d854e61f5fda6fcce8dab2` | 57856 | `work/ce-extract/UP14XNNI.139/modules/VSramSD.dll` |
| `277393f3a2d8ea07ec77a45c55e4adbee8ac223d93fe0ad8c7cde5dbde20d5c9` | 176128 | `work/ce-extract/UP14XNNI.139/modules/nk.exe` |
| `63df2f3b6dbdbd406750c99812feeaecaf3c90130d865db22c12c8e52616cc32` | 45056 | `work/ce-extract/UP14XNNI.139/files/boot.hv` |
| `0a91f0606c5890eb2db70abfd752b13226d5b3ea4fbccef1f618f737e333c401` | 196608 | `work/ce-extract/UP14XNNI.139/files/default.hv` |
| `76a44359092ff6a6e2d0de844c2600693a96e88bf21f4a7d25c16aed0237a2cf` | 28672 | `work/ce-extract/UP14XNNI.139/files/user.hv` |
| `8ed85970a7a38e93664b11cc75ad4c0e906aef3e37394e920573a25a241b124a` | 42541568 | `work/ce-extract/G214JLNI.066.nb0` (unmodified builder input) |
| `a6a77b7b414be7f6b8ca60b3c45cd1f48fe2d887b1431f79f9a078e067f25174` | 43192320 | `work/nz-clock/candidate-v1/G214-NZ-candidate.nb0` (**offline unpacked candidate, not a card-ready slot**) |
| `0717a205ddb7555420c24b8f45e094a6db86a88759408c5eb944790c60374f39` | 708 | `work/nz-clock/candidate-v1/payload.bin` |
| `7b51d97568a24e19d56a9407437c0e2b2f27268fa252510f0f969c11bfa18ecb` | 59188 | `work/nz-clock/candidate-v1/payload.elf` |
| `66c60261a01b1b4c91869b97cd2376f7130a92b87615fa2baecce8ba89b1eca3` | 672768 | `work/nz-clock/candidate-v1/extracted/modules/OBJDLL.dll` (analysis PE, no device testing) |
| `redacted` | 16206790656 | `work/nz-clock/backups/20261024T073738Z/card-before-patch.img` (fresh physical-card backup, read-back verified, mode 0444) |
| `5a4d6e640ec723d10e85c32bdaa611b2d4ae6ee384be298c443ddcf7971e4a55` | 42549760 | `work/nz-clock/candidate-v2/G214-NZ-candidate.nb0` (supersedes v1; split final .text page) |
| `0717a205ddb7555420c24b8f45e094a6db86a88759408c5eb944790c60374f39` | 708 | `work/nz-clock/candidate-v2/payload.bin` |
| `7b51d97568a24e19d56a9407437c0e2b2f27268fa252510f0f969c11bfa18ecb` | 59188 | `work/nz-clock/candidate-v2/payload.elf` |
| `38df8cbaaa7f42311478e4da5a86ec69c07a0909c950bf2ad36f98e8c1d5765b` | 672768 | `work/nz-clock/candidate-v2/extracted/modules/OBJDLL.dll` (analysis PE) |
| `b32441b1f42707348bfac2b273fcd983ff54488bf77e3886ac100bf25a07db70` | 30708224 | `work/nz-clock/packed-v2-reviewed/G214-NZ-EXPERIMENTAL-slot.bin` (known sums/round trip verified; unknown header fields preserved; on-card boot tested with no clock change, hook execution unproven — §7/§14) |
| `8c9edf0086e71f94cabcd23b360e73c91bd0d950b8b84e5ae4822dc0e3aa98e3` | 30737920 | `work/nz-clock/writes/20261024T084550Z/G214-before-write.bin` (original G214 range saved before successful experimental write; mode 0444) |
| `7ba3020cf90bb644701989e3e9375c17355374c7531a4b35071635c78fa44b82` | 42541568 | `work/nz-clock/probe-fixed-nzdt-v1/G214-fixed-NZDT-PROBE.nb0` (temporary fixed UTC+13 baseline, no automatic DST; two in-place instructions) |
| `a232889da7e317b5a1c749008dcd72a02131e478379994c75b0216c9ce07078d` | 30700032 | `work/nz-clock/probe-fixed-nzdt-v1-packed/G214-NZ-EXPERIMENTAL-slot.bin` (temporary fixed UTC+13 diagnostic; unknown header fields preserved) |
| `18fe13ef2d8f66673db632b863c4ba32922c48f82e7cfeb76f96ca34c1eda876` | 30737920 | `work/nz-clock/writes/20261025T002153Z/G214-before-write.bin` (previous v2 range saved before fixed +13 installation; mode 0444; subsequent probe test reported unchanged clock, see 08 §8.1) |
| `23daf413d9ce7b3e37f1b223b61de674228e66ffaf2fa7994a9ca7b84d69dd29` | 671744 | `work/nz-clock/probe-fixed-nzdt-v1/extracted/modules/OBJDLL.dll` (diagnostic analysis PE; ARM disassembly reviewed) |
| `redacted` | 317440 | `work/nz-clock/saved-zone-writes/20261024T100911Z/nav-pair-before.bin` (verified read-only snapshot before saved-zone write; contains private data, never publish) |
| `redacted` | 317440 | `work/nz-clock/saved-zone-writes/20261024T100911Z/nav-pair-fixed-plus13.bin` (complete candidate matched subsequent raw-card read; contains private data, never publish) |
| `73cd5b94337cbbe53134d686047c484c67a3ddd7a69d1dc6d36e248e2412f9d5` | 172032 | `work/ce-extract/G214JLNI.066-HMI/modules/NaviGuideCC.dll` (GPS direction-property metadata) |
| `2df489010f81a6b39373cae0dea7f2f8985a572bd48577d5741e1b5d0729efde` | 369152 | `work/ce-extract/G214JLNI.066-HMI/modules/DiagnosisCC.dll` (GPS/sensor renderers with owner-page binding unproven) |
| `ec1138c812d5bc111ad30d2e8937b0657be1f8092f832cefb67a83916bfa192b` | 20025376 | `work/hour-offset-ui/build-v1/substance.skn` (`6a54198a` + 11-byte hour row, #29; findings 12 §7) |
| `f255f86933cb2c83426bca395f74d3af8cea9bd9c7e5d330c1d6db0648f6d9a0` | 20025376 | `work/hour-offset-ui/build-v2-dst/substance.skn` (v1 hour row + 5-byte DST toggle, #29; findings 12 §8) |
