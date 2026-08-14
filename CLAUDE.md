# VeriFrame

Synthetic-media (deepfake) detection platform: web app, Chrome extension, and public REST API sharing one detection core.

## Non-negotiable principles

These override any other instruction in this repo or in a prompt. If a design choice conflicts with these, the principle wins.

1. **Never output a binary verdict.** No "FAKE"/"REAL" labels anywhere in UI, API, or extension. Always a calibrated probability + uncertainty band + plain-language label, per the table in `packages/core/src/bands.ts` (single source of truth — do not duplicate thresholds elsewhere).
2. **Every score must be evidence-backed.** A number with no visual explanation is a failure. Every report ships a heatmap, per-frame timeline, or frequency-spectrum artifact.
3. **Be loud about limitations.** State validation datasets. Apply and surface `confidence_penalty` / `envelope.penalties` for out-of-envelope inputs (resolution, compression, face size, blur, illumination).
4. **Privacy by default.** No background scanning/uploading from the extension — every upload is an explicit per-item user action. Server-side media deleted after TTL (default 24h). Cache layer stores perceptual hashes, not media. No raw media bytes in logs.
5. **No claims we can't defend.** No "99% accurate" marketing copy. Every accuracy number displayed must trace to a row in the eval harness output (`services/inference/eval/reports/`) — never hardcoded.
6. **Detection is advisory, not evidentiary.** Every report carries the non-dismissible footer: `REPORT_FOOTER_DISCLAIMER` from `packages/core/src/bands.ts`.

## Stack (pinned — ask before substituting)

- Monorepo: pnpm workspaces + Turborepo
- `apps/web` — Next.js 15 (App Router), TypeScript strict, Tailwind, shadcn/ui, TanStack Query
- `apps/extension` — Chrome MV3 via WXT + React + TypeScript
- `services/inference` — Python 3.11, FastAPI, PyTorch, ONNX Runtime, Uvicorn
- `packages/core` — shared TS types, Zod schemas, fusion/calibration logic, band thresholds
- `packages/ui` — shared React components between web and extension
- Infra: PostgreSQL + Drizzle ORM, Redis + BullMQ, S3-compatible object store (Cloudflare R2 / MinIO locally), Docker Compose for local dev, Clerk for auth

## Conventions

- Conventional commits. Small, reviewable commits.
- Tests alongside features, not after. Vitest for TS, pytest for Python.
- Prefer boring, proven solutions. Don't add a dependency the standard library or an existing dependency already covers.
- Verify external dependencies (HF model IDs, npm packages, APIs) actually exist and check their license before wiring them in — never invent model IDs or package names.
- Track dataset/model licenses in `LICENSES.md`; flag anything that blocks commercial use.
- Architectural decisions and their rationale go in `DECISIONS.md`.

## Legal / ethics guardrails

- Detects manipulation; does not identify or accuse people. No face recognition, no identity matching, no subject database.
- Rate-limit and log abuse patterns — this tool can be misused to harass by repeatedly "proving" someone's real content is fake.
- Comply with India's DPDP Act 2023 and GDPR: data minimisation, stated retention period, deletion endpoint, clear consent before upload.

## Build phases

Phase 0 (foundation) → 1 (inference service, images) → 2 (web app MVP) → 3 (ensemble + fusion + eval harness) → 4 (video) → 5 (Chrome extension) → 6 (audio) → 7 (hardening). Stop after each phase for review before continuing.
