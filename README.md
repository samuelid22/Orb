# ORB

Orb is an AI-powered creative intelligence platform built for the Arbitrum
Open House Online Buildathon. It reconstructs plausible prompts from visual
references, composes new prompts from them, and enhances existing prompts.

This project reuses the proven Prometheus analysis engine (FFmpeg/FFprobe
structural analysis, Gemini vision analysis, prompt reconstruction, remix) but
is an independent project with its own frontend, branding, and infrastructure.

## Product modes

| Mode | Status | Description |
| --- | --- | --- |
| Decode | Local testing or testnet credits | Reconstruct a plausible prompt from JPEG, PNG, WebP, or a supported video. |
| Compose | Local testing or testnet credits | Create a new prompt from an image or video reference. |
| Enhance | Local testing or testnet credits | Improve an existing text prompt with optional preferences. |

All three require a real provider key on the backend. Orb does not present
mock analysis as a real result. Exact original creator prompts cannot be
guaranteed.

## Payments

**Arbitrum Sepolia TESTNET ONLY.** Orb credits are demo credits without
real-money value. A wallet needs Arbitrum Sepolia testnet ETH for the transfer
and gas. One successful Decode, Compose, or Enhance consumes one credit.

Orb uses an injected EIP-1193 wallet and a one-time signed, domain-bound,
five-minute challenge. Only the recovered wallet address receives a one-hour
in-memory browser session. The server stores a hash of the session token.
This stage supports externally owned wallets that can use `personal_sign`;
contract wallets are not yet supported.

The server issues 15-minute quotes for 1, 3, or 5 credits at the configured
testnet ETH price. The wallet sends native testnet ETH directly to a dedicated
configured receiving wallet, with a unique quote ID in transaction data.
The backend verifies the Arbitrum Sepolia chain ID, receipt status, canonical
block and confirmations, sender, destination, exact value, transaction data,
and that the receiver has no contract code. A unique transaction-hash database
constraint prevents duplicate grants. No Orb private key or contract is needed.
The receiver should be a **dedicated Orb testnet wallet**; do not reuse any
Prometheus account.

Credits, quotes, purchase grants, sessions, and reservations use SQLite
locally and Supabase Postgres in production. Local completed results remain
files; production completed results are Postgres JSONB. Both ledger stores
enforce uniqueness and nonnegative balances. An AI job reserves one credit
atomically, consumes it after a durable result is written, or releases it on
failure. Repeated requests use idempotency keys; startup reconciles
interrupted reservations against saved results. Render restarts cannot erase
production prompts or credit state. Paid job status and results require the
authenticated wallet session. Uploaded media and extracted frames are
temporary in production; recovered results include prompt and analysis text,
without media previews.

The inherited Nimiq payment code remains dormant. It is enabled only by an
explicit local testing flag for inherited tests and is not used by Orb credits.

### Configure testnet credits

Populate only the server-side environment with these values (see
`.env.example`):

| Variable | Requirement |
| --- | --- |
| `ORB_CREDITS_ENABLED` | `1` only when all settings are ready. |
| `ORB_PUBLIC_ORIGIN` | Exact browser origin, such as `http://127.0.0.1:5174` locally or your HTTPS origin later. |
| `ORB_ARBITRUM_RPC_URL` | Trusted HTTPS Arbitrum Sepolia JSON-RPC endpoint. |
| `ORB_CREDIT_RECEIVER` | Dedicated Orb Arbitrum Sepolia receiving wallet address (EOA). Never a private key. |
| `ORB_CREDIT_PRICE_WEI` | Default `1000000000000` wei (0.000001 testnet ETH) per credit. |
| `ORB_PAYMENT_CONFIRMATIONS` | Default `3`; backend checks canonical block and depth. |
| `ORB_CREDIT_DB` | Optional local SQLite path, default `api_output/orb_credits.sqlite3`. |
| `ORB_DATABASE_URL` | Production-only server-side Supabase Postgres URL; never a `VITE_*` value. |

To exercise paid gating locally, set `ORB_AI_LOCAL_TESTING=0` and
`ORB_CREDITS_ENABLED=1`, use the browser origin in `ORB_PUBLIC_ORIGIN`, and
provide a dedicated receiver and RPC. Do not expose a local bypass to a
public host. Testnet transfers require a funded user wallet; no private key
is needed by Orb. This repository has not deployed a contract or sent a
testnet payment on your behalf.

