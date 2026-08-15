# VeriFrame

Synthetic-media (deepfake) detection platform — web app, Chrome extension, and public REST API sharing one detection core.

VeriFrame never outputs a binary "fake/real" verdict. It reports a calibrated probability with an explicit uncertainty band, backed by visual evidence (heatmaps, per-frame timelines, frequency-spectrum plots), and is always framed as a signal for human review, not proof. See [`CLAUDE.md`](./CLAUDE.md) for the full set of non-negotiable principles this project is built around.

## Status

Phase 1 — the inference service analyses **images** end to end: face detection, a ViT classifier with test-time augmentation, Grad-CAM heatmaps, out-of-distribution envelope checks, and an ONNX export path, served over a REST API. Video, audio, the remaining detection streams, the web app, and the extension come in later phases.

No accuracy claim is made yet. The cross-dataset eval harness that would justify one is Phase 3 work; see [`services/inference/README.md`](./services/inference/README.md) for a documented false positive on genuine media that shows why.

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
