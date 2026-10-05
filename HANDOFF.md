# ORB Project Handoff

ORB is an AI-powered creative intelligence platform for the Arbitrum Open
House Online Buildathon. It reuses the proven Prometheus analysis engine but
is an independent project: new frontend, new branding, separate repository,
separate ports, and no shared deployments.

Absolute path: `C:\Users\USER\Documents\project-prometheus\project-orb`

Prometheus source: `C:\Users\USER\Documents\project-prometheus\ai-video-reverse-engineer`
(main @ `cb05f4b`; left completely unchanged, including its uncommitted work).

## What was copied from Prometheus (working tree, verified byte-identical)

- `prometheus/` — the full backend package: FastAPI app, job manager,
  FFmpeg/FFprobe video tools, pipeline, storage, analyzer (Gemini/OpenAI/
  mock), prompt builder, remix, schema, DTOs, and the payment module
  (see Payment isolation below).
- `tests/` — all engine tests, including the uncommitted
  `test_gemini_analyzer.py` / `test_scene_analysis.py` updates and the
  untracked `tests/test_jobs.py`, matching the uncommitted
  `prometheus/analysis/analyzer.py` and `prometheus/api/jobs.py` changes.
- `main.py`, `config.yaml`, `requirements.txt`, `Dockerfile`,
  `.dockerignore`, `LICENSE`.

## What was deliberately NOT copied

- `.git/` history (new independent repo, no remote configured).
- `.env` files, credentials, private keys.
- `.vscode/` IDE settings, Prometheus docs (`CODEX_HANDOFF.md`,
  `DEPLOYMENT.md`, `REAL_MINI_APP_TESTING.md`, old `README.md`).
- `samples/`, `uploads/`, `output/`, `api_output/`, logs, caches.
- `render.yaml` / `vercel.json` (no deployment connection).
- Prometheus branding assets and its `web/` frontend (Orb has a new one).

## What was created or modified inside Orb

- `.gitignore` — covers `.venv/`, `node_modules/`, `web_dist/`, `.env`,
  local output/upload dirs, caches, IDE files.
- `README.md` — setup, local run, tests, mode-status table.
- `package.json`, `vite.config.js` (dev port 5174, `/api` proxy to
  backend port 8790), `vitest.config.js` (jsdom), `.env.example`
  (no payment credentials; Nimiq enable-flag documented as forbidden).
- `web/index.html`, `web/styles.css`, `web/app.js` — the new ORB
  frontend: white `#FFFFFF` background, `#F5F9FF` surfaces, `#368BE9`
  accents, rounded cards/buttons, responsive layout, text wordmark.
- `web/api-url.js`, `web/api-url.test.js` — API base-URL helper and tests.
- `web/app.test.js` — 8 new interface tests.
- `prometheus/api/app.py` — payment isolation gate only (no analysis
  logic touched): inherited Nimiq payments stay dormant unless
  `ORB_ENABLE_NIMIQ_PAYMENTS=1`; `/api/payments/config` and
  `/api/payments/quotes/{id}/verify` return 503 when disabled.
- `tests/conftest.py` — autouse fixture enabling the flag so the inherited
  payment tests keep exercising that code.
- `tests/test_api.py` — one brand assertion adapted (`"Prometheus"` to
  `"ORB"` in the served-index test); all engine assertions unchanged.

## Frontend structure and modes (Stage 2)

- Header: exact "Orb" wordmark, a small blue ringed planet drawn in SVG
  with a slow CSS rotation and reduced-motion support. The hamburger
  opens a grouped Home / Workspace / Account / Information menu. Home
  returns to the upload screen; About Orb opens a small information
  panel. My Creations, Wallet & Credits, and Settings are static
  "Coming soon" rows.
- Home: the approved Stage 2 mockup's left-aligned badge and hero,
  centered pale-blue upload panel, wide blue Choose file button, and
  compact mode pills below the panel. The three large cards and duplicate
  header mode tabs were removed.
- The panel uses the mockup's "Drop your image or video" heading and
  supporting text, with an additional visible line explaining that Decode
  currently accepts videos only. The picker accepts MP4, MOV, and WebM,
  up to 200 MB. After selection the panel shows the file, service state,
  and Decode action; errors remain visible in the panel.
- Decode is active; Compose and Enhance pills are muted, non-interactive,
  and labeled "Coming soon" for assistive technology.
- Processing: spinner, phase text, stage list, progress bar, error + back.
- Results: title, metadata chips, source preview, scene-by-scene
  thumbnails, and a prompt card that states reconstruction is unavailable
  instead of fabricating one.
- Decode wires to the live backend (`/api/health` → `/api/ready` →
  `/api/upload-ping` gate, single-attempt correlated upload, 64 KB
  readability pre-check, job polling, basic-tier results). Videos only;
  images are rejected with an honest next-stage message. Compose, Enhance,
  prompt reconstruction, and remix have no client path and are visibly
  marked unavailable.
- Vite's local proxy now matches `/api/` endpoints rather than every
  `/api` prefix; this lets `/api-url.js` load in the dev server while
  preserving the backend proxy.
- The white application frame is capped at 1180px and centered on
  desktop. Tablet and mobile widths remain fluid. Mobile adds a 28px
  page gutter below the full frame, plus any bottom safe-area inset;
  the frame uses the dynamic viewport height.
- The menu closes on its toggle, outside click, Escape, or functional
  selection. Keyboard focus reaches Home and About Orb while reserved
  rows remain non-interactive. The menu stays within narrow viewports
  and scrolls internally on short screens.

## Backend functionality preserved

Upload streaming + validation, FFprobe metadata, scene detection, frame
sampling, basic-tier local inspection, staged/gated upload readiness,
single-attempt uploads with attempt IDs, job polling, result DTOs, prompt
reconstruction and remix code (server-side, unexposed), and the payment
module with its replay-protection tests (dormant behind the flag).

## Test results

- Backend: 138 passed (`pytest`), own `.venv`, Python 3.13.
- Stage 1 frontend: 11 passed (`test:web`: 8 app + 3 api-url), jsdom.
  Two failures during development were test-harness issues, not app bugs
  (a label assertion that ignored fast mock resolution, and a queued poll
  stuck behind a real 1500 ms timer); both fixed in the tests.
- `vite build`: clean (`web_dist/`).
- Independent startup smoke test on port 8790: `/api/health` ok
  (`payment_required: false`), `/api/ready` ready,
  `/api/payments/config` 503 as designed.
- Stage 2 frontend: 12 passed (9 app + 3 api-url) with
  `npm run test:web -- --pool=threads --maxWorkers=1`.
  The default Vitest fork pool timed out starting workers on this
  Windows host before running tests.
- Stage 2 production build: `npm run build` passed.
- Stage 2 served-index regression: 1 backend test passed after adapting
  its wordmark assertion to exact "Orb".
- Browser review: desktop 1776×887, tablet 768×1024, and mobile
  390×844. The page had no horizontal overflow at tablet or mobile
  widths. The menu opened and closed, file selection and clearing worked,
  Decode stayed disabled with the backend offline, and service guidance
  appeared. The planet uses a 32-second CSS rotation and a
  `prefers-reduced-motion` override. No end-to-end video analysis was
  run for Stage 2.
- Targeted UI follow-up: 12 frontend tests passed, and `npm run build`
  passed. Browser checks measured an 1180px centered frame at 1600px
  width and a 28px bottom mobile gutter at the end of a 390px-wide page.
  The grouped menu opened and closed by toggle, outside click, and
  Escape; Tab reached its two functional items with visible focus.
  The menu fit 390px and 320px widths and scrolled internally at
  320×400. The existing upload tests still cover file selection,
  readiness, single-attempt upload, error, and result states.

## Local history (no remote)

- `d0391b2` — initial project (engine copy, payment gate, new frontend,
  configs, README).
- `b56b3f7` — this handoff document.
- `e0baa81` — record test-harness fixes in this handoff.
- Stage 2 changes are currently uncommitted in the independent Orb
  working tree. No remote is configured; nothing has been pushed or
  deployed.

## Unresolved issues

- One inherited test needed a one-word brand adaptation (see above);
  no engine behavior was weakened.
- `resume-after-reload` recovery from Prometheus was intentionally left
  out of the Orb frontend for stage 1.
- The internal Python package is still named `prometheus` for
  compatibility; renaming is deferred.
- The Stage 2 homepage adds a visible video-only support line to the
  upload panel because the mockup's image-or-video heading would
  otherwise imply image analysis works. The mockup does not depict the
  opened menu, selected-file state, loading, errors, or results.

## Current priority

Stage 3 code is implemented and its five workflows were verified against a
live Gemini provider locally on 2026-09-24. Stage 4 wallet, testnet credit,
and payment-gating code is implemented locally on 2026-09-25; real on-chain
purchase verification still requires a dedicated receiver and a user-approved
funded testnet wallet transaction. Preserve all uncommitted work. Public
unpaid AI operations remain blocked. The configured default Gemini model
returned provider 503 errors during Stage 3 verification, so live checks used
a temporary process-only model override described below.

### Stage 3 implementation plan (recorded before code changes)

1. Add one server-side authorization function for every real AI entry point.
   Permit unpaid AI only with explicit local development configuration and a
   loopback client; fail closed in production until Stage 4 verifies credits.
   Keep inherited Nimiq tests isolated and Nimiq disabled in normal Orb.
2. Reuse `PrometheusPipeline` for video Decode. Add size/type/content checks
   for JPEG, PNG, and WebP and an Orb multimodal request for image Decode.
   Return real prompt, analysis, and refinements; reject missing providers.
3. Build Compose from analyzed visual evidence (video pipeline or image
   vision request), with a distinct creative synthesis request. Add a
   separate text-only Enhance request with constrained preferences.
