# ORB

ORB is an AI-powered creative intelligence platform built for the Arbitrum
Open House Online Buildathon. It decodes the visual language of a video and,
in later stages, composes and enhances creative generation prompts.

This project reuses the proven Prometheus analysis engine (FFmpeg/FFprobe
structural analysis, Gemini vision analysis, prompt reconstruction, remix) but
is an independent project with its own frontend, branding, and infrastructure.

## Product modes

| Mode | Status | Description |
| --- | --- | --- |
| Decode | Available (video) | Structural analysis of an uploaded video; prompt reconstruction ships with the Orb credit system. |
| Compose | Coming soon | Reference-based prompt generation. |
| Enhance | Coming soon | Prompt refinement. |

Image input support, Compose, and Enhance are not operational yet and are
marked as such in the interface. No result is ever fabricated.

## Payments

The inherited Nimiq payment code is dormant in ORB. It is disabled at startup
unless `ORB_ENABLE_NIMIQ_PAYMENTS=1` is set, which must never be done outside
the inherited test suite. ORB will use its own Arbitrum Sepolia payment and
entitlement system in a later stage. The Orb frontend contains no payment UI.

## Local development

Python 3.12+ and Node 22+ are required.

```powershell
# Backend (terminal 1)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn prometheus.api.app:app --host 127.0.0.1 --port 8790
```

```powershell
# Frontend (terminal 2)
npm install
npm run dev
```

Open the Vite network URL (default port 5174). The dev server proxies `/api`
to the backend on port 8790. Optional server-side configuration lives in
`.env.example`; no credentials are required for Decode.

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
