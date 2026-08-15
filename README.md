# VeriFrame

Synthetic-media (deepfake) detection platform — web app, Chrome extension, and public REST API sharing one detection core.

VeriFrame never outputs a binary "fake/real" verdict. It reports a calibrated probability with an explicit uncertainty band, backed by visual evidence (heatmaps, per-frame timelines, frequency-spectrum plots), and is always framed as a signal for human review, not proof. See [`CLAUDE.md`](./CLAUDE.md) for the full set of non-negotiable principles this project is built around.

## Status

Phase 3 — three detection streams (spatial CNN/ViT, frequency forensics, provenance) combined by weighted fusion, with calibration and fusion weights fitted by our own evaluation harness under a cross-dataset protocol. Upload an image in the browser and get an evidence-backed report with per-face results. Video, audio, temporal analysis, and the extension come in later phases.

Measured accuracy figures live in [`services/inference/eval/reports/`](./services/inference/eval/reports/) and are rendered on the app's `/accuracy` page. Nothing is hand-entered — see [the harness README](./services/inference/eval/README.md) for the protocol and its limits.

## Running the whole stack

```bash
docker compose up -d
```

Then, in separate terminals: the [inference service](./services/inference/README.md), the queue worker, and the web app — see [`apps/web/README.md`](./apps/web/README.md) for the exact commands and env setup.

## Structure

```
apps/web           Next.js web app (Phase 2)
apps/extension      Chrome MV3 extension via WXT (Phase 5)
services/inference   FastAPI + PyTorch/ONNX detection service (Phase 1+)
packages/core        Shared TS types, Zod schemas, band/fusion logic
packages/ui          Shared React components (web + extension)
```

## Local development

Requires Node 22+, pnpm 9+, Python 3.11, Docker.

```bash
pnpm install
docker compose up -d      # Postgres, Redis, MinIO
pnpm typecheck && pnpm lint && pnpm test
```

Copy `.env.example` to `.env` and fill in values before running any service.

The inference service has its own Python toolchain — see [`services/inference/README.md`](./services/inference/README.md) for setup, how a score is produced, and the configuration reference.

## Where the thresholds live

`packages/core/src/bands.json` is the single canonical band table. The TypeScript (`bands.ts`) and Python (`services/inference/app/bands.py`) sides both read that one file, and both test suites assert identical boundary behaviour. Change a threshold there and nowhere else.

## Build phases

See [`CLAUDE.md`](./CLAUDE.md#build-phases) for the phase breakdown. Each phase is reviewed before the next begins.

## Licensing

See [`LICENSES.md`](./LICENSES.md) for third-party dataset/model license tracking.
