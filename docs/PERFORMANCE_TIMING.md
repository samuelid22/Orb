# Orb performance timing

This adds observations only. It does not tune media processing, prompts, models,
retry delays, workers, wallet authentication, prices, payments, or storage.
No new database tables, API fields, response headers, or infrastructure settings
are required. Timings use Python `perf_counter` and browser `performance.now`.

## Backend events

The `uvicorn.error.orb_perf` logger uses Uvicorn's existing log handling. Each
message is an event name followed by compact JSON:

- `orb_perf`: request arrival, worker start, individual AI SDK calls, retry waits.
- `orb_perf_request`: HTTP acceptance/failure, body receive and parsing timings.
- `orb_perf_summary`: one final summary per worker, including failed jobs.
  Reused idempotent requests have `status: "reused"` and do not start a worker.

Correlate events with the generated `request_id` and `job_id`. Early request
arrival uses `decode_visual` / `compose_visual` until validated media determines
`decode_image`, `decode_video`, `compose_image`, or `compose_video`. Text uses
`enhance`. Filenames, addresses, signatures, hashes of user media, transaction
payloads, prompts, image/frame bytes, model payloads, and credentials are never
included in these new events. Labels and numeric metric keys are allowlisted.

### Timing fields

All `_ms` values are milliseconds. Stage durations accumulate across repeated
calls within the same request/job. Dimensions/duration are gauges, so a second
probe does not double them.

| Metric | Boundary |
| --- | --- |
| `request_ms` | Application ASGI entry to HTTP response completion |
| `multipart_receive_parse_ms` | ASGI entry to visual handler entry, including receive, framework multipart parsing/spooling and dispatch |
| `request_parse_ms` | Corresponding boundary for Enhance JSON |
| `upload_receive_ms` | Time awaiting ASGI receive messages; body is forwarded unchanged |
| `upload_save_ms` | Existing chunked UploadFile read and destination write |
| `authorization_ms` | Existing local/public authorization and signed session check |
| `file_validation_ms` | Existing image verification or video validation probe |
| `file_hash_ms` | Existing paid-media fingerprint, or Enhance request fingerprint; zero when skipped |
| `job_creation_ms` | Existing in-memory job creation |
| `credit_reservation_ms` | Existing reservation boundary; `paid: 0` indicates local bypass, not an actual credit reservation |
| `queue_ms` | Submission after reservation to actual worker entry |
| `worker_start_ms` | Request arrival to worker entry |
| `processing_ms` | Worker entry to completion, including existing cleanup |
| `ffprobe_ms` | All existing probes including metadata parsing |
| `ffprobe_process_ms` | FFprobe subprocess execution only |
| `scene_detection_ms` | Existing scene-cut detection and result parsing |
| `frame_extraction_ms` | Aggregate existing extraction calls and output checks |
| `ffmpeg_ms` | Aggregate scene-detection and frame-extraction subprocess execution |
| `frame_serialization_ms` | Local frame/image reads and SDK parts or explicit base64 preparation |
| `ai_total_ms`, `ai_longest_ms` | Sum and maximum of SDK provider call durations |
| `ai_success_average_ms` | Average SDK duration for calls that returned without an exception |
| `ai_retry_wait_ms` | Actual elapsed existing Orb retry sleeps |
| `response_parsing_ms` | JSON decoding and Gemini text extraction |
| `response_validation_ms` | Existing response schema/content validation boundary, including parsing within that boundary |
| `artifact_persistence_ms` | Existing pipeline manifest, analysis, scene and prompt writes |
| `result_assembly_ms` | Existing local source-media copy |
| `result_persistence_ms` | Existing durable result save (Postgres in production, existing local storage in development) |
| `credit_settlement_ms` | Existing consume/release call, including failed-job release |
| `cleanup_ms` | Existing visual worker source/temp cleanup |
| `total_ms` | Application request arrival to worker completion |

Summary counters include input bytes, received multipart bytes/chunks, dimensions,
video duration in seconds, scenes, scene/global/total extracted frames, FFmpeg
and FFprobe launch attempts, SDK AI calls, retries, and whether the operation
used the paid boundary. Failed process launches are counted as attempts.
AI/retry counts are explicit zeros when no call/retry occurred.

