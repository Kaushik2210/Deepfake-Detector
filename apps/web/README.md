# VeriFrame Web App

Next.js 15 app: upload an image, get an evidence-backed report. Phase 2.

## What runs today

| Piece | Status |
|---|---|
| Upload with explicit per-item consent | ✅ |
| Group photos: per-face results + plain-language conclusion | ✅ |
| Job queue (BullMQ) + standalone worker | ✅ |
| Report page with heatmap, bands, envelope | ✅ |
| Media TTL sweep (default 24h) | ✅ |
| Deletion endpoint (DPDP / GDPR) | ✅ |
| Privacy policy page | ✅ |
| Clerk auth | ⚠️ wired, runs in dev-bypass without keys |
| Video, audio, extension, hash-cache lookup | ❌ later phases |

## Running it

Four things need to be up. From the repo root:

```bash
docker compose up -d
```

```bash
pnpm --filter @veriframe/web db:migrate
```

Then the inference service (see `services/inference/README.md`), the worker, and the web app:

```bash
pnpm --filter @veriframe/web worker
```

```bash
pnpm --filter @veriframe/web dev
```

Copy the env template before first run:

```bash
cp .env.example apps/web/.env.local
```

## Auth

Clerk is wired but optional locally. Without `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` the app attributes every request to a single development user rather than refusing to boot, so the rest of the stack is workable without a Clerk account.

This is not a "skip auth" switch. `authDisabled()` throws if the keys are missing when `NODE_ENV=production`, and the ownership checks downstream run against a real user id either way — so the authorization path is identical in both modes.

## Data flow

```
browser ──POST /api/analyze──▶ MinIO (media)
                            └▶ Postgres (job row, status=queued)
                            └▶ Redis (BullMQ job)
                                      │
worker ◀──────────────────────────────┘
  ├─ fetch media from MinIO
  ├─ POST to inference service
  └─ write AnalysisReport to Postgres (status=complete)

browser ──GET /api/analyze/:id──▶ polls until complete, then renders
```

## Retention: two different paths

These behave differently and the privacy policy documents both.

- **Automatic expiry.** After `MEDIA_TTL_HOURS` the sweep deletes the object from storage, nulls `storage_key`, and stamps `media_deleted_at`. The job row and the perceptual hash survive, so the user can still read their report and a repeat upload can be recognised.
- **User deletion.** `DELETE /api/analyze/:id` removes the object *and* the row, hash included. Nothing is retained.

The sweep marks a row deleted only after the object-store delete succeeds. Doing it the other way round would leave orphaned media that no later sweep would ever revisit.

## Consent

The consent checkbox is unchecked by default and the submit button stays disabled until it is ticked — but that is only the visible half. `POST /api/analyze` rejects any request without `consent=true` **before** anything is written to storage, so bypassing the client does not bypass the gate. There is a test asserting that ordering.

## Local development gotcha

Rebuilding `packages/core` while `next dev` is running invalidates webpack chunks the dev server is holding, and it starts throwing `Cannot find module './vendor-chunks/...'`. Same if a production `next build` runs against the same `.next`. The fix is to stop the dev server, `rm -rf .next`, and restart.

## Notes on the UI

Band labels, thresholds, and the footer disclaimer are all read from `@veriframe/core` rather than restated here; tests assert the strings are *not* duplicated in the components, because a copied disclaimer would silently go stale when `bands.json` changes.

The score is drawn as an interval across the full band scale rather than a marker at a point, since a single tick invites reading the number as more precise than it is.