4. Integrate mode selection, upload/text workspaces, processing/results,
   copying, and guarded submission into the existing Stage 2 UI.
5. Test each milestone before proceeding, then run all backend/frontend
   suites and production build. Distinguish mock-provider integration tests
   from any genuine provider runs and record missing configuration.

### Stage 3 implementation and verification

- `prometheus/analysis/orb_ai.py` adds distinct image Decode, image Compose,
  video Compose synthesis, and text Enhance calls. It uses the inherited
  Gemini/OpenAI client and retry machinery. Images are sent as real bytes;
  video Compose is grounded in the existing frame-based video report. No
  filename-based or mock output is offered through Orb's new AI routes.
- `prometheus/api/app.py` adds JPEG/PNG/WebP uploads (20 MB and 32 million
  pixel bounds with Pillow content validation), new queued Orb routes, and
  structured prompt/visual-analysis results. Video Decode/Compose reuse the
  inherited FFprobe, segmentation, frame sampling, scene AI, global AI, and
  reconstruction pipeline. It preserves the video limit and multipart upload
  checks. Job errors are generic to clients, with details logged server-side.
- All three Orb operations pass through one `_authorize_ai` boundary before
  work starts. Stage 3 allows real provider calls only with `ORB_ENV=local`,
  `ORB_AI_LOCAL_TESTING=1`, a loopback request and local host, no forwarded
  client, and a configured server-side key. Production returns 402 until
  Stage 4 supplies verified credit authorization. The inherited Nimiq
  service and routes are restricted to explicit local testing; legacy real
  analysis cannot bypass the local/credit gate. Mock legacy analysis is also
  blocked outside explicit local testing.
- `web/index.html`, `web/app.js`, `web/styles.css` activate the three existing
  mode pills without changing the Stage 2 hero or visual identity. Decode and
  Compose share the upload workspace; Enhance has text and preference inputs.
  Results display the generated prompt, real visual evidence when available,
  original text for Enhance, and a working Copy Prompt control. Upload
  precheck, canary, single-attempt behavior, polling, and submission guard
  remain. Missing provider/payment configuration is shown in the UI.
- `requirements.txt` adds Pillow. `.env.example` and `README.md` document
  local-only provider configuration; no credentials were copied. `package.json`
  and `vite.config.js` bind Vite to loopback so its proxy cannot provide local
  unpaid AI access over a LAN. `tests/conftest.py` keeps inherited Nimiq
  tests explicitly local. `tests/test_api.py` now expects a missing key to
  fail before queuing a job.
- New `tests/test_orb_stage3.py` covers JPEG/PNG/WebP validation, image and
  video modes with fake providers, Enhance, provider errors, missing keys,
  forwarded requests, and production payment denial. New
  `tests/test_orb_ai.py` verifies actual image bytes reach both SDK adapters.
  Frontend tests cover mode activation, upload reliability, repeated clicks,
  result display and prompt copy.
- Initial Stage 3 backend suite: **150 passed** (`pytest -q`); existing FastAPI
  `on_event` deprecation warnings remain. Initial frontend suite: **14 passed**
  (`npm run test:web -- --pool=threads --maxWorkers=1 --isolate=false`). A
  concurrent run hit a Windows Vitest worker startup timeout; the reused
  worker run passed. Final `npm run build` passed.
- Browser review measured an 1180px centered frame at 1440px desktop width,
  and at 390px mobile width verified no horizontal overflow, a 28px bottom
  gutter, and a usable Enhance form. With no key, the live local backend
  shows clear configuration guidance and disables AI actions.
- At the time of that initial Stage 3 implementation, genuine end-to-end
  provider analysis had not run. The subsequent live verification is recorded
  below; automated tests still use fake SDK clients or the inherited mock
  analyzer and are identified separately from live results.
- Stage 4 must replace `_authorize_ai`'s local-only allowance with a verified
  Arbitrum Sepolia credit reservation/consumption flow, plus credit UX and
  durable entitlements. Public AI access remains closed. No deployment,
  push, or commit was made.

### Stage 3 live Gemini verification (2026-09-24)

- An existing, ignored Orb `.env` was present and readable. It configured
  `ORB_ENV=local`, `ORB_AI_LOCAL_TESTING=1`, and Gemini with a server-side
  key. The key was loaded only into the backend process environment and was
  never printed, copied into source, or committed. The backend bound to
  `127.0.0.1:8790`, and Vite to `127.0.0.1:5174`. `/api/health` reported
  local AI access with payment not required; `/api/ready` passed.
- The existing default `gemini-3.8-flash` was called for image Decode first,
  but Gemini returned 503 `UNAVAILABLE` after the configured retries, citing
  high demand. Orb displayed a safe error and retry path. Without editing
  `.env` or the tracked default, the backend was restarted with a temporary
  process-only `ORB_AI_MODEL=gemini-3.5-flash-lite`. `/api/health` confirmed
  the actual model for the successful checks. The default model's transient
  availability remains unverified; use an explicit supported model or retry
  when it recovers for further local checks.
- Real sample inputs were generated locally under the ignored
  `uploads/stage3-verification/`: a PNG showing a red/yellow balloon over
  green hills and a three-second MP4 showing a red ball moving across a
  simple landscape. Both were selected through Orb's UI. No mocked provider
  response was used for these five live workflows.
- **Image Decode:** request reached the backend and the live Gemini vision
  call; prompt, image-derived visual analysis, refinements, and original-prompt
  disclaimer appeared. Copy Prompt matched the displayed prompt exactly.
- **Video Decode:** the inherited FFprobe, scene/frame sampling, and Gemini
  analysis ran. Orb showed video metadata, scene evidence, reconstruction
  prompt, and disclaimer. Copy Prompt matched the displayed generation prompt.
- **Image Compose:** live Gemini analyzed the balloon reference and returned
  a distinct creative prompt with evidence and refinements. Copy matched.
- **Video Compose:** frame-based Gemini analysis and a distinct composition
  request returned a creative video prompt with evidence. Copy matched.
- **Enhance:** live Gemini improved a text prompt with selected output/style/
  detail preferences, preserved the original idea, and displayed original and
  enhanced text. Copy matched. A second live run confirmed the corrected
  prompt-specific loading label.
- During live review, two small fixes were made: `web/app.js` now shows
  operation-appropriate processing labels (including Enhance), and video
  Decode in `prometheus/api/app.py` returns only the inherited report's
  generation-prompt section via `prometheus/analysis/orb_ai.py`. The latter
  also removes inherited `INFERENCE:`/`OBSERVATION:` prefixes from result
  evidence. Frontend and backend tests were extended for these behaviors.
- Disabled actions during processing and exact clipboard contents were checked
  in the browser. At 1440px desktop width the app frame measured 1180px;
  at 390px mobile width there was no horizontal overflow and the bottom gap
  measured 28px. The menu opened and closed with Escape. A remote `Host` and
  a forwarded-client request each returned 402, while explicit local testing
  succeeded. Automated tests also cover disabled local testing and production
  denial. No payment code was added.
- Final backend suite: **151 passed**, 88 inherited FastAPI `on_event`
  deprecation warnings (`.venv\Scripts\python.exe -m pytest -q`). Final
  frontend suite: **15 passed** (`npm run test:web -- --pool=threads
  --maxWorkers=1 --isolate=false`). `npm run build` passed. The first backend
  run caught an overly specific assertion against its mock video fixture;
  after correcting that assertion and adding a direct extraction test, the
  full suite passed. Browser checks above are live-provider checks, separate
  from these automated tests.
- The backend and Vite processes were stopped after verification. No push,
  commit, or deployment was made. The ignored local sample files and logs
  remain for reproducibility; the exact configured key was checked as absent
  from those logs. Stage 4 still needs verified Arbitrum Sepolia credit
  authorization before public AI access can open.

## Later stage work

1. Resolve or explicitly override the default model's 503 availability for
   future local checks; all five workflows succeeded with the temporary
   `gemini-3.5-flash-lite` override.
2. Orb credit system on Arbitrum Sepolia with its own entitlement model;
   keep Nimiq code dormant.
3. Deployment configuration (new hosting, HTTPS, production RPC or model
   endpoints) — nothing is deployed or pushed anywhere yet.

### Stage 4 implementation plan (recorded before code changes, 2026-09-25)

1. Keep the existing Orb AI routes and local-only bypass. Introduce a
   dedicated persistent SQLite credit ledger and a bearer session backed by
   a one-time, expiring, origin-bound wallet signature. Require an authenticated
   session for balance, quotes, verification, and paid AI work.
2. Use a dedicated Arbitrum Sepolia receiver configured in Orb's environment.
   A server quote binds wallet, credit count, exact native testnet ETH amount,
   expiry, and transaction data. Verify RPC chain ID, receipt success and
   confirmations, canonical block, sender, receiver, amount, empty/expected
   transaction semantics, and quote data before granting; enforce unique
   transaction hash in the database. No contract or private key is needed.
3. Reserve one credit transactionally per AI idempotency key after validation.
   Finalize only after a result file is written; release on failure. Reconcile
   interrupted reservations against delivered result files after restart.
   Protect paid job status/results by wallet session and preserve the local
   development bypass and inherited Nimiq isolation.
4. Add a focused wallet/credits panel to the existing menu, a small testnet
   notice, network switching, balance and transaction states. Keep the current
   upload, results, desktop width, mobile spacing, and menu behavior.
5. Test signature replay, receipt rejection, duplicate grants/requests,
   concurrent reservations, failures and restart recovery with a mocked RPC;
   rerun backend and frontend suites and production build. Record clearly
   whether a real Arbitrum Sepolia transaction could be performed.

