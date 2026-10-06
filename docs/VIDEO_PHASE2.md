# Video performance Phase 2 — command profile and experiment gate

## Current commands (recorded before any production changes)

Scene detection:

```text
ffmpeg -nostdin -i SOURCE -vf "select='gt(scene,0.3)',showinfo" -f null -
```

Each unique extraction seek:

```text
ffmpeg -nostdin -loglevel error -y -ss TIMESTAMP_3DP -i SOURCE -frames:v 1 -q:v 2 DESTINATION.jpg
```

Threshold and quality come from existing config; these show default values.
There is no explicit decoder/encoder, map, audio/subtitle/data suppression,
thread count or sync flag. FFmpeg auto-selects streams/codecs and sync behavior.
JPEG output selects the MJPEG encoder, original dimensions and q:v 2.
The scene detector outputs selected video frames to the null muxer but may also
decode/transcode automatically selected audio. Extraction's image muxer does
not output audio; it still opens the container normally. No subtitle/data
output is requested by the image/null muxers. Scene comparison processes every
video frame at native dimensions, then existing code parses/deduplicates cuts.

Extraction uses input-side -ss (before -i), with default accurate-seek decoding
and discard after the preceding seek point; it is not a packet-only seek. Each
unique canonical seek launches a fresh process. Phase 1 reuses exact duplicate
seeks. The supplied long-video metrics have 32 unique frames: one scene
detection process plus 32 extraction processes equals 33 FFmpeg launches.

Experiments must retain the exact canonical requested seeks, original evidence
entries/order, dimensions and JPEG quality. Batch outputs must be matched to
actual source frame timestamps and baseline image hashes/pixels. Output-side
seeking and stream/thread flags are alternatives to measure, not assumptions.

No production change is approved by a local experiment alone: frame equivalence
and at least 20% medium/long extraction wall-time benefit without a serious
short regression are required. AI concurrency stays two, global/Compose stay
dependent/sequential, and payment/ledger behavior is outside this experiment.

FFmpeg's documented seek semantics: [input/output -ss and accurate seeking](https://ffmpeg.org/ffmpeg.html).
Filter behavior: [select and frame timestamps](https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect).

## Generated sources and measurement method

Experiments use local FFmpeg 9.0.1 (Windows), moving testsrc2 visuals and generated
AAC sine audio. H.264 yuv420p, 24 fps, two-second GOP, ultrafast/crf 20 generation
is consistent across strategies; extraction still uses original dimensions and
q:v 2. Hard visual changes give two short scenes and twelve long scenes. The
vertical source has one scene. Nominal durations are approximately 17.23 s,
30.09 s and 120.117 s; CFR muxing rounds actual duration to the frame grid.
These are generated fixtures, not copies of the production uploads.

The baseline diagnostic command adds only `-benchmark`, info logging and a
pass-through showinfo filter. A separate run of the original unmodified
production extract_frame function confirmed all 54 baseline JPEGs match that
diagnostic baseline byte-for-byte. showinfo reports source checksums/PTS; Pillow
compares JPEG bytes, dimensions, RGB MAE and PSNR. The batch uses the same
canonical millisecond seeks and selects the first decoded frame at/after each,
with prev_pts preventing later frames from satisfying the same seek. Original
evidence ordering is rebuilt from the requested scene/global list.

All default requested scene/global seeks, frame dimensions and per-entry
comparisons are saved in [the generated-fixture equivalence CSV](VIDEO_PHASE2_FRAME_EQUIVALENCE.csv).
No source media, user prompts, credentials or private production data are saved
in documentation. Large generated media/images and raw reports remain ignored
under output/. No AI provider is used.

### Extraction alternatives

- Baseline: accurate input-side seek and one process per unique frame.
- Single batch: one full sequential decode, select all canonical seeks, VFR image
  output, same q:v 2. No downscaling, new FPS, frame skipping or scene changes.
- Two batches: same selector separately for scene and global requests; may
  decode the source twice.
- No-audio flags: original seek plus -an/-sn/-dn.
- Threads 1/2: original seek, explicit decoder threads and no-audio flags; output
  JPEG quality/encoder defaults remain unchanged.
