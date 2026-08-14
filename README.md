# VeriFrame

Synthetic-media (deepfake) detection platform — web app, Chrome extension, and public REST API sharing one detection core.

VeriFrame never outputs a binary "fake/real" verdict. It reports a calibrated probability with an explicit uncertainty band, backed by visual evidence (heatmaps, per-frame timelines, frequency-spectrum plots), and is always framed as a signal for human review, not proof. See [`CLAUDE.md`](./CLAUDE.md) for the full set of non-negotiable principles this project is built around.

## Status

Phase 0 (foundation) — monorepo scaffold only. No detection logic yet.

## Structure

```
apps/web           Next.js web app (Phase 2)
apps/extension      Chrome MV3 extension via WXT (Phase 5)
services/inference   FastAPI + PyTorch/ONNX detection service (Phase 1+)
packages/core        Shared TS types, Zod schemas, band/fusion logic
packages/ui          Shared React components (web + extension)
```

## Local development

Requires Node 22+, pnpm 9+, Python 3.11+, Docker.

```bash
pnpm install
docker compose up -d      # Postgres, Redis, MinIO
pnpm typecheck
pnpm lint
pnpm test
```

Copy `.env.example` to `.env` and fill in values before running any service.

## Build phases

See [`CLAUDE.md`](./CLAUDE.md#build-phases) for the phase breakdown. Each phase is reviewed before the next begins.

## Licensing

See [`LICENSES.md`](./LICENSES.md) for third-party dataset/model license tracking.
