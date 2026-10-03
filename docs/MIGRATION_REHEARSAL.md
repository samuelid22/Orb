# USDG migration rehearsal — disposable populated Postgres

Run date: 2026-10-03. Branch: `usdg-test`; application revision:
`a24a618ee0694e56e1528e0d6d3a434b163f7f6d`.
No production database, hosted service, wallet, or real payment was accessed.
Application/migration/business logic is unchanged by this rehearsal.

## Repeat the rehearsal

Use the existing Orb Python environment with `requirements.txt` installed and
portable PostgreSQL binaries available. This run used official EDB PostgreSQL
17.11 Windows binaries, downloaded from
https://www.enterprisedb.com/download-postgresql-binaries.
The optional runner uses `cryptography` to issue its disposable TLS certificate;
it is already available through the development environment. No new production
dependency is introduced.

```powershell
# Default portable binary location is ignored api_output/migration_rehearsal_runtime/pgsql/bin.
.\.venv\Scripts\python.exe scripts/run-postgres-rehearsal.py

# All backend tests, INCLUDING eight real-Postgres integration cases:
.\.venv\Scripts\python.exe scripts/run-postgres-rehearsal.py --full-suite

# Or specify a different installed/portable bin directory:
.\.venv\Scripts\python.exe scripts/run-postgres-rehearsal.py --bin-dir 'C:\path\to\pgsql\bin'
```

The runner creates a new cluster bound only to `127.0.0.1` on a random high port.
TLS is enabled; local trust authentication applies only to this synthetic,
loopback-only cluster. It never loads `.env`, and strips inherited Orb,
Prometheus, Postgres, and AI credential variables. Tests require the owned
cluster's unique marker before creating any databases; cloud connection URLs
are refused. Each test uses a separate database, then drops only that database.
The owned server stops in `finally`; no Windows service is installed.
Initialization uses `initdb --no-sync` for disposable setup only; normal server
WAL/fsync durability remains enabled.

Default `pytest` skips these eight integration cases when the owned cluster is
not configured. Use the runner for actual Postgres validation, not a production
`ORB_DATABASE_URL`. RPC is mocked, and no AI provider request is made.

## Synthetic pre-migration ledger

The eight core tables are created from `POSTGRES_SCHEMA_V1`, with the exact
version-1 schema marker. Records simulate two authenticated wallets, used
challenges, native test-ETH purchases, one unpaid quote, successful/released
operations, and interrupted jobs with/without a durable result. No production
data is copied. Tokens and wallet addresses are synthetic fixtures.

| Existing table | Before | After migration |
| --- | ---: | ---: |
| schema_versions | 1 | 1 |
| challenges | 2 | 2 |
| sessions | 2 | 2 |
| balances | 2 | 2 |
| quotes | 4 | 4 |
| purchases | 3 | 3 |
| reservations | 6 | 6 |
| results | 4 | 4 |

Wallet A starts with granted=10, consumed=2, reserved=2, available=6.
Wallet B starts with granted=3, consumed=1, reserved=0, available=2.
Native purchases total 5+5 credits for A and 3 for B. Core version is 1.

## Actual CLI results

| Command/stage | Exit | Database effect |
| --- | ---: | --- |
| `--check` before migration | 2 | None; migration required |
| Explicit migration | 0 | Two additive USDG tables plus version-1 marker |
| `--check` after migration | 0 | None; ready |
| Repeat migration | 0 | None; already ready |
| Final `--dry-run` / check | 0 | None; ready |

Every existing table's row values, counts, column definitions, constraints,
indexes, relation OID/filenode, and row `ctid`/`xmin` are identical after the
migration. Thus balances, sessions, native quotes/purchases, job reservations,
results, and the original schema marker were neither updated nor rewritten.
No reservation settlement/release or startup reconciliation happens in the CLI.

`orb.usdg_quotes` has the expected eight columns, quote primary/foreign key,
chain 421614/decimals 6/positive amount/nonnegative block checks, and primary-key
index. It contains zero rows immediately after migration.
`orb.usdg_schema_versions` contains exactly one version=1 marker.

