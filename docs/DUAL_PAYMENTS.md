# Dual testnet payments

Orb can expose **Test ETH** and **Paxos USDG** simultaneously on Arbitrum
Sepolia (421614). Paxos test USDG has no monetary value. Both payments fund
the same Orb test-credit balance; each successful AI operation still costs one
credit. Wallet USDG balance display is not added in this pass.

The user reported successful real USDG testing of the earlier single-method
staging build: wallet authentication, 0.30 USDG / three credits, refresh
persistence, AI credit consumption, and duplicate prevention. Dual payments were subsequently reported working in production with the
earlier 100000-base-unit price. The new intended price below is a code/config
recommendation; this change does not deploy or alter production settings.

## Configuration and compatibility

```env
ORB_PAYMENT_METHODS=native_eth,usdg
ORB_CHAIN_ID=421614
ORB_USDG_CONTRACT_ADDRESS=0xFFC95faa3d63Cde504a05B567C600B78C0b41892
ORB_USDG_DECIMALS=6
ORB_CREDIT_PRICE_USDG_BASE_UNITS=3000
```

`ORB_PAYMENT_METHODS` is the explicit allow-list. Empty, unknown, or duplicate
values fail startup. It takes precedence over the legacy single-method switch.
Without it, `ORB_PAYMENT_METHOD=native` (or absent) keeps native ETH only;
legacy `ORB_PAYMENT_METHOD=usdg` keeps its staging-only guard. Single-method
quote requests may omit the method for existing-client compatibility. With
two methods, the request MUST select one.

Keep the current `ORB_CREDIT_PRICE_WEI`, receiver, trusted RPC, database URL,
confirmation count, signed sessions, HTTPS origin, and AI settings. USDG is
fixed at six decimals. Its credit price is a configurable positive integer,
with a default of 3000 base units: one credit is 0.003 test USDG, three are
0.009, and five are 0.015. Explicit 100000 remains valid for earlier pricing.
Zero, negative, and non-integer values fail startup. Price is separate from
the fixed chain/token/decimals safety checks. No floating-point payment
arithmetic is used; existing quotes retain their stored amount after repricing.
Explicit multi-method configuration prepares eventual production use without
requiring the `usdg-staging` target; do not enable it on production yet.

For staging retain `ORB_DEPLOYMENT_TARGET=usdg-staging` and its isolated
database, receiver, origin, and backend. Existing production values stay private
and unchanged. Do not point a staging backend at production storage: startup
job reconciliation is shared by every instance using that ledger.

## Server-authoritative API

`GET /api/orb/credits/config` returns the global `enabled`/testnet/chain fields
plus `payment_methods`:

```json
{
  "payment_methods": {
    "native_eth": { "enabled": true, "symbol": "ETH", "decimals": 18, "price_wei": "<existing-price>" },
    "usdg": {
      "enabled": true, "payment_method": "usdg", "token_symbol": "USDG",
      "token_contract": "0xFFC95faa3d63Cde504a05B567C600B78C0b41892",
      "token_decimals": 6, "price_base_units": "3000"
    }
  }
}
```

The selector shows only server-enabled known methods, defaults to native ETH
when available, and marks the selection with `aria-pressed`. Switching changes
only payment copy and clears displayed quote details. It does not submit a
transaction, change credits, or affect any AI mode. Controls are disabled while
a purchase is submitting; an outstanding payment still blocks another purchase.
The displayed USDG price preview uses the server-configured integer unit price.
Only the actual returned quote supplies the transaction amount/credits.

`POST /api/orb/credits/quotes` takes the signed session and:

```json
{ "credits": 3, "payment_method": "usdg" }
```

Prices, amount, receiver, token, expiry, and calldata come from the backend.
Native quotes include `payment_method=native_eth` and retain their existing
native value and ORB1 quote-binding data. USDG quotes include their explicit
token metadata and ERC-20 transfer data; native value is zero.

Verification still takes only quote ID and transaction hash. The persisted
quote determines the method: native quotes have the ORB1 binding; USDG quotes
require their `usdg_quotes` metadata record. Client verification cannot choose
or switch the method. A disabled method cannot be settled through another path.

The quoted `from`, `to`, `value`, and `data` stay unchanged. Native target is the
receiver; USDG target is the configured token with `transfer(receiver, amount)`
and zero native value. No approval transaction, private key, or new payment
contract is added.

### Fresh transaction fees

Each user-initiated purchase estimates fresh fees through the active EIP-1193
wallet provider before requesting transaction approval. No fee cache is used.

1. Confirm Arbitrum Sepolia and the authenticated account.
2. Read `eth_getBlockByNumber("pending", false)`, falling back to `latest` if
   pending is unsupported or has no valid positive base fee.
3. Prefer `eth_maxPriorityFeePerGas`. If unavailable/malformed, use the median
   of three recent blocks' 50th-percentile rewards from `eth_feeHistory`. Last
   fallback is current `eth_gasPrice - baseFeePerGas`, only if nonnegative.
   Zero tips are accepted from actual network data. Tips greater than the base
   fee are rejected as excessive; no static gwei fallback or arbitrary tip is
   substituted.
