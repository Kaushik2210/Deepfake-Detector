# Decisions

Running log of architectural choices and their rationale. Newest first.

## 2026-08-14 — Repo initialized fresh, scoped to project folder

The git repository originally present on this machine was rooted at the user's home directory (`C:\Users\Kaushik`) rather than the project folder, and was tracking unrelated projects and OS/profile directories. Rather than reuse or fix that repo, a new git repository was initialized directly inside the `Deepfake-Analyser` project folder so history and remotes stay scoped to VeriFrame only.

## 2026-08-14 — Phase 0 scope

Full monorepo skeleton built up front (pnpm + Turborepo workspaces for all apps/packages, Docker Compose, CI, `packages/core` fully implemented). `apps/web`, `apps/extension`, `packages/ui`, and `services/inference` are workspace stubs only — real implementation starts in their respective phases (2, 5, 2, 1) — so the workspace graph resolves and CI has something to run against without pretending unbuilt surfaces are done.

## 2026-08-14 — GitHub remote deferred

GitHub MCP connector returned "Bad credentials" and no `gh` CLI is installed locally, so the repo has no `origin` yet. Work proceeds with local commits; push happens once GitHub auth is available.