### Stage 4 implementation and verification (2026-09-25)

- `prometheus/api/orb_credits.py` adds a SQLite WAL credit ledger with durable
  challenges, hashed bearer sessions, wallet balances, payment quotes, unique
  verified purchases, and unique per-wallet idempotency reservations. It uses
  `eth-account` for EIP-191 wallet signature recovery and binds sign-in to an
  exact configured browser origin, Arbitrum Sepolia chain ID 421614, a random
  one-time nonce, and a five-minute expiry. Sessions expire after one hour.
  Contract-wallet signatures are not supported yet.
- The payment uses native Arbitrum Sepolia testnet ETH to a dedicated
  configured EOA, with unique quote data included in the transaction input.
  Quotes offer 1, 3, or 5 demo credits, defaulting to 0.000001 testnet ETH per
  credit and three confirmations. The backend independently reads the chain
  ID, transaction, receipt, canonical block, confirmation depth, receiver
  code, sender, recipient, exact value, input data, success status, and block
  timestamp. Database uniqueness prevents granting the same transaction or
  quote twice. No contract, payment key, or Prometheus account is used.
- `prometheus/api/app.py` adds wallet challenge/sign-in, balance, quote, and
  verification routes. Decode, Compose, and Enhance now use the existing
  authorization boundary: explicit loopback-only local testing still bypasses
  credits; otherwise a signed wallet session and one available testnet credit
  are required. Uploads are validated before credit reservation. SQLite write
  transactions reserve one credit atomically; job success finalizes only after
  a result is saved, and job failure releases it. Duplicate idempotency keys
  return the original job, while altered content under the same key is rejected.
  On restart, saved results finalize interrupted reservations; missing results
  release them. Paid status, result, and media reads require the wallet session.
  The inherited `/api/analyze` route remains local-only and cannot use wallet
  credits to bypass the new routes. Nimiq remains dormant.
- `web/wallet.js`, `web/index.html`, `web/app.js`, and `web/styles.css` add a
  compact Wallet & Credits panel under the existing menu, network detection and
  switch, wallet signing, available balance, quote/purchase/verification states,
  persistent pending transaction reference in session storage, and visible
  TESTNET ONLY/demo/no-real-money messaging. The frontend keeps its session
  token in memory and reloads paid media with authenticated requests. It
  retains an active paid job ID in session storage so results can be resumed
  after reconnecting. AI actions require an available credit in the UI, with
  a visible wallet/buy action when empty; the server remains authoritative.
  Ambiguous manual retries reuse an idempotency key. The approved home layout,
  responsive frame, menu, upload canary, and result experience remain.
- `requirements.txt` adds `eth-account`; `.env.example` and `README.md` document
  safe Arbitrum Sepolia settings, a dedicated receiving EOA, SQLite single
  instance limits, and the local paid-gate test procedure. The existing local
  `.env` was not edited. No credentials, private keys, or production backend
  URL were added to source.
- **Mocked-chain tests only:** `tests/test_orb_credits.py` uses generated
  disposable test wallets and a fake JSON-RPC provider. It covers valid and
  invalid signatures, nonce replay/expiry, wrong origin, wrong chain, failed
  or unrelated receipts, insufficient value, wrong input or receiver, missing
  confirmations, noncanonical blocks, duplicate grants, concurrent
  reservations, idempotency, AI failure release, and restart reconciliation.
  Paid API tests exercise image Decode, image Compose, and Enhance with a fake
  AI service; existing Stage 3 tests continue covering video and local bypass.
  `web/app.test.js` verifies wallet network switching, payment-flow UI states,
  authenticated paid upload, and active-job recovery reference. These tests
  do not prove a real Arbitrum transaction or live Gemini in paid mode.
- Final automated results: **166 backend tests passed** (`pytest -q`), with 92
  inherited FastAPI `on_event` deprecation warnings; **16 frontend tests
  passed** (`npm run test:web -- --pool=threads --maxWorkers=1 --isolate=false`);
  `npm run build` passed. Visual check: frame width 1180px in a 1440px desktop
  viewport, no mobile horizontal overflow at 383px, about 28px mobile bottom
  gap, and wallet panel within both viewports. The loopback preview servers
  were stopped after review.
- **Not verified on-chain:** no dedicated receiver or funded user wallet was
  provided, and the existing `.env` remains in local AI testing mode. No real
  Arbitrum Sepolia transfer, real wallet signature, or paid live-Gemini request
  was performed. To complete live verification, configure
  `ORB_CREDITS_ENABLED=1`, an exact `ORB_PUBLIC_ORIGIN`, trusted HTTPS
  `ORB_ARBITRUM_RPC_URL`, dedicated EOA `ORB_CREDIT_RECEIVER`, and persistent
  `ORB_CREDIT_DB`; set `ORB_AI_LOCAL_TESTING=0`; start Orb locally; connect a
  funded Arbitrum Sepolia wallet, sign the challenge, and approve a one-credit
  testnet transfer in the wallet. Do not provide a private key. The user must
  authorize and execute that transaction before claiming on-chain success.
  No deployment, push, or commit was made.

## 2026-09-25 local backend restart

- Confirmed the original Orb listener on `127.0.0.1:8790` belonged to Orb
  Uvicorn processes 13064/16152, then stopped them. Their environment had not
  loaded Orb's `.env`; live health had reported `provider=mock` and
  `orb_ai_access=configuration_required`.
- Installed `python-dotenv` **only in the existing Orb `.venv`** because
  Uvicorn's `--env-file` option required it. No source or dependency manifest
  was changed for this runtime repair. A rebuilt virtual environment will need
  `python-dotenv` installed again to use that launch option.
- Restarted Orb from its project directory with `uvicorn
  prometheus.api.app:app --host 127.0.0.1 --port 8790 --env-file .env`.
  The launch process uses a process-only `ORB_AI_LOCAL_TESTING=1`; no key was
  printed or copied. The `.env` file itself was left untouched and contains
  three `ORB_AI_LOCAL_TESTING` entries, with the last set to `0`. Without the
  process override, a fresh load would disable local AI testing.
- Final live `GET /api/health`: `status=ok`, `provider=gemini`,
  `model=gemini-3.5-flash-lite`, `orb_ai_access=local`;
  `configuration_required` is resolved. `GET /api/ready` returned HTTP 200
  with `status=ready`. The current backend parent process was PID 10212 and
  its listener child PID 13748 at verification time; PIDs may change later.
- This was a configuration/startup check, not a live AI workflow or payment
  verification. Prometheus, payment configuration, and source files were not
  modified; nothing was deployed, pushed, or committed.

## 2026-09-25 Arbitrum Sepolia local restart

- After the user updated Orb's `.env`, stopped the verified Orb Uvicorn
  processes and restarted from the Orb project with `--env-file .env` on
  `127.0.0.1:8790`. Inherited Orb variables were removed from the launch
  process so the updated file took effect; no process-only local bypass was
  applied. The serving backend PID was 9020 under parent 5768 at verification.
- Read-only inspection of the serving process confirmed `ORB_ENV=local`,
  `ORB_CREDITS_ENABLED=1`, `ORB_AI_LOCAL_TESTING=0`, Gemini provider,
  `gemini-3.5-flash-lite` model, the configured browser origin matching
  `http://127.0.0.1:5174`, and presence of the server-side Gemini key, RPC
  URL, and receiving address. No secret value was displayed.
- Read-only calls to the configured RPC returned HTTP 200 for `eth_chainId`,
  `eth_blockNumber`, and `eth_getCode`; chain ID was 421614 (Arbitrum Sepolia).
  The receiving address passed syntax and nonzero checks and had no contract
  code at the checked block. These checks do not establish who controls it.
- Replaced the mislaunched Orb Vite process on port 5173 with Orb Vite on
  `127.0.0.1:5174` (PID 9684 at verification). Frontend HTTP and proxied
  `/api/health` and `/api/orb/credits/config` returned successfully.
- Backend `/api/health` returned `status=ok`, `provider=gemini`,
  `orb_ai_access=credits`; the credit config endpoint reported enabled,
  testnet only, chain 421614, a one-credit price of 1000000000000 wei,
  and three confirmations. `/api/ready` returned `ready`. Wallet challenge,
  sign-in, balance, quote, and quote verification routes were registered;
  unauthenticated balance access returned HTTP 401.
- No wallet signature, real payment, credit grant, or paid AI operation was
  performed. A user-controlled wallet and testnet ETH are still needed for
  live payment verification. No source files, Orb payment settings, or
  Prometheus files were changed; nothing was deployed, pushed, or committed.

## 2026-09-25 Stage 5 production preparation (not deployed)

- The user reports a subsequent successful live local MetaMask signature,
  Arbitrum Sepolia credit purchase, and paid Decode. This Stage 5 work did not
  repeat that real transaction or spend testnet ETH.
- Selected architecture: a **new paid, single-instance Render Docker web
  service** with a persistent disk mounted at `/var/data`. Keep the SQLite
  ledger at `/var/data/ledger/credits.sqlite3` and saved AI results at
  `/var/data/results` on the same disk. Keep temporary uploads at
  `/tmp/orb_uploads`. Render's disk persists across deploys/restarts but
  precludes horizontal scaling and zero-downtime deploys. No Render service
  or disk was created.
- `prometheus/api/orb_deployment.py` and `prometheus/api/app.py` now fail
  public startup unless `ORB_ENV=production`, Gemini and its key are explicit,
  `ORB_AI_LOCAL_TESTING=0`, `ORB_CREDITS_ENABLED=1`, the exact HTTPS Orb
  frontend origin is set, and both ledger/results paths are under an actual
  attached disk mount. Production refuses inherited Prometheus variables or
  Nimiq payment activation. Local behavior remains supported. Production
  CORS allows only `ORB_PUBLIC_ORIGIN`. Legacy `/api/uploads`, `/api/inspect`,
  and `/api/analyze` paths are unavailable in production.
