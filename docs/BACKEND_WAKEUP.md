# Backend wake-up recovery

Recovery runs on frontend startup. If Orb is already marked unavailable,
window focus or an online event can start another recovery window. Concurrent
callers share the existing recovery task. Before a new analysis, the existing
readiness recheck can mark the service unavailable and restart recovery. There
is no periodic background keep-alive, and a focused ready page does not probe
just because it was idle.

## Timing policy

| Check | Before | Now |
| --- | --- | --- |
| Lightweight `/api/health` timeout | 15 seconds | 5 seconds |
| Pause after a failed health probe completes | 2 seconds | 1 second |
| `/api/ready` timeout | 15 seconds | 15 seconds |
| `/api/upload-ping` timeout | 15 seconds | 15 seconds |
| Pause after unsuccessful full verification | 2 seconds | 5 seconds |
| Overall recovery window | 100 seconds, checked between requests | 100 seconds, also bounds requests and delays |

Only a successful health response starts full readiness verification. Upload
verification runs only after readiness succeeds. The existing 204 success and
404/405 canary compatibility behavior are retained. Explicit AI/credit
configuration-unavailable health states retain their existing messages.

Each request is awaited before the next starts. Timeouts abort the current
request; Promise racing also prevents late responses from resuming an expired
attempt. Timeout coverage includes health/readiness response-body parsing.
Full checks keep their 15-second allowance unless less than 15 seconds remains
in the overall recovery window. The deadline uses a monotonic clock.

There is no attempt-count cutoff: transient latency can use the whole window.
With immediate failed health responses, the maximum is 100 health probes in
one window (one per second), with no readiness/canary calls. With continuously
stalled health requests, the maximum is 17 requests in 100 seconds. Requests
stop immediately after full verification succeeds. If health is available but
full verification fails immediately, full checks are limited to one sequence
per five seconds, not once per second. Thus the increased frequency applies
only to lightweight health probes during recovery, not steady-state traffic.

Wallet credit-config recovery remains separate and unchanged. Recovery does
not submit media, create an AI job, or reserve/consume credits.

## Validation

Fake-clock tests cover an awake backend; wake-up after 5, 20 and 60 seconds;
network errors; sequential probes; 5-second health and 15-second verification
timeouts; verification cooldowns; stale responses; the complete 100-second
window and final request cutoff. Application integration tests cover shared
focus/online recovery, disabled processing until canary success, independent
credit configuration and verification responses taking longer than 5 seconds.

These are deterministic local simulations, not production cold-start
benchmarks. No infrastructure, provider, wallet, payment or database changes
are involved.

Final validation: 215 frontend tests passed; 319 backend tests passed with
8 expected real-Postgres skips; guarded production build passed. An unchanged
backend test missed its 10-second job-error wait in the initial run, then
passed in isolation and in the full rerun without weakening its assertion.
