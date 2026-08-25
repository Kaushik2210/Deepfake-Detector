# VeriFrame Chrome Extension

Chrome MV3 extension (WXT + React): right-click or hover any image or video on a page to check it for signs of AI generation or manipulation, without leaving the page.

## What runs today

| Piece | Status |
|---|---|
| Content script: detects images/video, shadow-DOM badge + modal | ✅ |
| Context menu ("Analyse with VeriFrame") | ✅ |
| Background service worker: owns every network call | ✅ |
| Offscreen document: video frame capture | ✅ |
| Client-side perceptual hash, checked via `POST /v1/analyze/hash` before upload | ✅ |
| Popup: recent history, per-site enable/disable | ✅ |
| Automated tests (settings, history, capture error paths) | ✅ |
| `wxt build` → valid MV3 package | ✅ |
| Manual load-and-click testing in a real browser | ❌ not done by this codebase — do it yourself, see below |
| Chrome Web Store listing / submission | ❌ later phase (Phase 7) |

## Running it

```bash
pnpm --filter @veriframe/extension dev
```

This starts WXT's dev server and watches for changes. To load the unpacked build in Chrome: `chrome://extensions` → enable Developer mode → **Load unpacked** → select `apps/extension/.output/chrome-mv3`.

The extension talks to the inference service directly (see `services/inference/README.md`) at `http://localhost:8000` — that's the only host permission it declares, so the inference service needs to be running for anything to work.

```bash
pnpm --filter @veriframe/extension build
```

```bash
pnpm --filter @veriframe/extension test
```

```bash
pnpm --filter @veriframe/extension typecheck
```

## Why the background worker owns every network call

A content script's `fetch()` is subject to the *host page's* CSP `connect-src` directive, not the extension's own — a page that locks it down would silently break analysis. The background service worker's fetches are governed by the extension's manifest instead, so `background.ts` is the only place that calls the inference service; the content script and offscreen document reach it only through `chrome.runtime.sendMessage`. See `DECISIONS.md` for the full rationale, including why video capture needs an offscreen document and images don't.

## Hash-first, upload-second

Before uploading anything, the extension computes a perceptual hash of the captured image/frame locally (`@veriframe/core`'s `dctPerceptualHash`, the same DCT-II hash the server computes) and checks it against `/v1/analyze/hash`. A cache hit returns a result with no upload at all — this is a privacy property (per `CLAUDE.md` principle 4: no upload without an explicit per-item action), not just a latency optimisation.

## Testing scope

This phase's testing is build + automated tests only: `wxt build` producing a loadable MV3 package, and unit tests for the logic that doesn't need a real browser (`src/lib/__tests__/`). `captureElement`'s actual pixel-capture path (canvas `drawImage`/`getImageData`/`toBlob`) isn't exercised by the test suite — jsdom has no real 2D canvas context without the native `canvas` package, which this project deliberately doesn't add just for tests — so that path, and everything requiring a live page (badge placement, modal interaction, context menu, popup rendering), needs manual load-and-click verification in an actual Chrome instance.