- Orb result JSON is written with a temporary file, fsync, and atomic replace
  before credit settlement. Restart reconciliation now consumes a reserved
  credit only for a complete, matching prompt result; incomplete/missing
  results release the reservation. The ledger's SQLite transactions and
  unique payment/idempotency constraints remain unchanged.
- `vercel.json`, `package.json`, and `scripts/check-vercel-env.mjs` prepare a
  separate Vercel Vite build from the repo root into `web_dist`. Its build
  requires `VITE_API_BASE_URL` to be a nonlocal HTTPS backend origin. Local
  Vite's loopback proxy remains development-only. `.env.example` and
  `README.md` document Render/Vercel setup using placeholders, no secrets.
- Validation: **169 backend tests passed** with 94 inherited FastAPI
  deprecation warnings, using the already-installed local FFmpeg; **16
  frontend tests passed**. Guarded Vercel production build passed with a
  non-secret placeholder API origin. Missing/localhost API origins failed the
  build guard. Built assets contained the placeholder backend origin and no
  localhost backend or backend secret variable names. `.env` is ignored and
  untracked; the exact locally configured Gemini key was absent from source
  and built assets. The configured RPC currently matches the intentionally
  public Arbitrum Sepolia wallet-network endpoint already in the frontend;
  it has no credential-bearing userinfo, query, or fragment. A future
  credential-bearing RPC URL must remain server-side. `git diff --check`
  found no whitespace errors.
- The computer automation service timed out, so headless Edge was used for
  read-only screenshots of Orb's local page at desktop (1440px) and tablet
  (about 780 CSS px) widths; both retained the approved layout. Edge's
  minimum layout width made its attempted 390px screenshot a crop rather than
  a valid mobile viewport. Responsive CSS and UI code were unchanged;
  existing frontend tests passed, and Stage 4 had a prior 383px mobile visual
  check. Docker is unavailable locally, so the Render container was not built
  in this turn. Render mount behavior, Vercel/Render origins, wallet flow,
  disk persistence, and real production payment still require verification
  after deployment. Monitor disk usage, backup/recovery, and abuse of public
  endpoints during the first demo.
- Pre-existing uncommitted Orb changes were preserved. The already-running
  local Orb services were not restarted with these Stage 5 source changes.
  Orb is its own Git root but currently has no configured Git remote; all
  earlier Stage 3/4 work and this preparation remain uncommitted. An
  independent repository and reviewed commit/push are approval-gated steps.
  No source was changed outside the independent Orb project; no commit,
  push, deployment, paid infrastructure creation, or fund transfer occurred.

## 2026-09-25 Stage 5.1 local Git snapshot

- Reviewed the complete pending Orb source, frontend, test, configuration, and
  deployment-preparation changes for Stages 3 through 5. Confirmed Orb has its
  own Git root and no configured remote. The original Prometheus checkout is a
  separate sibling repository; its pre-existing changes were inspected only
  and were not modified.
- Secret and runtime-file audit: Orb's populated `.env` is ignored and
  untracked. No Gemini key bytes, private key block, seed phrase, runtime
  database, generated upload, or other private runtime file belongs in the
  snapshot. The only matching RPC URL in frontend code is the public Arbitrum
  Sepolia wallet-network endpoint without credentials. Stage only the reviewed
  source, test, documentation, and deployment-config files explicitly.
- Complete backend suite: **169 passed** with 94 inherited FastAPI deprecation
  warnings. The first sandboxed run could not access the installed FFmpeg;
  rerunning with that existing binary on the process PATH passed. Complete
  frontend suite: **16 passed** across two files, using one Vitest thread after
  the default worker pool timed out. Guarded `npm run build:vercel` passed with
  a safe placeholder HTTPS API origin; no production endpoint was created.
- Generated pytest directories were removed before staging. Record the final
  local commit hash and clean working-tree status in the task report. No push,
  deployment, infrastructure creation, or testnet transaction was performed.


## 2026-09-26 Stage 5.2 Supabase Postgres preparation (not deployed)

- Production persistence is now direct server-side Postgres through Psycopg;
  Render Free keeps only processing files in temporary storage. Local
  development remains SQLite with local result files. Production startup
  requires `ORB_DATABASE_URL`, paid credits, Gemini, an exact HTTPS browser
  origin, and `ORB_AI_LOCAL_TESTING=0`. No persistent Render disk or
  `ORB_DATA_DIR`/`ORB_CREDIT_DB`/`ORB_OUTPUT_DIR` production setting is
  required. A missing or unreachable Postgres database fails startup; there
  is no production in-memory or SQLite fallback.
- `prometheus/api/orb_database.py` owns a versioned `orb` Postgres schema
  and shared connection interface. The initial migration creates challenges,
  sessions, balances, quotes, purchases, reservations, and JSONB results under
  an advisory transaction lock. Database checks/unique constraints prevent
  negative balances, duplicate payment grants, and duplicate idempotency
  keys. The shared `CreditService` still verifies chain receipts, reserves
  atomically, settles once, and releases failed jobs.
- Completed paid result JSON is committed to Postgres before credit
  consumption. On restart, reconciliation consumes a reserved credit only if
  its complete matching result survives in Postgres; otherwise it releases
  the reservation. A status/result request can also finish settlement after
  a transient settlement failure. Public results retain prompt, analysis,
  and compact scene metadata; source media and frames are not persisted, so
  production preview media is unavailable after processing. Temporary
  upload and pipeline directories are cleaned after jobs.
- `README.md`, `.env.example`, and `requirements.txt` now document the
  server-only Supabase Postgres URL, TLS, Psycopg, Render Free, automated
  schema initialization, and exact manual deployment sequence. Supabase's
  shared Session pooler is documented for IPv4 Render connectivity. Existing
  local SQLite credits are not migrated automatically; perform an audited
  one-time data migration if they must carry into production. No Supabase
  project, Render service, Vercel site, or external transaction was created.
- Validation: **175 backend tests passed**, including existing SQLite and
  video tests plus mocked Postgres-path schema/transaction/recovery tests;
  **16 frontend tests passed**; guarded Vercel production build passed with
  a placeholder HTTPS API origin. The first full backend run exposed a
  two-second asynchronous test timeout; that test was given a bounded
  15-second deadline and the complete suite then passed. FastAPI emitted
  98 inherited deprecation warnings. No live Postgres connection, Supabase
  migration, live Gemini call, or real Arbitrum transaction was performed in
  this stage. A real Supabase connection, restart recovery check, and paid
  testnet workflow remain required after approved infrastructure creation.
- At the end of Stage 5.2 implementation, Orb changes were uncommitted and
  unpushed. The original Prometheus checkout, its history, and deployments
  were not modified.

## 2026-09-26 Stage 5.2 local commit audit

- Reviewed the complete Orb Stage 5.2 diff and ran the full validation again:
  **175 backend tests passed**, **16 frontend tests passed**, and the guarded
  production frontend build passed with a placeholder HTTPS API origin.
- The local `.env` remains ignored. The commit candidate contains no
  configured Gemini key, RPC secret, database URL, wallet private key, seed
  phrase, SQLite database, uploads, generated results, or runtime data.
  Credential-shaped URLs in tests use explicit `db.example.invalid`
  placeholders. No live Postgres or Supabase test was performed in this audit.
- This audit prepares one local Orb commit only; no push, deployment,
  infrastructure creation, or testnet transaction is part of this step.

## 2026-09-26 Wallet authentication UI state fix (local, not deployed)

- Fixed the Wallet & Credits button in `web/wallet.js`: an authenticated
  session now displays **Connected**; a connected account without valid Orb
  authentication displays **Sign again**; no selected account displays
  **Connect and sign**. The balance and payment interface remain unchanged.
- The signed backend session is stored in browser session storage with its
  server expiry, then checked against the currently selected MetaMask account
  and the authenticated backend balance endpoint on reload. A valid session
  restores without another signature. Expiry, backend 401, or account change
  clears stale UI state and requires a fresh signed challenge. An account
  change during a pending signature cannot authenticate the former account.
  A temporary backend failure displays **Retry session** and rechecks the
  saved token without requiring another signature.
- Updated the existing paid-flow frontend fixture and added dedicated wallet
  state tests in `web/wallet.test.js`. Full frontend suite: **24 passed** in
  3 files. Guarded production frontend build passed using a placeholder
  HTTPS API origin. No backend code, Prometheus code, payment configuration,
  deployment, or push was changed in this step.

## 2026-09-26 Wallet disconnect (local, not deployed)

- Added **Disconnect wallet** to Wallet & Credits, visible only for an
  authenticated Orb session. Clicking it immediately clears the browser's
  bearer token, authenticated address, displayed balance, pending payment,
  and saved paid-job pointer. A per-tab disconnected marker keeps the panel
  at **Connect and sign** after reload even if MetaMask still exposes the
  previously permitted account. Reconnecting uses the existing account
  request, signed challenge, and backend session flow.
- Added `POST /api/orb/wallet/logout`. It requires the exact configured
  browser origin and a valid bearer session, then deletes only that session
  from Orb's persistent sessions table. Other sessions and credit balances
  are unaffected. The frontend attempts MetaMask's
  `wallet_revokePermissions` for `eth_accounts` after local logout; an
  unsupported or rejected request does not undo logout. No transaction or
  token approval revocation is attempted. If backend revocation cannot be
  confirmed, the UI reports that local logout completed and the old server
  session will expire.
