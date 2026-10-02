# Isolated Paxos test USDG staging

All USDG implementation is on `usdg-test`. `main` and the live Orb frontend,
backend, and database keep their native testnet ETH flow. Do not merge this
branch or change production environment variables during staging testing.

The branch now also supports simultaneous Test ETH and Paxos USDG. See
[dual-payment configuration and migration](DUAL_PAYMENTS.md) before promotion.
Use `ORB_PAYMENT_METHODS=native_eth,usdg` only on the isolated staging backend
for the next acceptance pass. The original single-method settings below remain
supported. A populated native ledger requires the explicit additive migration;
startup still refuses to adopt it automatically.

This is **Paxos test USDG on Arbitrum Sepolia and has no monetary value**.
The [official Paxos token list](https://docs.paxos.com/guides/stablecoin/usdg/testnet)
identifies `0xFFC95faa3d63Cde504a05B567C600B78C0b41892` as its Arbitrum Sepolia token.
Chain ID is `421614` (`0x66eee`), decimals are `6`.

Pricing uses integers only: 1 credit = `100000` base units = 0.10 test USDG;
3 credits = `300000` = 0.30 test USDG; 5 credits = `500000` = 0.50 test USDG.
Arbitrum Sepolia ETH is still required for gas.

## Payment flow and safety

Signed authentication, wallet sessions, AI jobs, credit reservations, settlement,
failure release, and paid-job recovery use the existing Orb implementation.
`ORB_PAYMENT_METHOD` defaults to `native`; `usdg` enables the staging token flow.
Legacy `ORB_PAYMENT_METHOD=usdg` additionally requires `ORB_DEPLOYMENT_TARGET=usdg-staging`, the exact token,
six decimals, chain 421614, and the specified price. Invalid settings fail startup.

The server creates a 15-minute quote with wallet, receiver, token, amount,
credits, timestamps, status, and the chain's current block height. It returns
the ABI-encoded `transfer(address,uint256)` calldata. The frontend validates
that calldata against the quote and submits `eth_sendTransaction` with only
`from`, token-contract `to`, `value: 0x0`, and `data`. No allowance, approval
transaction, private key, or explicit gas/fee estimate is required.

Verification checks RPC and transaction chain, successful canonical receipt,
confirmations, authenticated sender, exact token target, zero native value,
calldata, configured token code and decimals, receiver, and the exact Transfer
event. Event topics/data must be canonical 32-byte words with correctly padded
addresses; removed, malformed, unrelated, or duplicate matching events fail.
The mined block must follow the quote's creation block. This rejects historic
transfers without requiring perfect server/sequencer clock agreement.

A standard ERC-20 transfer does not encode a quote ID. A transfer matching a
wallet's quote is assigned to that quote when verified, and the transaction's
global uniqueness prevents assigning it to any other quote. A purchase row,
quote completion, and credit grant commit together. Same-quote/same-transaction
retries return the existing balance without another grant. Concurrent retries
are protected by the quote lock and unique purchase constraints.

USDG verification must finish before quote expiry, including confirmations.
If funds were sent but the quote expired, retain the quote ID and transaction
hash for manual reconciliation; do not send another payment automatically.
Orb does not implement automated refunds in this pass. RPC uncertainty grants
no credits. The browser retains pending hashes for verification retries and
blocks a second payment while one is pending.

## Database isolation and additive bootstrap

Use a **new Supabase staging project**, separate password, and its own
`ORB_DATABASE_URL`. Do not copy the live database URL or environment group.
The current fixed `orb` namespace and restart reconciliation make shared
production storage unsafe, even with a different receiver or frontend origin.

For a fresh database, startup transactionally creates core schema version 1
under the existing advisory lock, followed by these additive tables:

- `orb.usdg_quotes`: quote ID primary/foreign key to `orb.quotes`, chain,
  token, decimals, receiver, exact integer amount, creation time and block.
- `orb.usdg_schema_versions`: singleton extension version `1`; identifies
  this ledger as initialized for USDG staging.

No existing core columns, constraints, rows, or schema-version values change.
`quotes.amount_wei` is the retained legacy integer quantity column: for USDG
quotes it contains token base units, duplicated/checked against the explicit
`usdg_quotes.amount_base_units`. It must not be interpreted as ETH in USDG mode.
Quotes' nullable `tx_hash` continues to track pending versus completed status.
Existing purchase transaction and quote uniqueness constraints are retained.

An unmarked ledger containing balances, sessions, challenges, quotes, purchases,
or reservations is rejected before the USDG extension is installed. It is never
adopted or cleared. Subsequent starts accept only extension version 1 and keep
all staging state. Native mode does not install this extension. No migration
has been applied to any hosted database, and no production migration is needed.

The staging database user needs permission to create the `orb` schema and its
tables. The application's deterministic startup bootstrap is the migration;
do not manually edit dashboard tables. Use one backend instance/worker.

## Local USDG testing

Use the README's dependency and frontend setup. Keep your existing `.env`
unchanged. Create an ignored `.env.usdg-local` privately with these settings
and your own server-side AI/RPC configuration:

```env
ORB_ENV=local
ORB_AI_PROVIDER=gemini
ORB_AI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<private-provider-key>
ORB_AI_LOCAL_TESTING=0
ORB_CREDITS_ENABLED=1
ORB_PAYMENT_METHOD=usdg
ORB_DEPLOYMENT_TARGET=usdg-staging
ORB_CHAIN_ID=421614
ORB_USDG_CONTRACT_ADDRESS=0xFFC95faa3d63Cde504a05B567C600B78C0b41892
ORB_USDG_DECIMALS=6
ORB_CREDIT_PRICE_USDG_BASE_UNITS=100000
ORB_PUBLIC_ORIGIN=http://127.0.0.1:5174
ORB_ARBITRUM_RPC_URL=https://<trusted-arbitrum-sepolia-rpc>
ORB_CREDIT_RECEIVER=0x<dedicated-staging-receiver>
ORB_CREDIT_DB=api_output/orb_usdg_credits.sqlite3
ORB_PAYMENT_CONFIRMATIONS=3
```

Start only the intended Orb local backend, from this branch:

```powershell
.\.venv\Scripts\python.exe -m uvicorn prometheus.api.app:app --host 127.0.0.1 --port 8790 --env-file .env.usdg-local
```

Run `npm run dev` in another terminal and open `http://127.0.0.1:5174`.
Local USDG uses separate SQLite storage automatically; hosted staging uses
Postgres with production security guards and unpaid access disabled.

## Manual cloud setup after approval

Nothing in this guide has been deployed or provisioned automatically.

1. **Supabase:** create an Orb-only staging project, such as `orb-usdg-test`.
   Generate/store a new database password privately. In Connect, select the
   Session pooler for IPv4 compatibility and obtain the exact Postgres URI.
   Require TLS and encode password characters as directed by
   [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).
   Do not import live balances, sessions, quotes, or results.
2. **Render:** create a new Docker web service named `orb-api-usdg-test` using
   the same GitHub repository, branch `usdg-test`, repository root, Dockerfile,
   one instance/worker, no disk, health path **`/api/health`**. Disable auto-deploy
   initially and deploy it manually only after entering staging settings.
   Keep the existing `orb-api-7qwv` service unchanged.
3. **Staging backend environment:** enter the following values privately.
   If the preview origin is not yet known, use the non-routable HTTPS placeholder
   below initially; wallet authentication will be unusable until you replace it
   with the actual preview browser origin.

| Variable | Staging setting |
| --- | --- |
| `ORB_ENV` | `production` |
| `ORB_DEPLOYMENT_TARGET` | `usdg-staging` |
| `ORB_PAYMENT_METHOD` | `usdg` |
| `ORB_CHAIN_ID` | `421614` |
| `ORB_USDG_CONTRACT_ADDRESS` | `0xFFC95faa3d63Cde504a05B567C600B78C0b41892` |
| `ORB_USDG_DECIMALS` | `6` |
| `ORB_CREDIT_PRICE_USDG_BASE_UNITS` | `100000` |
| `ORB_CREDIT_RECEIVER` | `0x<dedicated-staging-receiver>` |
| `ORB_ARBITRUM_RPC_URL` | `https://<trusted-arbitrum-sepolia-rpc>` |
| `ORB_PAYMENT_CONFIRMATIONS` | `3` |
| `ORB_DATABASE_URL` | `<private-new-staging-postgres-uri-with-TLS>` |
| `ORB_PUBLIC_ORIGIN` | `https://orb-usdg-preview.example.invalid`, then actual preview origin |
| `ORB_UPLOAD_DIR` | `/tmp/orb_uploads` |
| `ORB_AI_PROVIDER` | `gemini` |
| `ORB_AI_MODEL` | `gemini-3.5-flash-lite`, or your verified model |
| `GEMINI_API_KEY` | `<private-server-side-provider-key>` |
| `ORB_AI_LOCAL_TESTING` | `0` |
| `ORB_CREDITS_ENABLED` | `1` |

Do not set a production SQLite path or Nimiq flag. No wallet private key or
Supabase service-role key is needed. Use staging secrets rather than copying
the production environment group. Check `/api/health` and
`/api/orb/credits/config` for `payment_method=usdg`, chain 421614, price 100000,
and the exact token. Bootstrap must succeed against the isolated database.

4. **Vercel Preview:** use the existing Orb Vercel project. Keep its Production
   branch `main` and Production variables unchanged. Add these variables scoped
   to **Preview AND Git branch `usdg-test` only**:
   `VITE_API_BASE_URL=https://<staging-render-service>.onrender.com` and
   `VITE_ORB_DEPLOYMENT_TARGET=usdg-staging`. No backend secrets belong here.
   [Vercel supports Preview variables scoped to individual branches](https://vercel.com/docs/environment-variables).
5. **Deploy the Preview manually:** this branch's `vercel.json` disables Git
   auto-deployment for `usdg-test`, so pushing the branch does not deploy it.
   [This setting affects Git-triggered deployments](https://vercel.com/docs/project-configuration/git-configuration).
   After deployment approval, use the Vercel CLI from this branch, link to the
   existing Orb project, and run `vercel deploy` (Preview default; **no `--prod`**).
   Verify the build reads the branch-scoped Preview variables. Alternatively,
   enable this branch's Git deployment in a later approved change and trigger
   a Preview from `usdg-test`. The build guard refuses a Production USDG build
   or the existing production API URL. The Preview wallet also refuses a backend
   that does not identify itself as `usdg-staging` with USDG payments.
6. **Origin/CORS:** obtain the exact HTTPS Preview URL from the deployment.
   Set only staging Render's `ORB_PUBLIC_ORIGIN` to that browser origin with
   no path or trailing slash, then restart/deploy the staging service. Open
   that same URL for signing. If the preview is replaced with a new unique URL,
   update staging origin again, or use its actual stable branch alias if offered
   by Vercel. No wildcard or production origin change is needed.

## Obtain test assets and run the real test

1. Use the **Paxos Testnet Faucet** linked from the official
   [test-asset funding guide](https://docs.paxos.com/guides/developer/fund-sandbox-with-test-crypto).
   Select USDG and Arbitrum Sepolia, enter the purchasing wallet's public
   address, complete any faucet verification, and request test tokens. Confirm
   delivery on Arbitrum Sepolia. If that network/token is unavailable in the
   faucet, request test tokens from Paxos/the event organizer; do not substitute
   a different USDG contract. Never enter your private key or recovery phrase.
2. Import the official token contract above into MetaMask on chain 421614,
   using symbol USDG and six decimals. Have at least 0.30 test USDG for the
   three-credit test. Faucet tokens have no monetary value.
3. Obtain **Arbitrum Sepolia ETH** for gas from a faucet listed in Paxos's guide
   or [Arbitrum's testnet guide](https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info).
   Confirm the faucet is for Arbitrum Sepolia, not Ethereum Sepolia or mainnet.
4. Open the actual USDG Preview URL. Connect, switch to Arbitrum Sepolia, sign
   the staging challenge, and record the starting Orb credit balance.
5. Select three credits and click Buy credits with USDG. Check the server quote
   displays **0.30 test USDG**. In MetaMask, confirm token contract, receiver,
   zero native transfer value, and ETH gas. Approve the single token transfer.
6. Wait for three confirmations and backend verification. Save the quote ID
   and transaction hash from browser network requests and wallet activity.
   Credits must increase by exactly three. Refresh and sign again if required;
   the isolated Postgres balance must remain unchanged.
7. Repeat the same authenticated verification request (same quote ID/hash)
   using the browser's network-request replay feature; the response may report
   the existing credited purchase, but must not increase credits again. A
   different quote cannot accept that already-credited transaction.
8. Run one genuine Decode, Compose, or Enhance and confirm a saved result and
   exactly one consumed credit. Check session-expiry recovery and restart the
   staging backend to verify persisted credits/results. Keep production out of
   this test.

No real USDG transaction, live Supabase bootstrap, or live AI operation is
claimed by mocked tests. These remain required staging acceptance checks.

## Automated validation

Validated on 2026-10-02 (dual-payment branch): **253 backend tests passed**, **59 frontend tests
passed**, and the guarded staging frontend build passed. The backend emitted
108 existing FastAPI lifespan deprecation warnings. No tests were removed.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:web
$env:VITE_ORB_DEPLOYMENT_TARGET="usdg-staging"
$env:VITE_API_BASE_URL="https://orb-usdg-api.example.invalid"
npm run build:vercel
```

Blockchain tests use mocked RPC and disposable wallets; ledger tests use
temporary SQLite and SQL-recording Postgres drivers. They verify rejection,
atomic rollback, replay/concurrent idempotency, settlement/release, staging
bootstrap, existing-ledger refusal, and default native-ETH regression coverage.
They do not establish live Supabase or on-chain success.
