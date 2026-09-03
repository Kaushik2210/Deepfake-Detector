# Deployment guide

Five moving pieces, three of them needing an account only you can create (I can't sign up for services or hold your API keys — this walks you through each step, you do the account/secret parts). Total cost: free tier on every piece below covers a demo/portfolio deployment; a real user base with meaningful traffic would need to move off free tiers.

## Topology

```
Browser ──▶ Vercel (apps/web: Next.js — pages, API routes, upload)
              │        │
              │        ▼
              │   Railway: Postgres, Redis
              │        ▲
              ▼        │
        Railway worker (apps/web/src/worker — BullMQ job consumer + TTL sweep)
              │
              ▼
        Railway: inference service (services/inference — FastAPI, PyTorch)
              │
              ▼
        Cloudflare R2 (S3-compatible object storage for uploaded media)

Clerk (auth) sits alongside all of this — Vercel and the worker both talk to it.
```

**Why the worker is a separate service, not part of Vercel:** `apps/web/src/worker/index.ts` runs `pnpm worker` as a long-lived process (BullMQ job consumer, TTL sweep loop). Vercel's serverless functions can't run a persistent background process — the worker needs its own always-on host, which is why it's a second Railway service rather than something Vercel handles.

## 1. Clerk (authentication)

1. Create a free account and application at [clerk.com](https://clerk.com).
2. From the application's API Keys page, copy the **Publishable key** and **Secret key**. You'll paste these into Vercel and Railway's dashboards in the steps below — never into a chat with me or anyone else.
3. `authDisabled()` (`apps/web/src/lib/env.ts`) throws if these keys are missing in a production build, so the app will refuse to start in prod without them — this is deliberate, not a bug to work around.

## 2. Cloudflare R2 (object storage)

1. In the Cloudflare dashboard, create an R2 bucket (e.g. `veriframe-media`).
2. Create an R2 API token scoped to that bucket (Account → R2 → Manage API Tokens). Note the **Access Key ID**, **Secret Access Key**, and your account's R2 **endpoint URL** (`https://<account-id>.r2.cloudflarestorage.com`).
3. R2's free tier (10 GB storage, no egress fees) comfortably covers a demo deployment given the 24-hour media TTL sweep keeps storage from accumulating.

## 3. Railway (Postgres, Redis, inference service, worker)

1. Create a Railway project at [railway.app](https://railway.app), connect your GitHub account, and select this repo.
2. **Add Postgres and Redis** as Railway-managed plugins in the same project — each gives you a connection string (`DATABASE_URL` / `REDIS_URL` equivalents) in its own Variables tab.
3. **Inference service**: add a new service from this repo, set its **root directory** to `services/inference` (Railway will find the `Dockerfile` there automatically). Set these environment variables on that service:
   - `VERIFRAME_DATABASE_URL` — the Postgres connection string from step 2
   - `VERIFRAME_REDIS_URL` — the Redis connection string from step 2
   - `VERIFRAME_PUBLIC_BASE_URL` — this service's own public Railway URL (needed so artifact URLs like heatmaps resolve correctly cross-origin; you'll know this URL only after the first deploy, so deploy once, then set this and redeploy)
   - Everything else in `services/inference/app/config.py` has a sane default; override only if you need to (e.g. tighter rate limits).
   - Consider attaching a persistent volume at the model cache directory so pretrained weights (~340 MB+) don't re-download on every redeploy.
4. **Worker service**: add a second new service from the same repo, root directory = repo root (it needs the full pnpm workspace). Build command: `pnpm install --frozen-lockfile`. Start command: `pnpm --filter @veriframe/web worker`. Set the same env vars this service needs from `.env.example` (`DATABASE_URL`, `REDIS_URL`, `S3_*`, `CLERK_SECRET_KEY`, `INFERENCE_SERVICE_URL` pointing at the inference service's Railway URL, `MEDIA_TTL_HOURS`).
5. **Run migrations once** against the Railway Postgres instance: `pnpm --filter @veriframe/web db:migrate` with `DATABASE_URL` pointed at it (run this from your machine, or as a one-off Railway job).

## 4. Vercel (the web app)

1. Import this repo at [vercel.com](https://vercel.com/new).
2. Set the project's **Root Directory** to `apps/web` (monorepo support — Vercel auto-detects Next.js from there).
3. Set every variable from `.env.example` in the Vercel project's Environment Variables page, using real values: the Railway `DATABASE_URL`/`REDIS_URL`, the R2 `S3_*` values from step 2, the Clerk keys from step 1, and `INFERENCE_SERVICE_URL` pointing at the Railway inference service's public URL.
4. Deploy. Vercel handles the build (`next build`) and serving; no `vercel.json` is needed for this app.

## 5. Verify before calling it done

- Upload a small image on the deployed site, confirm a report renders with a heatmap (proves storage + inference service + artifact URLs are all wired correctly).
- Confirm the report disappears after deleting it, and check back in 24+ hours (or temporarily lower `MEDIA_TTL_HOURS`) to confirm the TTL sweep is actually running on the worker service.
- Toggle dark mode, check `/accuracy` and `/methodology` render the real eval numbers.
- Re-read `/terms` and `/responsible-ai` — the governing-law/contact fields are already filled in, but **get the Terms of Use page reviewed by an actual lawyer before this handles real users' data at any scale beyond a demo.**

## Not covered here

- **Chrome extension publishing** — needs your own Chrome Web Store developer account (one-time $5 fee, Google-owned process); nothing in this repo can do that step for you.
- **A custom domain** — set it up in Vercel's dashboard once you have one; not required to have a working deployment.
- **CI** (`.github/workflows/ci.yml`) already runs on every push/PR to `master`/`main` — it doesn't deploy anything, just typechecks/lints/tests/builds both workspaces.