- Validation: **26 relevant backend tests passed** across wallet credits,
  mocked Postgres adapter, and deployment guard; **26 frontend tests passed**
  across 3 files; guarded production frontend build passed with a placeholder
  HTTPS API origin. No live Postgres or deployed-browser verification was
  performed. At this validation point, Orb changes were uncommitted and
  undeployed; Prometheus was not modified.

## 2026-09-26 Wallet UX commit audit

- Reviewed the complete pending wallet authentication and disconnect diff,
  including the earlier **Connected** state fix. Full backend suite:
  **177 passed**. Full frontend suite: **26 passed** in 3 files. The first
  frontend runner attempt timed out before starting a worker or executing
  tests; a standalone retry passed. The guarded production frontend build
  passed with a placeholder HTTPS API origin.
- The populated `.env` remains ignored. The nine-file Orb commit candidate
  contains no configured Gemini key, database URL, RPC credential, wallet
  private key, seed phrase, runtime database, upload, or generated result.
  The Arbitrum RPC literal in the wallet network metadata is public; any
  credential-shaped database URLs in tests use invalid-domain placeholders.
  The original Prometheus checkout was not modified.
- This audit supports the requested single Orb wallet UX commit and push to
  `origin/main`. It does not authorize or perform deployment.

## 2026-09-26 Paid job session-expiry recovery (local, not deployed)

- A 401 from a paid job-status or result request now pauses polling immediately,
  retains the saved job ID, and opens the existing Wallet & Credits sign-in
  control with a clear session-expiry message. It does not submit another AI
  operation, reserve another credit, or mark the job failed.
- After a new signed session and successful balance check, polling resumes for
  the saved job only when the authenticated wallet matches the saved owner.
  The backend's existing wallet ownership check remains in force. A completed
  Postgres result can be read after reauthentication; a released job displays
  its error and refreshes the restored credit balance. A stale 401 from an old
  token cannot invalidate a newer session.
- The frontend now allows `resumePaidJob` to restart a job paused for auth even
  while `currentJobId` is retained. Intentional Disconnect still deletes the
  saved job pointer. The server session TTL remains 3600 seconds; no payment,
  video-limit, backend authorization, or deployment configuration changed.
- Added frontend tests for immediate 401 pause, saved-job retention, same-wallet
  signed recovery, wrong-wallet refusal, one-upload reuse, durable-result
  display, and released-balance refresh. Added backend tests for expired-token
  rejection, same-wallet result recovery, wrong-wallet 404, one settlement,
  and released-credit restoration. Existing Disconnect tests still pass.
- Validation: full backend suite **179 passed** (104 existing FastAPI
  deprecation warnings); full frontend suite **29 passed** in 3 files; guarded
  Vercel build passed with a placeholder HTTPS Orb API origin. An initial
  sandboxed pytest attempt failed before setup due temp-directory permissions,
  and an initial Vitest fork attempt timed out before executing tests; both
  suites passed using the supported test access and a single thread worker.
  No live production job or Supabase query was performed, and nothing was
  deployed, pushed, or committed in this change.

## 2026-09-27 Arbitrum Sepolia wallet fee rejection (local, not deployed)

- Audited Buy Credits: Orb's `eth_sendTransaction` request already contains only
  the authenticated `from` address, server-quoted `to`, exact hex `value`, and
  quote `data`. It contains no `gas`, `gasPrice`, `maxFeePerGas`, or
  `maxPriorityFeePerGas`. The quote `data` must remain because the backend
  checks the on-chain input against that quote to prevent unrelated payments.
- The reported `maxFeePerGas < baseFee` values therefore arise after the
  request reaches MetaMask or its RPC fee estimator. Orb cannot remove a fee
  override it does not send. The wallet UI now gives specific retry guidance
  for this rejection, reminds the user to check wallet activity, and does not
  automatically resubmit a transaction. Clicking Buy Credits again obtains a
  fresh server quote and asks MetaMask to estimate and approve it again.
- The payment amount, receiver, chain ID 421614, wallet authentication, and
  backend receipt verification remain unchanged. An integration test asserts
  both initial and retry transaction objects have exactly the four required
  fields and that a failed fee estimate creates no pending-payment record.
- No real on-chain transaction was initiated as part of this change. A live
  MetaMask retry is still needed to determine whether its current network/RPC
  fee estimate succeeds.
- Validation: targeted frontend file **16 passed**, full frontend suite
  **29 passed** across 3 files, and guarded Vercel production build passed
  using a placeholder HTTPS API origin. No push or deployment was performed.

## 2026-09-27 Final Orb UI/UX polish (local, not deployed)

- The header now contains the compact primary Connect Wallet / Connected
  action beside the existing menu. It uses the same signed wallet flow and
  opens Wallet & Credits; the redundant wallet prompts below upload/Enhance
  were removed. The panel still shows account, network, credits, buying, and
  disconnect. Its testnet notice is shorter.
- The processing view uses Orb's Neptune-style mark instead of a generic ring
  spinner. It rotates subtly and stops under reduced-motion preferences.
  Upload, image/video analysis, scene analysis, prompt creation, and Enhance
  labels now use product language. Payment verification text is simplified.
- The desktop frame is capped at **980px** and centered. The hero wraps in
  balanced lines. Mobile retains fluid width, safe-area bottom spacing, and
  responsive header, panel, upload, and mode controls. Existing circular panel
  close icons use a symmetric SVG cross with grid centering. This checkout has
  no separate processing cancel control or backend cancel route, so no fake
  cancel action was introduced.
- Results no longer render the backend provider name. Provider/infrastructure
  errors are shown as Orb AI errors. Decode keeps a plausible-reconstruction
  caveat; Compose and Enhance have distinct purpose text. A noninteractive
  `Generate · Coming soon` roadmap note appears below the mode pills.
- Existing local uncommitted wallet fee-guidance changes are preserved. No AI,
  payment, credit, auth, Postgres, chain, backend processing, or job-recovery
  behavior was intentionally changed. Nothing was committed, pushed, or
  deployed during this polish pass.
- Validation: full backend suite **179 passed** (104 existing FastAPI
  deprecation warnings); full frontend suite **33 passed** in 3 files; guarded
  Vercel production build passed with a placeholder HTTPS API origin.
- Local browser visual checks at desktop 1280px, tablet 768px, mobile 390px,
  and narrow mobile 320px confirmed the centered 980px desktop frame, fluid
  mobile layout, no horizontal overflow, 28px mobile bottom gap, readable
  header controls, reachable Wallet & Credits panel/close icon, and usable
  Enhance fields. The local Vite preview had no live backend attached, so
  rendered paid results and processing were checked by frontend tests rather
  than an end-to-end browser run. No real wallet transaction was initiated.

## 2026-09-27 Final visual refinement (local, not committed or deployed)

- The desktop frame maximum width is now **1005px**, centered. Tablet and
  mobile remain fluid with the existing breakpoints and safe-area spacing.
- The header and processing views share a CSS atmospheric blue/cyan sphere
  with Orb's tilted planetary ring. A diffused highlight travels left to right
  across the sphere to suggest prograde rotation; the ring remains steady.
  Header motion loops in 12 seconds and processing motion in 4.5 seconds.
  Reduced-motion preferences stop the animation.
- The mode row now reads Decode, Compose, Enhance, Create. Create is a locked,
  non-actionable mode with a Coming soon label. Its separate information button
  opens a keyboard-accessible roadmap popover and closes on outside click,
  Escape, or its close button. It has no backend path or credit action. The
  prior Generate roadmap note was removed.
- About Orb now explains the problem, the three current stages, the future
  Create stage, the creative loop, intended audiences, and testnet credits.
  Its sections stay scrollable on mobile and its close control stays visible.
- Rendered browser checks at 1280px, 768px, 390px, and 320px found no
  horizontal overflow. The desktop frame measured 1005px; mobile preserved a
  28px bottom gap. The Create popover was adjusted to fit a 320px viewport.
  The local preview had no live backend, so this pass did not perform a paid
  AI or wallet transaction in the browser.
- Validation: full backend suite **179 passed** (104 existing FastAPI
  deprecation warnings); full frontend suite **34 passed** in 3 files; guarded
  Vercel production build passed with a placeholder HTTPS API origin.

## 2026-09-27 Create close icon and Orb motion follow-up (local, not committed or deployed)

- The Create information popover's text `×` used uneven font glyph metrics
  despite grid centering. It now uses a symmetric SVG cross inside the same
  28px circular button. Browser geometry showed zero horizontal and vertical
  offset on desktop and mobile, and at 125% and 150% CSS zoom.
- The previous oversized, blurred, symmetric glow moved in CSS but changed
  too little of the clipped sphere to read as motion. A narrower atmospheric
  highlight now traverses the sphere fully from left to right while Orb's ring
  stays steady. The header loop takes 6 seconds; the larger processing mark
  loops in 2.4 seconds. Reduced-motion rules continue to stop movement.
- A temporary local visual fixture rendered both sizes together; it was
  removed after checks. Browser samples over 300ms measured about 3.6px of
  left-to-right header travel and 9.5px of processing travel. Desktop and
  390px/320px mobile popovers showed a centered close cross and no horizontal
  overflow. The local preview had no backend attached, so no live AI or paid
  processing flow was run for this purely visual follow-up.
- Validation: targeted frontend file **21 passed**; full frontend suite
  **34 passed** in 3 files; guarded Vercel production build passed with a
  placeholder HTTPS API origin.

## 2026-09-29 Hackathon submission README refresh

- Reworked README around the user's submission draft for the Arbitrum Open
  House Singapore Online Buildathon: why Orb exists, Decode, Compose,
  Enhance, locked Create roadmap, Arbitrum integration, credit safety,
  architecture, video processing, and security.
