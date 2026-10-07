# Liquid-glass UI test branch

This is a frontend visual experiment on `ui-liquid-glass-test`, not a production
rollout. Do not merge or deploy it without a separate review.

## Starting point and preserved experiments

- Main starting HEAD: `2399c9f896f2f9264b8f0e2e42de8a733e07768b`.
- Uncommitted Phase 3 scene-detection experiments were preserved before creating
  the UI branch. The stash is
  `bd0d5a667b95f0060da719a92a54cd0f49f36bc8`, named
  `Preserve Phase 3 scene experiments before liquid glass UI`.
- The stash contains the previous HANDOFF changes, `docs/VIDEO_PHASE3.md`,
  `docs/VIDEO_PHASE3_SCENE_COMPARISON.csv`, `scripts/benchmark-video-phase3.py`,
  and `tests/test_video_phase3_experiments.py`. It has not been applied or dropped.
  Recover it separately on the intended experiment branch with a clean working
  tree; do not mix it into this UI commit. Generated benchmark artifacts remain
  ignored and untouched.

## Visual system

- Ice-blue CSS radial gradients, faint arcs and atmospheric spheres, with no
  background images, canvas, WebGL, video backgrounds or new dependencies.
- Shared color, radius, blur, spacing and shadow tokens. Larger glass surfaces
  use a 20px backdrop blur where supported; an opaque pale-blue surface is the
  fallback. Child controls do not each add another backdrop blur.
- A centered, fluid workspace retains the 1005px desktop maximum width.
- Compact hero: “Understand visuals. Create better prompts.” The mode controls
  sit above the workspace, with icons and supporting descriptions. Create stays
  locked; its existing information popover remains the only action in that card.
- Header wallet capsule and a read-only authenticated credit capsule. Detailed
  account, network, balance and purchase information remain in Wallet & Credits.
- Frosted upload, selected-file and Enhance surfaces; luminous Orb processing
  treatment; separate analysis, prompt and refinement result cards.
- Floating wallet sheet with a sticky close header, button-style 1/3/5 quantity
  controls and the existing Test ETH / Paxos USDG controls.
- Original ringed Orb surface motion remains left-to-right: 6 seconds in the
  header and 2.4 seconds during processing. The ring stays steady. Reduced motion
  disables surface animation, progress animation and result transitions.
- Visible focus outlines, opaque form fields, wrapping prompt text, safe-area
  bottom spacing and a compact two-column mode grid on mobile.

## Functional boundaries

All existing element IDs and the file input's accepted types were retained.
The actual file input is still positioned over the whole Choose File control,
with pointer events enabled. There is no programmatic picker click, label-only
activation, added asynchronous picker activation, or duplicate touch handler.
Readability checks, retry limits, cancellation and same-file reset logic are
unchanged. Supported sizes remain 20 MB for images and 200 MB for videos.

`web/app.js` only mirrors the existing authenticated `onBalance` notification
into the new header capsule, hiding it when unauthenticated. Its original
button synchronization and paid-job recovery calls are retained. `wallet.js`
and every backend file are unchanged. There are no changes to prices, fees,
transactions, authentication, AI requests, polling, credit settlement or data.

`vercel.json` disables Git deployment for `ui-liquid-glass-test`, alongside the
existing `usdg-test` restriction. This is a repository guard for the test branch;
no Vercel/Render service or environment configuration was changed. Main's
configuration remains unchanged.

## Validation and rendered checks

Run the existing checks from the Orb root:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q
npm.cmd run test:web -- --maxWorkers=1
$env:VITE_API_BASE_URL = 'https://orb-api.example.invalid'
npm.cmd run build:vercel
```

The backend suite was run without provider/database credentials, with the local
FFmpeg/FFprobe installation available. Real Postgres integration checks that
require an explicitly configured disposable database remain expected skips.
Result: **319 passed, 8 skipped**. The guarded production build passed with the
placeholder HTTPS origin. Full frontend result: **196 passed across 8 files**.
An overlapping validation run hit local worker-start/test timeouts; rerunning
the complete frontend suite alone passed without test or timeout changes.
No application dependency was added.

Rendered checks used headless Microsoft Edge/Chromium against an isolated local
Vite preview, with mocked API and EIP-1193 wallet responses. Non-local external
requests were blocked. There were no live AI calls, signatures or transactions.

| Viewport | Coverage |
| --- | --- |
| 1440 × 900 | Desktop home, Create, wallet, selected file, processing, results, Enhance |
| 1280 × 800 | Laptop layout and primary upload control visibility |
| 1024 × 800 | Compact desktop layout |
| 768 × 1024 | Tablet layout |
| 390 × 844 | Mobile layout and wallet sheet |
| 360 × 780 | Smaller mobile layout |
| 320 × 700 | Narrow mobile layout, wrapping and scroll access |

At all seven sizes, checks passed for no horizontal page overflow or clipped
controls; the real input receiving the Choose File hit target; exactly one
native filechooser event; Create opening and Escape dismissal; authenticated
header state; 3/5 selection and payment-method switching preserving quantity;
reachable sticky wallet close control; selected-file removal/reset; mocked
Decode image, Compose video and Enhance results; updated credits; long-text
wrapping; and reduced-motion computed styles. Each mocked operation produced
one request, with no duplicate visual submission.

Additional 1440px and 320px checks verified keyboard focus/activation, About
opening and closing, Copy Prompt copying the displayed text, and actual changing
Orb surface transforms. Screenshots and the local browser harness/report are
ignored artifacts under `output/liquid-glass/`, not committed runtime data.

## Browser limitations

Headless Chromium and mobile-width/touch emulation are not physical Zerion,
MetaMask, Rabby or Android Chrome testing. The standards-based direct file input
was preserved and activated successfully in Chromium; a wallet WebView's native
chooser limitations still require physical-device verification. Backdrop blur
is a progressive enhancement; unsupported browsers retain opaque surfaces.
Narrow screens scroll vertically to the upload control and long results.
No live wallet/payment/AI end-to-end verification is claimed for this visual pass.