- Output-side seek: -ss after -i; decoding from the start rather than indexed
  seeking. It produced identical JPEGs but was substantially slower.

## Default CPU benchmark

All values below are wall milliseconds. No FFmpeg subprocesses were run
concurrently within an extraction strategy.

| Source | Frames | Baseline | Single batch | Two batches | No-audio | Decoder threads 1 | Decoder threads 2 | Output seek |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ~17 s / 1024x576 | 12 | 1791.7 | 550.1 | 1318.1 | 1458.8 | 1736.3 | 1831.0 | 8058.3 |
| ~30 s / 720x1564 | 10 | 1506.1 | 1047.6 | 2140.0 | 1835.2 | 2030.0 | 2052.3 | 20022.9 |
| ~120 s / 1280x720 | 32 | 4088.2 | 2896.8 | 5743.7 | 5326.3 | 4933.3 | 4039.8 | 177662.9 |

Baseline versus single-batch CPU milliseconds:

| Source | Baseline CPU | Single-batch CPU | Two-batch CPU |
| --- | ---: | ---: | ---: |
| Short | 1159 | 765 | 1734 |
| Vertical | 1625 | 2766 | 5359 |
| Long | 4287 | 8282 | 17656 |

On this multicore workstation single-batch wall time improves about 31% on
medium and 29% on long media, but CPU work increases 70% and 93% respectively.
Sequential decoding through all requested timestamps can cost much more CPU
than separate indexed seeks to nearby keyframes. Two full passes are worse.

## Local one-CPU safety check

Only the benchmark Python process and its children were affinity-limited to one
CPU. No system-wide affinity, application runtime, infrastructure or production
setting was changed. This is a CPU-budget sensitivity check, not a Render
replica. Final medium/long check ran after the default benchmark finished.

| Source | Baseline wall | Single batch wall | Two batch wall | Baseline CPU | Single batch CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short | 2400.2 | 1196.6 | 1691.6 | 797 | 719 |
| Vertical | 2428.5 | 5439.7 | 4792.9 | 985 | 2562 |
| Long | 7105.2 | 8964.2 | 12125.3 | 2630 | 6140 |

The single batch regresses about 124% on vertical and 26% on long media; two
batches regress about 97% and 71%. This fails a clearly superior, low-risk
medium/long performance gate for a CPU-constrained service. Results depend on
keyframe spacing, source codec and host CPU scheduling; production source GOP
and Render's actual decoding budget were not inspected or altered.

## Scene detection benchmark

The algorithm, threshold and native-resolution full-frame comparisons are
identical for all candidates. All three fixtures returned identical cut lists
for all variants (the same empty list for the one-scene source).

| Source | Baseline | -an/-sn/-dn | Video map + suppression | Decoder/filter threads 1 | Decoder/filter threads 2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short | 818.9 | 394.8 | 603.9 | 1189.7 | 484.4 |
| Vertical | 986.5 | 1059.8 | 918.9 | 2139.9 | 1454.0 |
| Long | 2925.7 | 2707.2 | 2804.2 | 5275.0 | 3375.5 |

Suppressing audio reduces unrelated work, but wall benefits were inconsistent.
One-CPU no-audio runs were 548.9 / 1888.9 / 6703.8 ms versus 599.6 / 2069.7 /
8744.0 ms baseline; the short run came from the first constrained check.
No candidate showed a consistent large speedup in both host configurations.
Forcing `-map 0:v:0` is also unsafe as a universal replacement: automatic stream
selection may choose a different stream in multi-video sources. It is not adopted.

## Equivalence, overhead and decision

- All 54 representative evidence entries match JPEG bytes for single/two batch,
  stream-suppression, decoder-thread and output-seek variants. MAE is zero;
  identical-pixel PSNR is infinite (represented as null in raw JSON).
- Batch/suppression/thread variants also match decoded source checksums and
  dimensions. Rebased showinfo timestamps differ at most 0.0384 ms from native
  batch PTS because of seek/time-base conversion and printed precision; this
  is not a different selected frame. No nearby requested seeks are merged.
- Generated VFR and odd/overlapping seek tests also produce identical baseline
  JPEGs and source checksums. Output-seek's emitted PTS is not independently
  exposed by the pre-output showinfo filter; its equivalence is supported by
  identical JPEG bytes, not a fabricated emitted timestamp.