- Preserved the public frontend and backend links and the Arbitrum Sepolia
  testnet/demo disclaimer. Removed outdated product and predeployment wording;
  the retained `prometheus` internal package path is explained only where
  needed for the working startup command and repository layout.
- Preserved and refreshed PowerShell setup, local unpaid/paid testing,
  Supabase Postgres, Render Free, Vercel, environment configuration, and
  deployment validation instructions. Local startup explicitly loads `.env`
  with Uvicorn, including installation of `python-dotenv`. Render's recurring
  health check is documented as `/api/health`, with `/api/ready` reserved for
  upload/analysis readiness checks.
- Corrected the old in-memory session description: hashed server sessions
  persist in the ledger, browser tokens use session storage, and same-wallet
  signing resumes an existing paid job after expiry. Documented durable result
  recovery, temporary production media, and the single-worker/instance
  reconciliation constraint.
- All private configuration examples use placeholders; no populated `.env`,
  API key, database credential, RPC credential, private key, or seed phrase
  was read or added. `.env` remains ignored. Only README and HANDOFF were
  edited; application code and the original Prometheus project were untouched.
- Validation: full backend suite **179 passed** with 104 existing FastAPI
  deprecation warnings; full frontend suite **34 passed** in 3 files after
  retrying an initial worker-start timeout; guarded production build passed
  with a placeholder HTTPS API origin. These tests use AI/blockchain/database
  doubles where documented; no live provider call, Supabase verification, or
  on-chain transaction was performed during this documentation task.
- No commit, push, or deployment was performed.

## 2026-10-02 USDG staging database isolation review

- Started from clean `main` at `ed54ebe682ca64be6580f33887881b01099ae4f3`
  and created the requested local `usdg-test` branch. Main remains unchanged.
- Inspected the existing payment service and Postgres schema without reading
  populated environment files or connecting to any deployed database.
- Sharing production's current ledger is unsafe: all Postgres connections use
  the fixed `orb` schema; balances are keyed only by wallet; sessions, quotes,
  purchases, reservations, and results have no deployment/environment scope.
  Startup reconciliation visits every reserved job and can release a live
  production job's reservation if its result has not yet been stored.
- Per the user's section 10 stop instruction, payment implementation is
  paused pending agreement on isolated staging storage. Recommended minimum:
  a separate staging Postgres database with separate credentials and a staging
  `ORB_DATABASE_URL`; a separate Supabase project is one way to provide it.
  No production database URL or environment group should be reused. A separate
  schema in the existing database would require deliberate schema selection
  and database role permissions; the current code does not support it safely.
- No application code, schema, payment configuration, production deployment,
  Prometheus, or orb-demo-video files were changed. Only this HANDOFF entry was
  added on `usdg-test`. No tests were rerun because application code is unchanged.
- No infrastructure was created, and no commit, push, migration, deployment,
  wallet signature, or transaction was performed.

## 2026-10-02 Paxos test USDG implementation on usdg-test

- The user approved an isolated staging Postgres database; implementation
  resumed on `usdg-test`. The unchanged main baseline is
  `ed54ebe682ca64be6580f33887881b01099ae4f3`. No existing environment file,
  production database/service, Prometheus, or orb-demo-video was modified.
- Native ETH remains the default when USDG variables are absent. USDG mode
  requires the explicit `usdg-staging` target, Arbitrum Sepolia 421614, official
  Paxos token `0xFFC95faa3d63Cde504a05B567C600B78C0b41892`, six decimals,
  and integer pricing of 100000 base units per credit.
- USDG quotes store wallet, receiver, token, exact amount, creation time/block,
  deadline, and completion via the existing quote record. Standard ERC-20
  transfer calldata has no quote ID; a matching transfer is assigned once to
  its verified quote, protected by global transaction and quote uniqueness.
  Payments must be mined after quote creation and verified before expiry.
- Backend verification independently checks network, receipt success,
  canonical block and confirmations, wallet/target/value/calldata, receiver
  EOA, token code/decimals, and one exact well-formed nonremoved Transfer log.
  Credit grant, purchase insertion, and quote completion are atomic. Concurrent
  same-quote retries return the existing grant without incrementing twice.
- Added USDG extension version 1: `orb.usdg_quotes` and
  `orb.usdg_schema_versions`, with a quote foreign key, integer constraints,
  and transactional/advisory-locked fresh database bootstrap. Core schema
  version 1 and existing columns stay intact. USDG refuses an unmarked,
  nonempty Orb ledger. No hosted migration was applied. Local USDG defaults
  to separate SQLite; public staging requires its own Postgres URL.
- Wallet sends only from/to/value/data; USDG target is the configured token,
  native value is zero, and data is a server-quoted ERC-20 transfer. Wallet
  controls gas/fees and requests user approval. Added concise USDG/gas copy,
  quote validation, pending-payment protection, and wallet rejection/funds
  guidance. Wallet/session/AI credit-reservation and job-recovery flows remain.
- Staging build rejects the current production backend and Production USDG
  deployments; staging wallet refuses a backend not identifying as USDG
  staging. Vercel Git auto-deploy for `usdg-test` is disabled in branch config
  so the authorized push does not publish a preview automatically. Production
  branch configuration and external settings were not changed.
- `.env.example`, README, and `docs/USDG_STAGING.md` document safe placeholders,
  isolated Supabase setup, Render staging, branch-scoped Vercel Preview values,
  exact origin/CORS, test-asset acquisition, and the manual acceptance flow.
  No new runtime dependency or payment contract was added.
- Validation: full backend **225 passed**, with 106 FastAPI deprecation
  warnings; full frontend **49 passed** across 4 files; guarded staging build
  passed with a placeholder HTTPS API origin. Tests include default native
  regressions, USDG faults/expiry/replays/concurrency/rollback, signed purchase
  followed by paid Enhance, result recovery, and staging isolation. Blockchain
  and AI use mocks; Postgres uses SQL-recording/SQLite-backed doubles. No live
  Supabase, Gemini, or USDG transaction verification was performed in this pass.
- Ready for the user-authorized commit/push to `usdg-test`, then stop before
  cloud creation/deployment. Staging credentials, actual preview origin,
  receiver, faucet funds, live database bootstrap, and one real payment/AI
  acceptance test remain external setup work.

## 2026-10-02 Dual-payment preparation and explicit USDG migration

- Started from clean `usdg-test` at `fc9a9c838347f637bda0b559928f933243b0beab`.
  Main and origin/main remain `ed54ebe682ca64be6580f33887881b01099ae4f3`.
  The user reported real single-method USDG staging success: 0.30 USDG,
  three credits, persistence, AI consumption, and no duplicate grants. This
  pass prepares dual methods; it does not claim their live staging acceptance.
- Added `ORB_PAYMENT_METHODS=native_eth,usdg`. The explicit list takes
  precedence over the legacy single switch; absent variables preserve native
  ETH. USDG token/chain/decimals/100000 price checks remain. Explicit methods
  prepare eventual production activation without a staging-only requirement;
  the legacy USDG switch and designated staging origins keep their safeguards.
- Config exposes server-enabled structured methods; quotes explicitly select
  a method when both are enabled. Single-method omitted selection remains
  compatible. Existing native price/receiver/ORB1 calldata and verification
  remain; USDG uses exact server-quoted transfer calldata, zero ETH, and receipt
  Transfer verification. Verification dispatches by persisted quote metadata,
  not client claims or the backend's default method. Both assets share global
  purchase-hash/quote uniqueness and atomic credit grants.
- Added compact Test ETH / Paxos USDG selection, pressed-state accessibility,
  method-specific notices/funds guidance, and explicit quote requests. UI shows
  only enabled methods and blocks another payment while one is pending.
  Wallet/session/job recovery, AI operations, credit lifecycle, and balances
  are unchanged. No wallet USDG balance query or dependency was added.
- Added `python -m prometheus.api.orb_usdg_migrate --check` (alias `--dry-run`)
  and the explicit migration without flags. The command reads privately supplied
  ORB_DATABASE_URL, never imports the app or loads .env, and checks core v1
  columns/constraints/version plus extension shape. Missing/extra/partial or
  unsupported schemas fail closed. Checks are read-only: exit 0 ready, 2
  migration required, 1 refused. Migration adds only usdg_quotes and extension
  marker in one advisory-locked transaction, verifies, and safely retries. No
  balance/session/purchase/job/result row is changed or reconciled. Startup
  still rejects a populated unmarked ledger; no production migration was run.
- README, .env.example, USDG staging guide and docs/DUAL_PAYMENTS.md document
  staging dual acceptance, production backup/migration rehearsal, commands,
  configuration, and compatible rollout: new backend native-only, new frontend,
  then enable both methods. Old tabs may require refresh. Existing staging
  isolation/build guard and disabled Git auto-deploy remain. No merge, hosted
  environment change, production database/service change, Prometheus edit,
  orb-demo-video edit, or blockchain transaction was performed.
- Final validation: complete backend **253 passed** with 108 existing FastAPI
  deprecation warnings; complete frontend **59 passed** across four files;
  guarded staging production build passed with a non-routable HTTPS origin.
  Frontend ran with one threads worker after a fork-worker startup timeout;
  initial sandbox Node/temp-directory access errors were resolved with normal
  filesystem access. Targeted final dual/migration tests also passed (28).
  RPC/AI and Postgres catalogs use doubles; real Postgres migration rehearsal
  and real dual-method staging payments remain pre-merge acceptance gates.
- Secret/runtime review found no real credentials or private runtime files in
  the 16 intended changes. Populated env files remain ignored. Authorized
  delivery is one commit/push solely to `usdg-test` after validation, then stop;
  no production database/origin/environment or deployment action is authorized.


## 2026-10-03 Populated disposable Postgres USDG migration rehearsal