## First public deployment preparation

This repository is prepared for a separate Orb frontend on Vercel and a
separate Orb API on Render. Deployment, repository publishing, paid resource
creation, and testnet transfers require the owner's approval. Do not reuse a
Prometheus service, database, account, or environment group.

### Persistent credit storage with Supabase Postgres

Create an independent Supabase project and obtain its server-side Postgres
connection URL. For a persistent Render backend that needs IPv4 connectivity,
Supabase's [connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
recommends the **shared Session pooler**. Set its URL in `ORB_DATABASE_URL` on
an independent **Render Free Docker web service**. Render's
[Free service guide](https://render.com/docs/free) confirms that local files
are lost on restart or spin-down, so no Render disk is required or used here.
Startup fails if production lacks a valid Postgres URL or cannot connect. The
URL is passed to Psycopg with TLS required by default; an explicit
`sslmode=require`, `verify-ca`, or `verify-full` is also accepted. Keep the
database password out of source, Vercel, logs, and chat.

On first connection, Orb creates a dedicated `orb` schema and version 1
tables in one transaction guarded by a Postgres advisory lock. Later starts
accept exactly schema version 1; they do not drop or rebuild existing tables.
The database user needs permission to create that schema and its tables.
Back up this database. Any future schema change needs an explicit versioned
migration. Existing local SQLite credits are **not** imported automatically;
plan and audit a one-time migration if they must carry over.

The Docker image installs FFmpeg/FFprobe and runs one Uvicorn worker on
`0.0.0.0:${PORT:-10000}`. Let Render set `PORT`; set the health-check path
to `/api/ready`. The output and upload directories are temporary inside
`/tmp` and are removed after processing. Postgres stores the deliverable
prompt/analysis JSON before credit settlement. On restart, Orb consumes a
reserved credit only when that result exists in Postgres; otherwise it
releases the reservation. A result remains available through its paid job
ID after a Render restart. Keep one backend instance for this initial
deployment so restart reconciliation cannot race an active worker.

Enter these variables **manually in the independent Orb Render service**.
Use placeholders here; never add real values to source or `VITE_*` settings.

| Variable | Production value |
| --- | --- |
| `ORB_ENV` | `production` |
| `ORB_AI_PROVIDER` | `gemini` |
| `ORB_AI_MODEL` | `gemini-3.5-flash-lite` (or the verified working model) |
| `GEMINI_API_KEY` | `<server-side-secret>` |
| `ORB_AI_LOCAL_TESTING` | `0` |
| `ORB_CREDITS_ENABLED` | `1` |
| `ORB_PUBLIC_ORIGIN` | `https://<exact-Orb-Vercel-production-domain>` |
| `ORB_ARBITRUM_RPC_URL` | `https://<trusted-Arbitrum-Sepolia-RPC>` (server-side, including any provider credential) |
| `ORB_CREDIT_RECEIVER` | `0x<dedicated-Orb-Arbitrum-Sepolia-EOA>` (public address only) |
| `ORB_CREDIT_PRICE_WEI` | `1000000000000` for the current one-credit testnet price |
| `ORB_PAYMENT_CONFIRMATIONS` | `3` |
| `ORB_DATABASE_URL` | `postgresql://<user>:<password>@<Supabase-host>:<port>/<database>?sslmode=require` (server-side secret) |
| `ORB_UPLOAD_DIR` | `/tmp/orb_uploads` |

Do not set `ORB_ENABLE_NIMIQ_PAYMENTS`, any `PROMETHEUS_*` setting, a wallet
private key, or an Orb `.env` file on Render. Production startup rejects
inherited Prometheus configuration. CORS allows only `ORB_PUBLIC_ORIGIN`,
which must be the exact HTTPS browser origin used for wallet challenges.
Preview domains need a separate explicitly configured backend or will not
be able to authenticate; do not use a wildcard origin.

### Independent Vercel frontend

Create a new Orb Vercel project with this repository's **root directory** as
the project root. `vercel.json` selects Vite, runs `npm run build:vercel`, and
publishes `web_dist`. Set only this frontend-safe production variable:

| Variable | Production value |
| --- | --- |
| `VITE_API_BASE_URL` | `https://<independent-Orb-Render-service>.onrender.com` (origin only) |

The Vercel build fails if this value is missing, non-HTTPS, localhost, or has
a path or credentials. Do not put Gemini keys, RPC credentials, or wallet
secrets in Vercel. Local `npm run dev` still proxies `/api` to loopback port
8790; production browser requests use `VITE_API_BASE_URL` directly. Confirm
that the final Vercel domain exactly matches Render's `ORB_PUBLIC_ORIGIN`
before allowing wallet payments.

### Manual setup sequence

1. After approving independent infrastructure, create an Orb-only Supabase
   project. In **Connect**, copy the Postgres **Session pooler** URI and add
   `sslmode=require` if it is absent. Keep the URI private; no Supabase
   service-role API key is needed. Ensure its database user can create an
   `orb` schema. Do not manually create the tables.
2. Create an independent Render **Free** Docker web service from Orb's
   `Dockerfile`, with no disk and one running instance. Set the server-side
   variables below, including `ORB_DATABASE_URL`, and `ORB_UPLOAD_DIR=/tmp/orb_uploads`.
   Set its health check to `/api/ready`. Verify startup creates schema version
   1 and that `/api/health` and `/api/orb/credits/config` report the expected
   provider, paid mode, and Arbitrum Sepolia chain. A failed database
   connection must prevent startup.
3. Create the separate Vercel project, set only `VITE_API_BASE_URL` to the
   exact Render HTTPS origin, and set Render's `ORB_PUBLIC_ORIGIN` to the exact
   Vercel HTTPS browser origin. Verify CORS and wallet signing from that origin.
4. With separate approval for a testnet transfer, run the one-credit purchase
   and Decode check below, then restart Render and verify the paid result and
   balance still load from Postgres. Review backup and schema migration access
   before using real user wallets.

### Approval and post-deployment checks

After approving an independent repo push and creating the independent
Supabase project, create the Render Free backend, enter its variables, and
confirm public
`/api/health` reports Gemini and `orb_ai_access=credits`, `/api/ready` reports
`ready`, and `/api/orb/credits/config` reports enabled on chain 421614. Then
create the Orb Vercel project, set `VITE_API_BASE_URL`, and verify its exact
domain matches `ORB_PUBLIC_ORIGIN`. A production `ORB_AI_LOCAL_TESTING=1`,
missing Postgres URL, missing API key, or wrong origin prevents a safe launch.

Only after both deployments are live and the owner authorizes a testnet
payment: connect MetaMask, switch to Arbitrum Sepolia, sign the challenge,
inspect the current balance, buy one testnet credit, wait for verification,
run one Decode, confirm a real Gemini result and exactly one credit consumed,
then restart the backend and confirm the wallet balance and result persist.
No deployment payment success is claimed from automated tests alone.

## Local development

Python 3.12+ and Node 22+ are required.

```powershell
# Backend (terminal 1)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:ORB_ENV="local"
$env:ORB_AI_LOCAL_TESTING="1"
$env:ORB_AI_PROVIDER="gemini"
$env:GEMINI_API_KEY="your-own-development-key"
.venv\Scripts\python -m uvicorn prometheus.api.app:app --host 127.0.0.1 --port 8790
```

```powershell
# Frontend (terminal 2)
npm install
npm run dev
```

Open `http://127.0.0.1:5174`. The dev server binds to loopback and proxies
`/api` to the backend on port 8790. `.env.example` lists the server settings;
the commands above set them explicitly because Uvicorn does not automatically
load `.env`. OpenAI is also supported with `ORB_AI_PROVIDER=openai` and
`OPENAI_API_KEY`. Without a provider key, AI controls remain unavailable.

The AI authorization check runs on the server for every operation. Unpaid
testing requires both local flags and a loopback request. Outside that path,
Decode, Compose, and Enhance require a signed wallet session and reserved
testnet credit. With credits disabled, public AI access remains blocked. Do
not enable local testing flags on a public server.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
npm run test:web
npm run build
```

## Project layout

- `web/` — the ORB frontend (vanilla JS + Vite).
- `prometheus/` — the inherited analysis engine (internal package name kept
  for compatibility; see HANDOFF.md).
- `tests/` — inherited engine tests plus new frontend tests.
