# Orb

Orb is an AI-powered visual intelligence and creative prompting platform that helps creators understand, reconstruct, compose, and refine the prompts behind images and videos.

It combines multimodal AI with Arbitrum Sepolia testnet credits to create a verifiable, on-chain access layer for AI-powered creative workflows.

Built for the **Arbitrum Open House Singapore Online Buildathon**.

> The `usdg-test` branch prepares two payment methods: Arbitrum Sepolia Test ETH
> and Paxos test USDG. USDG has no monetary value.
> The live `main` deployment still uses native testnet ETH. See
> [USDG staging setup](docs/USDG_STAGING.md) for configuration, isolation,
> fresh database bootstrap, preview deployment, and the manual payment test;
> [dual-payment promotion](docs/DUAL_PAYMENTS.md) covers the payment selector,
> explicit populated-database migration, and staged production rollout.

## Live Demo

- **Frontend:** [Open Orb](https://orb-azure-ten.vercel.app)
- **Backend:** [Orb API](https://orb-api-7qwv.onrender.com)

> Orb currently runs on Arbitrum Sepolia. Credits are testnet/demo credits and have no real-money value. You need Arbitrum Sepolia testnet ETH for purchases and gas.

The backend runs on Render Free and may need time to wake after inactivity. Orb displays “Preparing Orb…” while checking readiness. See [Render's Free service guide](https://render.com/docs/free) for cold-start and temporary-filesystem behavior.

---

## Why Orb

Generative image and video tools can produce remarkable visuals, but creators often encounter content without knowing:

- how it may have been prompted
- how to describe its visual composition
- how to turn a reference into a generation-ready prompt
- how to improve an existing idea for modern generative models

Orb turns that problem into a creative workflow.

---

## Core Modes

### Decode

Upload an image or video and Orb reconstructs a plausible generation prompt based on:

- subject
- composition
- lighting
- camera perspective
- movement
- visual style
- atmosphere
- scene structure

Decode does not claim to recover the creator's exact original prompt. It produces a plausible reconstruction based on visual evidence.

### Compose

Upload an image or video reference and Orb creates a new generation-ready prompt inspired by it.

Compose is designed for creators who want to reuse the visual language, mood, structure, or cinematography of a reference without attempting to recover its original instructions.

### Enhance

Paste an existing image or video prompt and Orb refines it into a more deliberate generation-ready instruction.

Enhance can improve:

- composition
- lighting
- camera direction
- atmosphere
- visual detail
- motion language
- scene consistency

Choose an image or video target, an optional visual style, and a level of detail. Orb displays the original and improved prompts. Enhance improves text; it does not generate media.

### Create — Coming Soon

Orb's planned Create mode will turn the knowledge produced by Decode, Compose, and Enhance into finished images and videos using advanced generative media models.

The long-term Orb workflow is:

**Decode → Compose → Enhance → Create**

Understand → Build → Refine → Realize

Create is visibly locked and unavailable. Its information popover explains the roadmap; it does not run an AI operation or charge credits. Orb currently returns prompts, not generated images or videos.

### Inputs and Results

- **Images:** JPEG, PNG, and WebP, up to 20 MB.
- **Videos:** MP4, MOV, M4V, and WebM, up to 200 MB, subject to media validation.
- **Enhance:** an existing prompt of 3–4,000 characters.
- **Results:** a generation-ready prompt with visual analysis where applicable, and a Copy Prompt action.

---

## Arbitrum Integration

Orb uses **Arbitrum Sepolia** for its testnet credit system.

Users can:

1. Connect an EVM-compatible injected wallet, such as MetaMask.
2. Authenticate using a signed challenge.
3. Purchase testnet Orb credits.
4. Use one credit per successful Decode, Compose, or Enhance operation.
5. Receive the resulting prompt.
6. Have the credit settled only after a successful result is safely stored.

### Network

- **Network:** Arbitrum Sepolia
- **Chain ID:** `421614`
- **Payment assets:** native testnet ETH and optionally Paxos test USDG
- **Credit type:** demo/test credits only

The Buy Credits panel offers 1, 3, or 5 credits. The default price is `1000000000000` wei (0.000001 testnet ETH) per credit, plus network gas. Orb obtains fresh EIP-1559 fee estimates; the wallet controls the gas limit and presents transaction approval. The server quote supplies the configured price and receiving address; the user approves every transfer in their wallet. See [payment fee policy](docs/DUAL_PAYMENTS.md#fresh-transaction-fees).

When explicitly enabled with `ORB_PAYMENT_METHODS=native_eth,usdg`, Paxos test USDG uses the official Arbitrum Sepolia token and six decimals. Its configurable positive-integer price defaults to `ORB_CREDIT_PRICE_USDG_BASE_UNITS=3000`: 1/3/5 credits cost 0.003/0.009/0.015 test USDG. An explicit `100000` remains valid. Test USDG has no monetary value; Sepolia ETH is still needed for gas. Existing quotes retain their original amount if the configured price changes.

Orb independently verifies payment receipts before granting credits. It checks the chain, successful receipt, canonical block and required confirmations, authenticated sender, dedicated receiving wallet, exact payment value, and the native ETH quote identifier or USDG Transfer event as appropriate.

Payments use a direct native ETH transfer or an ERC-20 USDG transfer to the configured testnet receiving wallet. USDG credit grants require independent receipt and Transfer-event verification. Orb does not need a payment contract or a wallet private key. Authentication currently supports externally owned wallets using `personal_sign`; contract-wallet authentication is not implemented.

---

## Credit Safety

Orb's paid AI flow is designed to prevent duplicate charges and unfair credit loss.

The backend:

- verifies wallet ownership using a nonce-based, domain-bound, expiring signed challenge
- prevents duplicate payment grants using a unique transaction constraint
- reserves credits atomically
- uses idempotency keys to prevent duplicate AI submissions
- consumes one credit only after a result is safely stored
- releases the reservation if the AI operation fails before producing a durable result
- preserves completed results across backend restarts
- allows same-wallet recovery after wallet-session expiry

Wallet sessions last one hour. The browser keeps its token in session storage; the backend persists a hash of that token and its expiry in the ledger. If a paid job's session expires, Orb pauses polling and asks the user to sign again. Authenticating the same wallet resumes the existing job without a new reservation or charge. Another wallet cannot access that job or result.

Disconnect Wallet clears the browser's wallet, payment, and saved-job state and requests backend session revocation. If server sign-out cannot be confirmed, Orb reports that the old session will expire. Disconnecting does not erase purchased credits or send a blockchain transaction.

---

## Architecture

### Frontend

- Vanilla JavaScript
- Vite
- Vercel
- EIP-1193 wallet integration

### Backend

- Python
- FastAPI
- Uvicorn
- FFmpeg / FFprobe
- multimodal AI provider integration
- Render

### Persistence

- PostgreSQL on Supabase in production
- SQLite for local development
- persistent wallet sessions and credit balances
- payment quotes and verified purchases
- job reservations and credit settlement
- completed AI results

Production stores completed prompt and analysis data in Postgres JSONB. Local development stores completed results in files alongside its SQLite ledger. Production does not depend on a persistent Render disk.

### Blockchain

- Arbitrum Sepolia
- native testnet ETH payments
- server-side transaction verification

---

## Video Processing

For video Decode and Compose, Orb:

1. validates the uploaded media
2. inspects it with FFprobe
3. detects scene structure
4. samples representative frames
5. analyzes scene-level and global visual information
6. constructs the resulting generation prompt

The uploaded source media is temporary and is not used as permanent production application storage. Production cleans up source files and extracted frames after processing. Durable recovery restores prompt and analysis text, without media previews. Local development retains result files and previews for inspection.

---

## Security

Orb keeps sensitive configuration server-side.

The frontend never receives:

- AI API keys
- database credentials
- wallet private keys
- recovery phrases
- backend secrets

Orb uses signed wallet challenges for authentication and validates paid operations server-side. Wallet authentication includes nonce replay protection, expiry, chain, and exact browser-origin checks. Production CORS allows the configured Orb frontend origin, not a wildcard.

Public AI operations require an authenticated wallet and available credits. The unpaid development bypass requires explicit local settings and a loopback request; production startup rejects that bypass.

---

## Running Locally

### Requirements

- Python 3.12+
- Node.js 22+ and npm
- FFmpeg and FFprobe available on `PATH`
- a server-side Gemini API key and access to the selected model
- an injected EVM wallet and Arbitrum Sepolia testnet ETH for payment testing

SQLite is included with Python and initialized automatically; Supabase is not required locally.

Run the following commands from the Orb repository root in two separate PowerShell terminals.

### Backend

Create the Python environment and install dependencies. `python-dotenv` is needed for Uvicorn's explicit `--env-file` option.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt python-dotenv
if (!(Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Edit `.env` privately. This example uses placeholders only:

```env
ORB_ENV=local
ORB_AI_PROVIDER=gemini
ORB_AI_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=<your-server-side-api-key>
ORB_AI_LOCAL_TESTING=1
ORB_CREDITS_ENABLED=0
ORB_PUBLIC_ORIGIN=http://127.0.0.1:5174
```

Use a model available to your provider account. The model above was verified during Orb's local AI testing. A real provider key is required; Orb does not substitute mock output for genuine analysis.

Local development also supports `ORB_AI_PROVIDER=openai` with a server-side `OPENAI_API_KEY`. The production configuration requires Gemini.

Start the backend with the local environment file explicitly loaded:

```powershell
.\.venv\Scripts\python.exe -m uvicorn prometheus.api.app:app --host 127.0.0.1 --port 8790 --env-file .env
```

The `prometheus` module path is Orb's existing internal Python package name. This command runs the backend from this independent Orb repository.

Uvicorn does not load `.env` automatically. Restart the backend after editing it, and remove stale shell overrides if they conflict with the file. Keep `.env` private and ignored by Git.

### Frontend

In the second terminal:

```powershell
npm ci
npm run dev
```

Open [local Orb](http://127.0.0.1:5174). Vite binds to loopback port 5174 and proxies `/api` to the backend at port 8790. Use this exact browser origin for wallet testing.

### Backend Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8790/api/health
Invoke-RestMethod http://127.0.0.1:8790/api/ready
```

`/api/health` reports service and AI configuration. `/api/ready` checks whether the backend can accept analysis, including processing tools and temporary storage. `/api/upload-ping` checks multipart upload handling without running AI.

### Local Payment Testing

To exercise the actual paid flow, update the server-side `.env` and restart the backend:

```env
ORB_ENV=local
ORB_AI_LOCAL_TESTING=0
ORB_CREDITS_ENABLED=1
ORB_PUBLIC_ORIGIN=http://127.0.0.1:5174
ORB_ARBITRUM_RPC_URL=https://<trusted-arbitrum-sepolia-rpc>
ORB_CREDIT_RECEIVER=0x<dedicated-testnet-receiving-address>
```

Keep the AI provider settings from the previous example. The receiving address must be a valid externally owned wallet address, not a private key. Fund the purchasing wallet with Arbitrum Sepolia testnet ETH, connect and sign, then use Wallet & Credits to buy credits.

Optional local settings include `ORB_CREDIT_DB` (default `api_output/orb_credits.sqlite3`), `ORB_CREDIT_PRICE_WEI` (default `1000000000000`), and `ORB_PAYMENT_CONFIRMATIONS` (default `3`). Do not enable the legacy Nimiq payment flag; that integration remains disabled and separate from Orb credits.

---

## Deployment Configuration

Orb uses a separate Vercel frontend, Render Free Docker backend, and Supabase Postgres database. Configure secrets through the backend hosting environment, never through committed `.env` files or client-side `VITE_*` variables.

### Supabase Postgres

Use a server-side Postgres connection string in `ORB_DATABASE_URL`. For a persistent IPv4 backend, use the shared **Session pooler** connection from the project's **Connect** panel, as described in [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres). Use TLS (`sslmode=require` or a supported verification mode), and correctly encode special characters in credentials.

Orb creates its dedicated `orb` schema and version 1 tables transactionally under a database advisory lock. Existing tables are not dropped or recreated on startup. The database user must be able to create the schema and tables. Future schema changes require a versioned migration; local SQLite data is not imported automatically.

All production ledger state, sessions, quotes, purchases, reservations, and completed results live in Postgres. Startup reconciles interrupted reservations: a saved deliverable result is settled; an incomplete operation's reservation is released. Use **one backend instance and one worker** so startup reconciliation cannot race another active worker.

### Render Backend

- **Runtime:** Docker, using the repository's `Dockerfile`
- **Recurring health-check path:** `/api/health`
- **Instances/workers:** one
- **Persistent disk:** not required
- **Temporary uploads:** `/tmp/orb_uploads`

The Dockerfile installs FFmpeg/FFprobe and starts Orb with:

```sh
uvicorn prometheus.api.app:app --host 0.0.0.0 --port ${PORT:-10000}
```

Let Render supply `PORT`. Production uses Render environment variables and does not need a local `.env` file. Keep `/api/ready` for analysis readiness checks, rather than Render's recurring liveness check.

Enter these backend settings privately. All secret and account-specific values below are placeholders:

| Variable | Production setting |
| --- | --- |
| `ORB_ENV` | `production` |
| `ORB_AI_PROVIDER` | `gemini` |
| `ORB_AI_MODEL` | `gemini-3.5-flash-lite`, or your verified available model |
| `GEMINI_API_KEY` | `<server-side-api-key>` |
| `ORB_AI_LOCAL_TESTING` | `0` |
| `ORB_CREDITS_ENABLED` | `1` |
| `ORB_PUBLIC_ORIGIN` | `https://<exact-orb-frontend-domain>` |
| `ORB_ARBITRUM_RPC_URL` | `https://<trusted-arbitrum-sepolia-rpc>` |
| `ORB_CREDIT_RECEIVER` | `0x<dedicated-testnet-receiving-address>` |
| `ORB_DATABASE_URL` | `postgresql://<user>:<password>@<host>:<port>/<database>?sslmode=require` |
| `ORB_UPLOAD_DIR` | `/tmp/orb_uploads` |
| `ORB_CREDIT_PRICE_WEI` | `1000000000000` (current default) |
| `ORB_PAYMENT_CONFIRMATIONS` | `3` (current default) |

Production requires Postgres, the Gemini provider and explicit model, a server-side API key, paid credit mode, local testing disabled, and an exact HTTPS frontend origin. It refuses an ephemeral SQLite ledger. Production does not require `ORB_DATA_DIR`, `ORB_CREDIT_DB`, a durable `ORB_OUTPUT_DIR`, or a Supabase service-role key.

Set `ORB_PUBLIC_ORIGIN` to the frontend's exact browser origin, without a trailing slash or path. CORS and signed wallet challenges use this origin. A different preview domain needs its own explicitly configured backend origin. Do not enable legacy payment settings or add wallet private keys.

### Vercel Frontend

- **Project root:** repository root
- **Framework:** Vite
- **Build command:** `npm run build:vercel`
- **Output directory:** `web_dist`
- **Frontend-safe environment variable:** `VITE_API_BASE_URL=https://<orb-backend-domain>`

`vercel.json` contains the build and output settings. `VITE_API_BASE_URL` must be an HTTPS backend origin without a path, credentials, or localhost. The guarded build rejects invalid values. For the live demo, this public API origin is `https://orb-api-7qwv.onrender.com`.

Do not put Gemini keys, database connection strings, RPC credentials, or wallet secrets into Vercel or `VITE_*` variables. Production requests use the configured backend origin; the loopback Vite proxy is for development only.

### Deployment Validation

After an authorized deployment or configuration update:

1. Check `/api/health`, `/api/ready`, and `/api/orb/credits/config`; confirm paid mode and chain ID `421614`.
2. Confirm the production frontend origin matches `ORB_PUBLIC_ORIGIN` and wallet signing works from that origin.
3. Connect MetaMask, switch to Arbitrum Sepolia, sign the challenge, and inspect the balance.
4. With approval for a testnet transfer, buy one credit and wait for server verification.
5. Run Decode; confirm a genuine AI result and exactly one consumed credit.
6. Confirm same-wallet session recovery works. Refresh/restart the backend and check that the balance and completed result remain available.

Automated tests do not establish that a deployed provider call or on-chain payment succeeded. Repeat the real flow when validating a new deployment.

---

## Tests and Build

For `usdg-test`, use the [staging validation commands](docs/USDG_STAGING.md#automated-validation),
including `VITE_ORB_DEPLOYMENT_TARGET=usdg-staging` for the guarded build.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:web
```

Check the guarded production build in a separate terminal with a non-secret placeholder HTTPS API origin:

```powershell
$env:VITE_API_BASE_URL="https://orb-api.example.invalid"
npm run build:vercel
```

The placeholder is for build validation only. Use the real public Orb backend origin for deployment.

Repository validation on **2026-10-06** (`main`): **309 backend tests passed**, **8 opt-in real-Postgres tests skipped**, **192 frontend tests passed**, and the guarded production frontend build passed. No deployment was performed during this validation.

Video performance Phase 1 adds bounded independent scene AI calls (maximum two),
reuse of validated unchanged-upload metadata, and exact FFmpeg seek reuse without
changing visual evidence or prompts. See [implementation and local comparisons](docs/VIDEO_PHASE1.md).

The backend suite covers AI validation, upload reliability, wallet authentication, payment verification, credit lifecycle, result recovery, and production guards. The frontend suite covers wallet/session recovery, payment requests, mode state, results, and UI behavior.

Provider and blockchain integration tests use test doubles. Postgres adapter tests use a SQL-recording driver and a SQLite-backed database double; they do not connect to a live Supabase database. The opt-in real-Postgres migration tests require the disposable rehearsal database and were not run in this pass. Live AI and on-chain checks are separate from these automated tests.

## Performance Diagnostics

Orb records content-free structured backend timings for upload, validation, queue wait, media processing, AI calls/retries, result persistence, and credit settlement. Browser timings are development-only by default, with a local tab opt-in for production diagnostics. This does not change processing or payment behavior. See [Performance timing](docs/PERFORMANCE_TIMING.md) for metrics, safe diagnostic activation, local mock-provider fixture results, and measurement limits.

## Project Layout

- `web/` — Orb frontend and frontend tests
- `prometheus/` — Orb backend and analysis engine under the retained internal Python package name
- `tests/` — backend tests
- `scripts/check-vercel-env.mjs` — frontend production API-origin guard
- `Dockerfile` — Render backend image and startup command
- `vercel.json` — frontend deployment settings
- `.env.example` — safe configuration template
- `HANDOFF.md` — implementation history and validation notes