- Worked only in Orb on `usdg-test`, starting from clean
  `a24a618ee0694e56e1528e0d6d3a434b163f7f6d`. Main/origin/main remain
  `ed54ebe682ca64be6580f33887881b01099ae4f3`. No production database,
  Render/Vercel configuration, original Prometheus, orb-demo-video, real wallet,
  provider, or payment transaction was accessed or modified.
- No local Postgres/container runtime existed. Used official portable EDB
  PostgreSQL 17.11 binaries under ignored api_output, with an owned loopback-only
  random-port TLS cluster. No Windows service/cloud infrastructure was created.
  Added a runner that strips inherited configuration, never loads .env, creates
  a unique cluster ownership marker, and stops only its owned cluster. Windows
  inherited output-pipe handling was fixed in the test launcher, not Orb code.
- Added eight opt-in real-Postgres integration cases. Each uses a new database
  with exact POSTGRES_SCHEMA_V1 and synthetic sessions/wallets, balances, native
  quotes/purchases, successful/released/reserved jobs and durable results.
  Initial counts: schema_versions 1, challenges 2, sessions 2, balances 2,
  quotes 4, purchases 3, reservations 6, results 4. Wallet A: granted 10,
  consumed 2, reserved 2, available 6; wallet B: granted 3, consumed 1,
  reserved 0, available 2.
- Actual subprocess CLI: pre --check exit 2/no mutation; explicit migration
  exit 0; post --check exit 0; repeat migration and final dry-run exit 0/no
  changes. Adds only usdg_quotes and usdg_schema_versions with marker 1.
  Full core row values/counts, columns/constraints/indexes, relation identities,
  filenodes and row ctid/xmin stayed identical. No migration reconciliation or
  credit release occurred. Existing migration code needed no fix.
- Five separate malformed ledgers (partial USDG, extra core column, wrong
  session column type, missing core table, unsupported USDG version/integrity)
  refused both check/apply with exit 1 and no changes. Injected failure after
  the first extension table rolled back all DDL. Two concurrent migration
  commands succeeded under the advisory lock with one marker and unchanged core.
- Real ASGI startup on migrated Postgres passed production paid guards using
  synthetic config and mocked RPC, then showed both payment methods, preserved
  authenticated access/native payment replay, issued a 300000-unit three-credit
  USDG quote, and recovered the durable result. EXISTING restart reconciliation
  consumed one reserved completed result and released one interrupted no-result
  reservation; A became granted 10/consumed 3/reserved 0/available 7. Other
  records/counts remained intact and a second startup made no further changes.
  No recovery, pricing, auth, payment, AI, or database application logic changed.
- Evidence: docs/MIGRATION_REHEARSAL.md and ignored JSON reports under
  api_output/migration_rehearsal_runtime/<run-id>/reports. The focused real-PG
  run was 97ca51a0bb7a4fe88865f32c135a0c7d: eight passed. These are actual
  Postgres migrations, not SQL doubles; blockchain RPC is mocked and AI is
  not called. Frontend: 59 passed (four files). Guarded staging production
  build passed with a non-routable HTTPS API origin.
- Full backend validation passed: **261 tests**, including all eight real-PG
  cases (112 existing FastAPI deprecation warnings), in 365.97 seconds. The
  full-suite cluster run was 7c4e08d7d74a45f29ae407d741712623; its reports are
  saved alongside the focused run, and both owned servers were stopped. No commit/push/merge/deployment was performed. Portable binaries,
  TLS keys, clusters and raw runtime reports are ignored, as are populated env
  files. Remaining: real dual staging acceptance, separate merge/production
  approval, verified backup/restore, authorized production check/migration,
  core-record comparison, compatible native-first rollout, then real payments.
  Finish active AI work before backend restart; the migration itself does not
  reconcile jobs. See docs/DUAL_PAYMENTS.md for the exact rollout.

## 2026-10-03 Migration CLI suppressed-exception diagnosis

- Inspected clean application sources on `usdg-test` at
  `ba321cbb2a6fe2cc3bb8b9aa60d346f39a904f8f`. The user's untracked
  `backups/` directory was neither opened nor modified.
- Plain `python` in this session resolves to the global Python 3.13 executable,
  which has no `psycopg` or `psycopg_binary`. Orb's `.venv` has both installed.
  The production database environment variable remains unavailable to this
  Codex process; no production connection or schema inspection was attempted.
- Reproduced the suppressed exception using only a synthetic connection URL.
  `_connect_postgres()` fails at `import psycopg` with
  `ModuleNotFoundError: No module named 'psycopg'`, wraps it as
  `RuntimeError: Orb could not connect to its production Postgres database.`,
  and the migration CLI's broad exception handler emits the reported generic
  message and exit 1. No SQL is executed in this failure path.
- Minimal correction: in the same private PowerShell environment where psql
  succeeds, use `.\.venv\Scripts\python.exe -m prometheus.api.orb_usdg_migrate
  --check`. This selects Orb's installed dependencies. It does not establish
  what the production schema check will return once the correct interpreter
  is used; another live error would require diagnosis in that private session.
- No application behavior was changed and no temporary diagnostic mode was
  needed. No credentials were printed, production records modified, write
  migration applied, merge/deployment/configuration change made, or commit
  created. Only this handoff records the local diagnostic evidence.

## 2026-10-04 Configurable USDG credit price

- Working on `main`, separated USDG pricing from the fixed token safety guard.
  `CreditConfig.__post_init__` previously rejected `self.usdg_price != USDG_PRICE`,
  where `USDG_PRICE` was 100000. That made a legitimate 3000-unit price fail
  startup with the generic Paxos configuration error.
- Default/intended USDG price is now 3000 base units per credit: 1/3/5 credits
  cost 0.003/0.009/0.015 test USDG. Environment parsing accepts positive decimal
  integers only; zero, negative, malformed, decimal and scientific values fail
  startup. Explicit 100000 remains valid. Typed configuration also rejects
  non-integers, including booleans. No floating-point payment arithmetic added.
- Chain 421614, official Paxos contract, six decimals, explicit payment-method
  enablement and isolated legacy staging checks remain enforced. Native ETH
  pricing, receiver configuration, receipt verification, authentication, credit
  lifecycle, persistence, migrations and job recovery are unchanged. Existing
  USDG quotes retain their stored amount across price changes.
- Updated configuration examples, README and payment/staging guides. The
  existing frontend formatter already supports the smaller values; only its
  tests changed, with explicit 1/3/5-credit price coverage.
- Full backend: 274 passed, 8 opt-in real-Postgres tests skipped, 114 existing
  FastAPI deprecation warnings. Full frontend: 62 passed. Guarded main production
  build passed using https://orb-api.example.invalid. Provider and blockchain
  calls were mocked; no live AI, chain transaction or production database access
  occurred during this pass.
- User confirmed both production Git auto-deployments are disabled and
  authorized commit/push to main after validation. No production environment,
  database or service configuration was changed; no deployment was performed.
  Changes are confined to independent Orb. Populated .env files, secrets,
  backups, uploads, results and runtime databases remain excluded from Git.

## 2026-10-04 Credit config recovery and wallet restoration isolation

- Fixed the frontend conflation of pending/failed payment config requests with
  explicit server-disabled configuration. `web/wallet.js` now keeps parsed
  configuration separate from loading/ready/disabled/unavailable state.
  Only a successfully fetched explicit `enabled: false` shows
  "Testnet credits are not configured on this Orb server."
- Initial pending requests show "Loading credit options…". Transient request,
  timeout, HTTP error (including unexpected 401/403), invalid JSON or invalid
  response failures show "Credit service is starting…". Exhaustion shows
  "Credit service temporarily unavailable. Try again." Success clears the
  temporary warning and renders the server's payment methods without refresh.
- One shared config task prevents concurrent requests/retry cycles. Each
  request has a 15-second abort timeout; retry backoff is 1/2/4/8 seconds,
  capped at 8 seconds, with at most 12 attempts and a two-minute total budget.
  Explicit disabled responses are not retried. The header opens the panel
  safely while loading and can restart recovery after exhausted retries.
- Config validation/payment rendering precede independent network and session
  restoration. A wallet provider, saved-session or balance restoration failure
  cannot erase valid payment config. The isolated USDG Preview guard and legacy
  single-method compatibility remain intact; ready responses must have usable
  server-enabled payment metadata before purchase controls become available.
- Added 27 mocked-fetch/wallet frontend tests covering delayed responses,
  network/CORS failures, 503/401/403, invalid responses, timeout/abort ordering,
  late stale responses, bounded retry/backoff, manual recovery, disabled state,
  both payment options and wallet/session/network restoration independence.
  Full frontend: 89 passed. Guarded main production frontend build passed with
  https://orb-api.example.invalid. Full backend: 274 passed, 8 opt-in real-
  Postgres tests skipped, 114 existing FastAPI deprecation warnings. Provider,
  wallet and blockchain integration checks used mocks; no live payment or AI
  operation was performed in this pass.
- No backend, pricing, quote/transaction/verification, database, auth protocol,
  session expiry, AI/job recovery or Render/Vercel configuration code changed.
  No production services/databases or secrets were accessed. User authorized
  commit/push to main after full validation; production automatic Git deployments
  were previously confirmed disabled. Original Prometheus remains untouched.

## 2026-10-05 Mobile file readability recovery

- Decode/Compose image and video uploads now stay on the selection screen with
  an accessible "Checking file…" status before any upload/processing UI appears.
  A small 64 KB prefix is checked; no full-file browser buffering was added.
- `web/file-readability.js` permits only two additional local reads for
  NotReadableError/NotFoundError, after 300 ms and 800 ms. Each read has a
  five-second timeout. Other errors/timeouts are not retried. FileReader provides
  the same bounded prefix check when Blob.arrayBuffer is unavailable.