**Do not add all stage columns to get total time.** Several are nested:
validation includes its initial FFprobe; extraction includes FFmpeg; response
validation includes JSON parsing. Request receive/parse includes network waits
observable inside the app, not time spent in a browser or a proxy before ASGI.
SDK construction/imports and other unlabelled work remain included in total
processing time. Startup/cold-start delay before the app receives a request
must be compared with frontend diagnostics, not inferred from backend totals.

For AI calls, events include `sequence`, `purpose`, `attempt` (one-based),
`duration_ms`, and `success`. Purposes are scene/global/image analysis,
compose synthesis, and Enhance. Success means the SDK returned; subsequent
output validation can still fail and cause the existing retry. A retry event
includes its planned delay; the summary records actual wait duration. SDK
internal HTTP retries/serialization are inside SDK call duration and are not
separately observable here. No SDK hooks or retry policy changes were added.

Thread-local ContextVars are explicitly rebound to each worker's timing record;
the single-worker FIFO, reservation order and public job payload are unchanged.
Timing is not recovery state and is not stored in the ledger. Logger failures
are swallowed by the observer, never by the existing operation/settlement code.
Request timing can arrive after the summary for an extremely fast job; use its
separate request event in that case. A killed process may lack a final summary;
request/worker-start and prior AI events remain useful.

## Frontend diagnostics

Development builds enable content-free console events. Production is quiet by
default. To opt in locally in a browser tab:

```javascript
sessionStorage.setItem("orb-perf", "1");
// Reload to also capture initial service startup. Run an analysis normally.
```

Disable with `sessionStorage.removeItem("orb-perf")` and reload. This is a
browser-only diagnostic flag, not a payment/authentication flag.

- `orb_perf_service`: the existing readiness/wakeup sequence before interaction.
- `orb_perf_frontend`: readability completion, readiness wait, upload/request
  start/return/duration, job-ID availability, poll count/request duration/actual
  scheduled wait, first result detection, retrieval/display, and click-to-result.

No visible debug UI, new requests, retries, or changed poll intervals are added.
Timings remain in memory; a page reload cannot reconstruct the original click
timestamp. Same-page session recovery retains the timer, including the time
spent reauthenticating. Leaving the flow ends that frontend observation; it does
not cancel or change the backend job. Poll waits are measured browser scheduling
time, not an exact server-completion-to-next-poll delay. Client and server
monotonic timestamps are not interchangeable across machines.

## Local validation example (2026-10-06)

Generated four-second 320×240 video, 144770 source bytes; real local FFprobe /
FFmpeg, mocked Gemini SDK transport, SQLite/local bypass. This was run during
other validation, not as an isolated production benchmark.

```text
orb_perf_summary {"operation":"decode_video","status":"complete","paid":0,"total_ms":2831.015,"queue_ms":0.993,"processing_ms":2749.417,"ffprobe_launches":2,"ffprobe_ms":141.557,"scene_count":1,"frames":10,"scene_frames":2,"global_frames":8,"ffmpeg_launches":11,"ffmpeg_ms":1654.852,"scene_detection_ms":193.070,"frame_extraction_ms":1465.902,"frame_serialization_ms":5.632,"ai_calls":2,"ai_retries":0,"ai_total_ms":31.997,"result_persistence_ms":98.774}
```

This shortened example omits IDs and other numeric fields. AI timings are mock
transport timings, **not Gemini latency**. Do not extrapolate this small local
video's timings to production media or Render resources.

Repeat with FFmpeg/FFprobe available, using the existing test environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q 'tests/test_orb_performance.py::test_real_video_tools_with_mocked_ai_have_exact_counts[decode]' --log-cli-level=INFO
```

The entire instrumentation suite is `tests/test_orb_performance.py`; it also
checks image Decode/Compose, video Compose, Enhance, retries, failed uploads/jobs,
deterministic queue isolation, content exclusion, unchanged result payloads,
real signed disposable wallet sessions, mocked purchases, credit settlement /
release / idempotency, and logger failure. It never needs live AI or a production
database. `web/performance.test.js` and `web/app.test.js` cover browser timing.

A five-round local microbenchmark (10000 iterations/round, median, during other
validation) measured about **10.4 μs** per timer-plus-numeric-metric observation
and **58.1 μs** per AI JSON log event; the empty-loop baseline was 0.094 μs.
A NullHandler excluded real log-output I/O. Observer overhead is measurable but
small at these boundaries; production logging I/O and end-to-end overhead have
not been benchmarked. No paid/live Gemini calls were made.