4. Validate with `eth_estimateGas` using exactly the quoted transaction,
   including native quote-binding data or USDG transfer calldata. Require a
   valid positive estimate, but leave the gas limit to the wallet. Arbitrum's
   execution and data-posting estimate can change while approval is pending;
   do not assume 21,000 gas. See [Arbitrum gas estimation](https://docs.arbitrum.io/arbitrum-essentials/how-to-estimate-gas).
5. Refresh the base fee after estimation, then set (all arithmetic is BigInt):
   `maxFeePerGas = ceil(baseFeePerGas * 3 / 2) + maxPriorityFeePerGas`.
   This gives 50% base-fee headroom without blindly doubling it. Tests cover
   integer rounding, large quantities, fresh rising base fees, and 49% base
   growth. It is a bounded approval cushion, not a guarantee against unlimited
   delay/congestion. The tip bound keeps the cap at most 2.5 times the current
   base fee (plus integer rounding). This cap is a maximum, not the amount
   necessarily charged; see [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559).
6. Recheck account/network, authentication epoch, provider identity and quote
   expiry. Submit once with the two EIP-1559 fields; omit `gasPrice`, `gas`, and
   `nonce`. The wallet still presents approval and selects the gas limit.

Read RPCs have an eight-second timeout and the entire estimate a 30-second
deadline. Unsupported/malformed read sources may fall back; wallet rejection,
disconnect, or changed identity stops the attempt. Missing robust estimates
show “Orb couldn't obtain a fresh network fee estimate. Please retry Buy
Credits.” There is no static-fee fallback and no automatic transaction resend.
An ambiguous submission without a valid hash cannot trigger verification or
credit grant: inspect wallet activity before another manual attempt. Payment
verification and shared ledger idempotency remain unchanged.

Validation uses deterministic mocked providers; a real wallet/testnet approval
must be checked separately after an authorized deployment. No live transaction
is sent by automated validation.

## Verification, replay, and settlement

Both methods retain chain, authenticated sender, receiver, receipt success,
canonical block, confirmation, exact value/calldata, and quote ownership checks.
USDG additionally verifies the exact token contract, zero native value, token
code/decimals, quote creation block, expiry, and one canonical matching Transfer
log (from, to, integer value). The UI distinguishes insufficient token funds
from ETH required for gas.

`purchases.tx_hash` is globally unique across BOTH methods; `quote_id` is unique
and `quotes.tx_hash` is unique. Purchase insertion, quote completion, and balance
grant commit atomically under the existing quote lock. Same quote/hash retries
return the existing balance. Cross-method transfers fail before granting.
Native settlement timing is unchanged; USDG verification must complete before
its 15-minute expiry, including confirmations. Retain a submitted hash for
verification retry/support rather than automatically sending another payment.

Credit reservations, idempotent AI submissions, durable results, consumption,
failed-operation release, wallet sessions, and paid-job recovery are unchanged.

## Explicit production migration — NOT run by this task

No core table, schema version, purchase, wallet, job, session, or balance is
rewritten. The extension remains version 1 and adds only:

- `orb.usdg_quotes`: primary/foreign key to `orb.quotes`, chain, token,
  decimals, receiver, integer base-unit amount, creation time and block.
- `orb.usdg_schema_versions`: validated singleton version 1 marker.

Existing single-method USDG staging databases already have these structures;
the migration validates them and is a no-op. A populated native ledger without
the extension still fails startup when USDG is enabled. It requires the explicit
command below. Fresh isolated ledgers keep their deterministic startup bootstrap.

Run from the approved code revision with `ORB_DATABASE_URL` privately supplied
to the process. The command does NOT load `.env`, import the FastAPI app,
reconcile reservations, or reveal connection details.

```powershell
# Read-only check. Exit 0 = ready; 2 = valid core needing migration; 1 = refused.
.\.venv\Scripts\python.exe -m prometheus.api.orb_usdg_migrate --check

# Explicit additive migration. Run only after database-change approval/backup.
.\.venv\Scripts\python.exe -m prometheus.api.orb_usdg_migrate

# Confirm ready; must return exit 0.
.\.venv\Scripts\python.exe -m prometheus.api.orb_usdg_migrate --check
```

On Render/Linux use `python -m prometheus.api.orb_usdg_migrate` (same options)
in an authorized operator environment with its existing Postgres credentials.
No database URL should appear in the command line, chat, logs, or source files.

The migration checks the expected core version, exact column types/nullability,
primary/unique/foreign-key/check constraints, and extension shape/version.
Missing, partial, extra, or unsupported schema shapes fail closed. It uses the
same advisory transaction lock as bootstrap, a short table lock for the quote
foreign key, a 10-second lock timeout, and a 30-second statement timeout.
Extension DDL, marker, and verification commit together or roll back together.
Retries are safe. `--check`/`--dry-run` uses a read-only transaction and no DDL.
An extra table in the fixed `orb` namespace requires manual review.

Do not delete the extension as rollback: leave additive tables and records in
place and disable USDG. The unchanged native code ignores extra tables. Revert
application/environment settings if needed; any database restoration requires
reconciliation of payments made after the backup.

## Isolated staging acceptance required before merge

1. Keep the existing isolated Supabase/Render/Preview environment. Set only
   staging `ORB_PAYMENT_METHODS=native_eth,usdg`; keep the staging target and
   exact Preview origin. Remove the obsolete single-method override or leave
   it knowing the explicit list takes precedence. No production changes.
2. Run migration `--check` against the staging DB. For the previously initialized
   USDG DB expect ready/no-op. Separately test the additive migration on a
   disposable populated native ledger or restored staging copy, then rerun check.
   Verify balances, sessions, native purchases, active reservations, and results
   survive. Never boot another backend against production for this test.
3. Deploy the branch only to the authorized staging backend and Preview. Keep
   Preview-only `VITE_ORB_DEPLOYMENT_TARGET=usdg-staging` and API URL pointing
   only to staging. Git auto-deployment remains disabled for this branch.
4. Native ETH: select Test ETH, buy a small credit bundle, verify exact balance
   increase, refresh persistence, and one successful AI operation consuming one.
5. USDG: select Paxos USDG, obtain three-credit 0.009 quote, approve ERC-20 transfer
   using Sepolia ETH gas; verify exact +3 balance, refresh, and one AI consumption.
6. Replay each same quote/hash verification; no new grant. Try each hash on a
   fresh quote of the OTHER method; both must reject. Test insufficient funds,
   rejected wallet approval, and pending verification without another charge.
7. Restart only staging: balances/results persist. Check job/session recovery.
   Record both transaction hashes, quote IDs, before/after balances, and results
   as private acceptance evidence. Do not claim success from mocked tests.

## Prepared production rollout — requires separate approval

An old frontend omits the quote method; dual mode deliberately requires it.
Use this compatible order instead of enabling both methods before frontend:

1. Finish real dual staging acceptance and migration rehearsal above. Review
   and approve merge/deployment separately; this pass does not merge.
2. Make a verified production database backup and test recovery on an isolated
   restore. Record balances/reservations/purchases for post-migration comparison.
3. Run migration `--check` privately against production after approval. If it
   returns 1, stop. Exit 2 is expected for the untouched native ledger.
4. Run explicit migration, repeat `--check`, and verify core records unchanged.
5. Deploy the new backend with **native only** (`ORB_PAYMENT_METHODS=native_eth`)
   and existing production receiver/price/RPC/origin/database/AI configuration.
   Verify `/api/health`, config, signed sessions, and native purchase path.
6. Deploy the new frontend to production with the existing production API URL;
   omit `VITE_ORB_DEPLOYMENT_TARGET=usdg-staging`. It initially shows native only.
   This frontend sends explicit methods and also accepts legacy config.
7. Enable `ORB_PAYMENT_METHODS=native_eth,usdg` on production Render and add the
   exact token/decimals and configurable price variables above. Keep chain 421614 and every
   existing native setting. Do not use the staging target/origin/database.
8. Verify health/config, reload the production frontend, and verify both options.
   Stale pre-upgrade browser tabs may need refresh; no payment has been sent
   when a missing-method quote is rejected.
9. Perform one small native purchase and one small USDG purchase, checking exact
   increases, confirmations, receipt verification and replay rejection.
10. Verify a successful AI operation consumes one, failed operation restores
    reservation, refresh/restart persistence, and same-wallet job recovery.

## Validation limits

2026-10-02: complete backend suite **253 passed** (108 existing FastAPI
deprecation warnings), complete frontend suite **59 passed**, guarded staging
production build passed with a non-routable HTTPS API placeholder. Frontend
tests used `node node_modules/vitest/vitest.mjs run --pool=threads --maxWorkers=1`
after a Windows fork-worker startup timeout. Initial sandbox temp-directory
access errors were resolved by running test tools with normal filesystem access.

Automated tests use mocked RPC/AI, temporary SQLite, and SQL/catalog Postgres
doubles. They cover dual config/quotes/payments, cross-method failures, global
replay, atomic rollback, concurrency, unchanged native behavior, selector states,
and migration validation/rollback/retry. Live dual payment and real Postgres
migration rehearsal remain required; no deployed database was accessed here.


## Disposable populated-Postgres rehearsal (2026-10-03)

The explicit migration was rehearsed on an owned local PostgreSQL 17.11 cluster
with TLS and synthetic populated core-v1 records. Eight real-Postgres tests
passed: read-only check, additive migration, unchanged core data/schema/physical
rows, idempotent retries, five failure cases, atomic DDL rollback, concurrent
migrations, and dual-mode application startup/recovery. See
[MIGRATION_REHEARSAL.md](MIGRATION_REHEARSAL.md) for snapshots, commands,
expected startup reconciliation, and remaining approval gates. This satisfies
the local real-Postgres rehearsal requirement; it does not establish live dual
payment acceptance or authorize production migration. No production service or
database was accessed. The earlier validation paragraph above describes the
previous code-preparation pass and its test doubles.