- Bare process startup (`ffmpeg -version`, median of five) was 51.949 ms on the
  default workstation. Long baseline FFmpeg-reported processing wall sums to
  1726 ms versus 4088.2 ms Python-observed wall; that gap includes process/init /
  shutdown and other work outside FFmpeg's timer, not solely OS launch cost.
  Version startup and generation/decoding workloads are different measurements.
  No production startup overhead is inferred from these local figures.
- Extraction launches are baseline 12/10/32, one batch 1/1/1, two batches 2/2/2;
  adding detection gives long-video totals 33 / 2 / 3. Fewer launches do not
  guarantee lower CPU consumption or better constrained-host wall time.

**No production strategy is selected.** Existing extraction/detection commands,
33 launches for the supplied 32-frame job, Phase 1 behavior and orb_perf fields
remain unchanged. No production speedup is claimed. Experiments, tests and
documentation were initially kept uncommitted pending user approval; no
production optimization or deployment is part of this work.

## Repeat locally

```powershell
.\.venv\Scripts\python.exe -B scripts/benchmark-video-phase2.py
.\.venv\Scripts\python.exe -B scripts/benchmark-video-phase2.py --fixtures medium long --variants single_batch two_batch --one-cpu --fixture-dir output/video-phase2 --output output/video-phase2-onecpu
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_video_phase2_experiments.py
```

The CLI refuses output outside Orb/output, and batch failure removes only its
experimental destination. One-CPU affinity is restored by process exit. No
production provider, database or blockchain credentials are needed. Benchmark
output records strategy, process count, wall/CPU time, source PTS, dimensions,
ordering and objective image equivalence; production diagnostics are unchanged.

## Initial validation and remaining limits

- Full backend suite: **319 passed, 8 expected opt-in real-Postgres skips**;
  142 existing FastAPI deprecation warnings. This includes ten new local
  experiment tests and the existing Phase 1, payment and idempotency coverage.
- Full frontend suite, executed twice with one Vitest worker: **191 passed,
  1 failed** each time. The unchanged test
  `web/wallet.test.js:585`, `rejects quotes for another method before wallet
  approval (usdg)`, expected `wrong payment method` but received
  `3 testnet credits added.` Both method variants passed when run in isolation
  (2 passed, 57 deselected). The test uses six timer turns to await connection
  before clicking a method; selection is ignored while wallet state is busy.
  This suggests test timing/order sensitivity, but the exact full-suite cause
  is not established. No wallet code or tests were changed to hide the failure.
- Guarded production frontend build: **passed** with the safe placeholder
  `VITE_API_BASE_URL=https://orb-api.example.invalid`.
- No application source, frontend source, payment code, database logic or
  production settings changed. No live Gemini or production service calls.
  Main remains at `a722bbb936b97990865c14f4bc17a3a52f6a7b2a`; no commit, push
  or deployment was performed.

Actual production codec/GOP, deployed FFmpeg build and CPU quota were not
benchmarked. One-CPU affinity is a sensitivity check, not a Render replica.
An adaptive extraction proposal would need those measurements and independent
equivalence/performance tests before adoption. No adaptive strategy is added
here. The unrelated frontend failure was subsequently resolved as described below.

### Follow-up validation and documentation commit

The wallet test failure was traced to the intentional preview-config failure
test leaving a real retry timer alive. That older instance could replace a
later test's payment buttons using the later fetch mock and document. This was
test isolation leakage, not a production cross-method payment bypass.

Commit `97568fac4714cfd30d0d236ffbf293de1415197a` changes only
`web/wallet.test.js`: fake timers own the intentional retry, teardown clears
them before restoring real timers, and cross-method tests explicitly await
authentication and assert selection/rejection. The three affected cases passed
ten executions each; all 59 wallet tests and all **192 frontend tests passed**.
The complete backend suite passed **319 tests with 8 expected skips**; the
guarded production build passed with the safe placeholder HTTPS API origin.

The user subsequently authorized committing and pushing these benchmark
artifacts separately. Production extraction remains unchanged; no performance
optimization or deployment is authorized by this documentation commit.