- Persistent failures clear the saved File, input value and attempt state,
  restore selection controls, and show "Couldn't access this video/image" with
  concise Files/Browse guidance. Diagnostics remain in the console. Orb does not
  claim it can force an Android provider. Normal picker cancellation preserves
  the selection; clearing a pending check aborts it. Late or superseded reads
  cannot start an upload, including after a replacement File succeeds.
- Local retries construct no FormData and send no media/job request, so no
  backend job or credit reservation/consumption begins. A successful check
  proceeds to readiness and one existing authenticated/idempotent upload POST.
  HTTP upload retries, payments, pricing, database, AI/FFmpeg behavior, job
  recovery and infrastructure remain unchanged. A readable prefix still cannot
  guarantee that the remainder stays accessible throughout upload.
- Added focused helper and rendered frontend tests for immediate success,
  bounded retry/backoff, third-read success, non-retryable errors, timeout/late
  resolution, cancellation/replacement, clean image/video failures, fresh
  same-name selection, empty files, Decode/Compose, repeated clicks and paid
  authentication/idempotency preservation. Full frontend: 110 passed. Guarded
  production build passed using https://orb-api.example.invalid.
- Full backend: 274 passed, 8 opt-in real-Postgres tests skipped, 114 existing
  FastAPI deprecation warnings. An initial run's two guard failures came from
  the runner's temporary PROMETHEUS_FFMPEG_DIR variable; supplying FFmpeg through
  the test process PATH made the complete suite pass without backend changes.
- No production services/database, live AI quota or on-chain transactions were
  used. Secrets and runtime artifacts remain excluded. Original Prometheus is
  untouched. User authorized commit/push to main after validation; automatic
  production Git deployments were previously confirmed disabled. No deployment
  is performed here. Physical Android Gallery verification remains a follow-up
  after the user deploys this change.

## 2026-10-05 Mobile wallet browser control compatibility

- Replaced the native credit quantity select with compact HTML button radios
  for 1/3/5 credits, defaulting to 1. The labelled radio group exposes checked
  state, a single Tab stop, arrow-key wrapping and Home/End navigation. Native
  button Space/Enter activation is preserved; no touch-specific handlers or
  wallet/browser detection were added. Quantity remains usable during wallet
  activity and survives payment-method switching. Existing integer pricing and
  server-authoritative quote/transaction construction are unchanged.
- Choose File is now an associated label containing the actual native file
  input. The transparent input covers only the visible Choose File control,
  remains keyboard/screen-reader accessible, and accepts direct taps as a
  fallback for browsers that do not forward label activation. Removed the
  JavaScript input.click handler, avoiding duplicate picker activation or an
  async boundary. Accepted media types, absence of capture, change handling,
  readability preflight, cancellation and same-file reset behaviour remain.
- Wallet & Credits keeps its existing fixed panel and desktop appearance; its
  heading/close control now sticks while the panel scrolls. No backdrop or
  modal architecture was introduced.
- Full frontend: 126 passed (16 added cases); full backend: 274 passed,
  8 opt-in real-Postgres tests skipped, 114 existing FastAPI deprecation
  warnings. Guarded production build passed with https://orb-api.example.invalid.
  Tests cover accessible selection, keyboard navigation, all native/USDG
  quantities and exact unchanged transaction fields, selection during/after
  payment, label/direct input single activation, cancellation, same-name reset,
  image/video Decode/Compose and single-upload submission. Existing readability,
  authentication, payment/idempotency and paid-job recovery tests still pass.
- Also checked the built frontend in a local Chromium browser with in-memory
  mocked wallet/API responses and all real transactions blocked. Native pointer
  and Enter activation emitted file-chooser events. Keyboard quantity selection
  and method switching worked. At 390px and 320px there was no horizontal page
  overflow; the wallet close control remained hit-testable after panel scrolling.
  Physical Zerion Android, MetaMask, Rabby, Chrome Android and Edge checks remain
  manual follow-ups: web code cannot guarantee a host app presents its chooser
  or releases a native overlay. No live AI, payments or production API/DB calls
  occurred. The local mock server was stopped after verification.
- No backend, authentication protocol, pricing, ETH/USDG verification,
  persistence, AI, MetaMask gas behaviour or infrastructure code changed.
  Original Prometheus remains untouched. User authorized commit/push on main
  after validation; production automatic Git deployments were previously
  confirmed disabled. No deployment is performed in this pass. Secrets and
  runtime files, including the local QA screenshot, are excluded from the commit.

## 2026-10-05 Direct native file-picker activation

- Physical Zerion Android feedback confirmed quantity controls and general
  wallet/page interaction now work, but Choose File still did not open a picker.
  This follow-up changes only the file-control markup/styles and related tests.
- Removed the wrapping label and its forwarding path. A non-interactive relative
  wrapper contains visual text with pointer-events disabled and the real file
  input positioned over its entire area (inset 0, width/height 100%, opacity 0,
  z-index 1, pointer-events auto). The input remains focusable, screen-reader
  labelled, and neither display:none nor visibility:hidden. No synthetic click,
  async activation, duplicate touch handler or wallet-specific detection exists.
- Accepted formats, absence of capture, file change handling, Decode/Compose,
  readability preflight, cancellation, same-file reset and paid/idempotent upload
  behaviour remain unchanged. Quantity, wallet/payment, MetaMask gas, backend,
  AI, database, blockchain and infrastructure code were not modified.
- Local Chromium checks of the guarded build confirmed all five sampled hit
  points across the control target file-input at 1280px, 390px and 320px; input
  bounds equal the visual wrapper bounds. Direct click and Enter opened native
  file-chooser events, click counts were one, and mobile widths had no horizontal
  overflow. Checks used an isolated local mock API without real AI/payment or
  production access; local test servers were stopped afterward.
- Physical Zerion Android must be retested after a user-authorized deployment.
  If direct native input activation still fails there, the remaining problem is
  likely Zerion's embedded WebView/native file-chooser implementation. Normal
  website JavaScript cannot reliably repair a host app that does not present
  the chooser. This change does not promise to force a particular Android
  picker/provider. Original Prometheus remains untouched.
- Full frontend: 127 passed. Full backend: 274 passed, 8 opt-in real-Postgres
  tests skipped, 114 existing FastAPI deprecation warnings. Guarded production
  build passed using https://orb-api.example.invalid. Focused tests verify the
  input's active overlay, no wrapper/label/programmatic activation, a single
  native click path, cancellation, same-name reset, image/video Decode/Compose
  and no duplicate media uploads. Existing wallet/payment/readability suites
  remain passing. User authorized commit/push to main after validation; automatic
  production Git deployments were previously confirmed disabled. No deployment
  is performed here; secrets/runtime data and the QA screenshot remain excluded.

## 2026-10-05 Fresh Arbitrum Sepolia EIP-1559 fee estimation

- User reported wallet-selected caps below the current Arbitrum Sepolia base
  fee before a transaction hash was returned. Both native ETH and USDG need
  native ETH gas. This change is frontend-only and wallet-agnostic.
- Added web/payment-fees.js: fresh EIP-1193 reads on every Buy Credits attempt;
  pending block base fee with latest fallback; priority suggestion from
  eth_maxPriorityFeePerGas, then three-block feeHistory median rewards, then
  gasPrice minus base fee. All quantities and fee arithmetic use BigInt.
  Invalid/absent base fees fail closed. Tips above the base fee are rejected
  as excessive rather than replacing them with an arbitrary static gwei tip.
- The fee cap is ceil(fresh base fee * 3 / 2) + priority fee: 50% base-fee
  headroom. Base fee is refreshed after exact-payload eth_estimateGas. The
  wallet controls the gas limit; no gasPrice, gas, or nonce is supplied.
  Tests cover rounding, quantities beyond Number precision and 49% base-fee
  growth. This is a bounded cushion, not a guarantee against unlimited wallet
  approval delays or congestion. Details and primary-source links are in
  docs/DUAL_PAYMENTS.md; README payment guidance is updated.
- The original quoted from/to/value/data remain unchanged for native ORB1
  binding and USDG transfer. Before sending, recheck authenticated wallet,
  account/chain, provider identity, auth epoch and quote expiry. Read calls
  have 8-second timeouts and a 30-second total estimation deadline. Rejection,
  disconnect or identity change stops the attempt; late responses cannot send.
- Clear fee-estimation error copy replaces static-fee fallback; base-fee error
  guidance is wallet-neutral. Diagnostic errors stay in the console. Only one
  eth_sendTransaction is permitted per user attempt. No hash means no payment
  verification or grant; ambiguous send errors advise inspecting wallet activity
  before a manual retry. Existing shared replay/idempotency protections remain.
- Added 53 deterministic frontend tests for RPC fallbacks, malformed data,
  bounds, fresh repeated estimates, exact native/USDG payloads, identity races,
  rejection, ambiguous sends, missing hashes and late timeout completion.
  One asynchronous settlement assertion now waits for the actual expected
  balance instead of relying on fixed event-loop flushes.
- Full frontend: 180 passed. Guarded production build passed with the safe
  https://orb-api.example.invalid API origin. Full backend: 274 passed, 8 opt-in
  real-Postgres tests skipped, 114 existing FastAPI deprecation warnings. The
  initial sandbox run could not access pytest's Windows temporary directory;
  rerunning with required local filesystem access passed the complete suite.
  Production DB/RPC/AI credentials were removed from the test process environment.
  No live transaction, AI call or
  deployment is performed. Physical wallet/testnet approval remains a manual
  check after an authorized deployment. Backend, pricing, verification, database,
  infrastructure and original Prometheus code remain unchanged.