## Failure and concurrency safety

On five separate populated disposable databases, both check and apply returned
1 and preserved the deliberately altered starting state:

- Partial USDG schema (only one extension table).
- Incompatible core shape (unexpected quote column).
- Incorrect core column type (session expiry changed to text).
- Missing required core table (results).
- Unsupported extension version (marker changed to 2 after removing its v1
  check constraint). This violates the extension integrity/version contract and
  is refused before any DDL; version 2 cannot exist under the valid v1 check.

A separate test injects a DDL failure when the version-marker table is created,
AFTER the quote table DDL. The command returns 1 and the first table is rolled
back too: no partial commit or change to the populated core survives.

Two concurrent explicit migration processes both succeed; advisory locking
produces one extension installation and one already-ready response. Exactly
one version marker exists and every original core record remains identical.

## Application startup after migration

The real FastAPI application runs its ASGI startup through TestClient, using
production paid-mode guards, the migrated Postgres ledger, dual payment methods,
synthetic sessions, mock RPC, and a non-secret AI placeholder. This is local
application integration, not hosted deployment or live Gemini/payment testing.

Verified: health 200; credit config enabled with `native_eth` and `usdg`;
existing session authenticates; original native purchase verification is
idempotent; USDG three-credit quote is exactly 300000 base units and zero native
transaction value; the completed durable job result is recoverable.

Startup intentionally runs EXISTING restart reconciliation, unlike migration:

- Reserved job WITH a completed durable result becomes consumed exactly once.
- Interrupted reserved job WITHOUT a result becomes released exactly once.
- Wallet A becomes granted=10, consumed=3, reserved=0, available=7.
- Wallet B remains unchanged.
- Completed/released reservations, sessions, native records, and results remain
  intact; all original table row counts remain unchanged.
- A second application startup causes no further change or charge.

This is expected recovery behavior, not a migration side effect. The backend's
startup/recovery implementation was not changed.

## Saved evidence

Each run saves ignored JSON evidence under
`api_output/migration_rehearsal_runtime/<run-id>/reports/`:
`pre_migration`, `post_migration`, `migration_commands`, `application_startup`,
five `failure_*` reports, `atomic_rollback`, and `concurrent_migrations`.
Snapshots include full synthetic records and schema/physical-row comparisons;
no real session token, database credential, or API key is included. Portable
binaries, TLS keys, runtime clusters, and raw reports remain ignored.

The focused rehearsal passed all eight integration tests on PostgreSQL 17.11
with TLS. The full backend suite passed **261 tests**, including those eight
real-Postgres cases (112 existing FastAPI deprecation warnings). Frontend:
**59 tests passed** across four files. The guarded staging production build
passed with VITE_API_BASE_URL set to a non-routable HTTPS placeholder and
VITE_ORB_DEPLOYMENT_TARGET=usdg-staging. No deployment occurred.

Focused run: `97ca51a0bb7a4fe88865f32c135a0c7d`; full-suite run:
`7c4e08d7d74a45f29ae407d741712623`. Both owned servers were stopped.
The rehearsal itself made no commit or push. A follow-up delivery was
authorized for `usdg-test` only after rerunning full validation.

## Remaining approval gates

1. Complete real dual-method staging acceptance: native ETH and USDG purchases,
   exact balances, refresh persistence, AI consumption, both replay protections,
   and cross-method rejection. This rehearsal uses mock RPC, not live payments.
2. Approve merge and production work separately. Obtain a verified production
   backup and prove restore on isolated storage; confirm the production database
   version/permissions and run the read-only migration check after approval.
3. Run the explicit migration and repeat check plus core-record comparison.
   A refusal requires investigation; do not bypass schema checks.
4. Follow docs/DUAL_PAYMENTS.md rollout: backend native-only, compatible frontend,
   then enable dual methods. Finish active AI work before restarting backend so
   restart reconciliation does not treat a running job as interrupted.
5. Verify real production payments, credit consumption, persistence, and replay
   only after separate authorization. No deployment/migration/merge is performed
   by this rehearsal.
