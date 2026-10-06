# Safe video performance Phase 1

## Dependency graph and scope

The scene prompt uses only video metadata, that scene's start/end/index and its
sampled frames. It does not consume another scene's analysis. Those calls now
run with **at most two outstanding calls**, including each call's existing
retry loop. A freed slot is refilled on completion, without queuing all scenes.
Each thread receives a separate copied ContextVar context for job timing.

FFmpeg extraction remains sequential. Scene frames are prepared before the
scene-provider phase. Results are stored by original scene position and saved
in that order, regardless of completion order. Global analysis still consumes
the ordered scene descriptions and therefore is **not independent**; it runs
after all scene analyses. Compose synthesis still consumes the completed report
and runs last. Image and Enhance provider behavior is unchanged.

No scene threshold, scene boundaries, sampling timestamps/counts, image
dimensions, JPEG quality, FFmpeg arguments/timeouts, model, prompt, provider
retry policy, job-worker count, payment or database settings changed.

## Probe reuse

Orb's visual upload validation previously probed the source, discarded the
metadata, then the pipeline probed it again. The handler now passes its internal
`ValidatedVideo` record into the pipeline. Reuse requires the same resolved
path, device/inode, size and nanosecond modification/change timestamps captured
before and after the original authoritative probe. Changed/missing/different
files fall back to the existing probe and its validation/errors. No frontend
metadata is trusted. Unchanged Orb video uploads use one FFprobe instead of two.
Standalone pipeline calls without validated metadata still perform a probe.

## Exact seek reuse

The existing FFmpeg seek is `f"{timestamp:.3f}"`. That exact string is the
canonical key, together with source path, image format and quality. No nearby
seek strings are merged. Raw sample timestamps, indices, order, filenames and
all evidence entries remain unchanged. Reused bytes are copied to the original
expected destination so existing artifacts and DTOs still work. The cache holds
paths rather than media buffers and is fresh for each pipeline run.

Fixture inspection:

| Fixture / existing sampling configuration | Scene entries | Global entries | Duplicate canonical seeks |
| --- | ---: | ---: | ---: |
| Four-second synthetic, default eight global frames | 2 | 8 | 0 |
| Four-second two-cut fixture, default eight global frames | 4 | 8 | 0 |
| Same two-cut fixture, existing four-global-frame configuration | 4 | 4 | 4 |

The last case shares `0.500`, `1.500`, `2.500`, `3.500` between scene/global
sampling. It retains eight frame entries but extracts four unique frames.
Production sampling configuration was not changed to produce this case.

## Failure, cancellation and credit safety

On a scene failure, no replacements are dispatched after the failure is
observed. Pending futures are cancelled where possible; already-running SDK
calls are joined before the job may clean up source frames or settle/release
its reservation. Synchronous SDK calls cannot be forcibly interrupted; their
existing timeout/retry bounds remain in force. Some independent calls may have
already started before another call's failure becomes known.

Scene threads perform only analysis: they never reserve credits, persist durable
job results or settle the ledger. The existing single job worker still reserves
once, saves the completed durable result once, and settles once. Existing
status/result recovery may repeat an idempotent settlement call during a race;
the ledger still consumes exactly one credit. A failed job restores its credit.
Duplicate submissions still return the existing job without another provider
operation or consumption. UI cancellation behavior remains unchanged.

## Instrumentation

All previous events/fields remain. Added:

- `peak_ai_concurrency`: observed peak overlapping SDK calls.
- `sequential_ai_sum_ms`: summed SDK durations, alias of `ai_total_ms`.
- `scene_ai_wall_ms`: elapsed bounded scene-provider phase; excludes extraction
  and ordered artifact writes, includes retries and thread scheduling/join.
- `unique_extracted_frames` and `frame_cache_hits`: actual extractions versus
  reused entries. Existing `frames` continues counting evidence entries.

Overlapping call durations must not be summed as elapsed processing time.
Provider rate limits can still trigger the unchanged retry policy; local mock
speedups are not a prediction of production Gemini latency.

## Repeatable local checks

With FFmpeg/FFprobe available and no opt-in external test database configured:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -s tests/test_video_phase1.py
```

This uses only generated media, fake provider responses/delays, disposable
SQLite ledgers and generated test-wallet signatures. It verifies 1/2/12 scenes,
peak two calls, out-of-order completion with ordered assembly, unchanged prompt
instructions/frame hashes/results, retry/error/timeout/interruption behavior,
probe identity guards and credit consumption/release/idempotency.

The benchmark tests print `PHASE1_BENCHMARK` JSON for default generated
fixtures and the existing four-frame configuration. Both paths include the
authoritative validation probe. The reference uses the pre-Phase-1 serial
scene algorithm and a second pipeline probe. Provider delays are artificial:
500 ms per scene and 250 ms global. No live Gemini call is made. Local totals
include filesystem writes and FFmpeg; host load can affect them.

## Measured local comparison (2026-10-06)

Final isolated benchmark run, real local FFmpeg/FFprobe with the artificial
provider delays above:

| Fixture / global frames | Total before → after | Probes | FFmpeg launches | Evidence entries | AI calls | Peak AI calls |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic / 8 | 1924.7 → 1853.9 ms | 2 → 1 | 11 → 11 | 10 → 10 | 2 → 2 | 1 → 1 |
| Two-cut / 8 | 2515.6 → 1935.8 ms | 2 → 1 | 13 → 13 | 12 → 12 | 3 → 3 | 1 → 2 |
| Two-cut / 4 | 2224.2 → 1207.1 ms | 2 → 1 | 9 → 5 | 8 → 8 | 3 → 3 | 1 → 2 |

Four independent 500 ms calls took 2190.2 ms sequentially versus 1129.7 ms
with the bounded pool, including local preparation/artifact writes. The parallel
AI phase itself took 1022.4 ms. Full backend validation: 309 passed, 8 expected
opt-in real-Postgres skips. Frontend: all 192 passed using one test-runner worker
after an initial Windows fork startup timeout; no frontend/config changes.
Guarded production build passed with a safe placeholder HTTPS API origin.
These are local mock-provider measurements, not production/live AI claims.
