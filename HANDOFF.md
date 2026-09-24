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

## Frontend structure and modes

- Header: ORB wordmark + mode tabs (Decode active; Compose and Enhance
  disabled with "Coming soon").
- Home: hero ("Every visual starts with an idea." / "Decode, compose, and
  enhance your creative prompts."), three mode cards, large centered
  dropzone, service status, Decode button, error area.
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

## Backend functionality preserved

Upload streaming + validation, FFprobe metadata, scene detection, frame
sampling, basic-tier local inspection, staged/gated upload readiness,
single-attempt uploads with attempt IDs, job polling, result DTOs, prompt
reconstruction and remix code (server-side, unexposed), and the payment
module with its replay-protection tests (dormant behind the flag).

## Test results

- Backend: 138 passed (`pytest`), own `.venv`, Python 3.13.
- Frontend: 11 passed (`test:web`: 8 app + 3 api-url), jsdom.
- `vite build`: clean (`web_dist/`).
- Independent startup smoke test on port 8790: `/api/health` ok
  (`payment_required: false`), `/api/ready` ready,
  `/api/payments/config` 503 as designed.

## Unresolved issues

- One inherited test needed a one-word brand adaptation (see above);
  no engine behavior was weakened.
- `resume-after-reload` recovery from Prometheus was intentionally left
  out of the Orb frontend for stage 1.
- The internal Python package is still named `prometheus` for
  compatibility; renaming is deferred.

## Next stage work

1. Image-input support in the backend (probe/segment/sample for stills)
   and frontend upload acceptance.
2. Compose (reference-based generation) and Enhance (prompt refinement)
   backend endpoints plus real UI wiring.
3. Orb credit system on Arbitrum Sepolia with its own entitlement model;
   keep Nimiq code dormant until then.
4. Prompt reconstruction exposure for Decode once entitlement exists.
5. Deployment configuration (new hosting, HTTPS, production RPC or model
   endpoints) — nothing is deployed or pushed anywhere yet.
