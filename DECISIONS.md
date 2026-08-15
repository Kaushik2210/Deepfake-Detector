# Decisions

Running log of architectural choices and their rationale. Newest first.

## 2026-08-15 — Fusion weights are measured, and a stream is allowed to measure as useless

`derive_fusion_weights` sets each stream's weight proportional to how far its validation AUC sits above chance, normalised. A stream at or below 0.5 gets exactly zero and contributes nothing. Two consequences were chosen deliberately:

- A stream measuring **below** chance is not inverted to extract signal from it. Inverting would be fitting to the validation split rather than measuring, and would leave a detector whose reasoning we could not explain.
- When no fitted weights exist, fusion falls back to a single stream and says so, rather than averaging with invented weights. An unfitted product should behave conservatively, not guess.

## 2026-08-15 — The frequency stream must not move a no-face result

Stream B runs on the whole frame, so it produces a score even when no face is found. Wiring it into the no-face path initially dragged a blank gradient to 0.376 — "weak indication, likely benign" — which asserts the image was examined and looked fine. It was not examined; the primary detector could not run.

Stream B's thresholds are derived from face imagery and it has no validated standalone accuracy on anything else, so on the no-face path it is reported as context but contributes nothing to the score, which stays at 0.5. Stream D is treated differently and still overrides, because it reads recorded facts rather than inferring from pixels and needs no face. There is a regression test naming this specific failure.

## 2026-08-15 — Provenance overrides rather than being heavily weighted

A valid C2PA manifest or self-identifying generator metadata is categorically better evidence than a statistical detector, so Stream D acts through clamp/floor rather than through a weight. Both stop short of certainty: the generator floor leaves the score below 1.0 because such metadata is trivially removable and forgeable, and the C2PA clamp does not zero the score because a signature attests to a signing chain, not to the content being unaltered before signing.

`trusted_signer` is always reported as unknown. We maintain no signer allow-list, and claiming trust we cannot substantiate would be worse than admitting the gap.

## 2026-08-15 — Unmeasurable metrics report themselves as unmeasurable

TPR at FPR=0.1% needs at least ~1,000 authentic samples to observe a single false positive, and far more for a stable estimate. Rather than print a number derived from a handful of events, `tpr_at_fpr` returns "not measurable" with the arithmetic explaining why, and the report and accuracy page render that text. A missing row reads as "fine"; an explicit "not measurable" does not. AUC carries a bootstrap confidence interval for the same reason — sampling error should be visible rather than implied.

## 2026-08-15 — Evaluation corpora are streamed from ZIP archives, never committed

Neither corpus is published as parquet, so `datasets.load_dataset` streaming is unavailable. Both are ZIPs on the Hugging Face hub, which is served with HTTP range support, so `HfFileSystem` plus `zipfile` reads individual members without downloading whole archives — a few hundred images instead of 5.4 GB. The trade-off is many small ranged requests, which is I/O-bound and rate-limited; a full run takes hours on a home connection, dominated by network rather than CPU.

The reporting corpus is CC BY-NC 4.0. Using it for evaluation only was a deliberate decision: it contributes no weights and no code to the product, only numbers in a report. If VeriFrame is commercialised it must be replaced and the numbers regenerated. This is recorded in `LICENSES.md`.

## 2026-08-15 — No second backbone adopted, and why that is recorded rather than worked around

Every candidate for the second ensemble member is blocked. The best on the merits (`yermandy`, MIT, CLIP ViT-L/14, real cross-dataset numbers) does not document its preprocessing — its README defers to the DeepfakeBench pipeline — nor which logit means "fake", and runs at ~6.8 s per forward pass on CPU. The only architecturally distinct model with standard loading (`Organika/sdxl-detector`, Swin) is CC-BY-NC-3.0, and unlike an eval dataset, weights ship inside the product.

Wiring either in with guessed normalisation would produce confident nonsense rather than a visible failure, so neither was adopted. The ensemble machinery is built and tested so that adding one later is configuration. Details in `LICENSES.md`.

## 2026-08-15 — Group photos: the maximum face score needed a multiplicity correction

Reporting the highest face score as the image score has a defect that shows up precisely on group photos. Every face tested is another opportunity for a high score to appear by chance, so an eight-person photo has many more chances to produce one than a portrait. Left uncorrected, group photos would score systematically higher than solo photos for reasons unrelated to manipulation — and this detector already returns 0.71 on a genuine photograph, so the base rate of spurious highs is not negligible.

`aggregate.py` keeps the maximum as the headline, because one manipulated face does mean the image is manipulated, but distinguishes three cases:

- **One face elevated among several.** Penalised by a factor that shrinks as face count grows, floored at 0.55 so a crowd scene never erases a real signal. This is the face-swap shape, but also the shape chance produces.
- **Every face elevated.** No multiplicity penalty, because coincidence does not explain a uniform result. Instead a caveat that a detector reacting identically to every face usually points at a whole-image cause — AI generation, filtering, unusual compression — rather than each person being edited separately.
- **Some but not all elevated.** Reported as genuinely ambiguous, with the per-face detail left to distinguish real findings from faces that are merely small or badly lit.

## 2026-08-15 — Each face carries its own envelope, not the image's

A group photo mixes a 200px front-row face with a 30px face at the back. Judging both against image-level measurements would report identical confidence for two findings that deserve very different confidence. `assess_face` measures size, blur and exposure on each face's own crop, and the small-face penalty scales with how far under the threshold the face falls rather than being a flat cut.

## 2026-08-15 — The conclusion is assembled from templates, not generated

The plain-language summary is what most readers will actually read, which makes it the easiest place to accidentally state a verdict. It is built from fixed templates chosen by the face-count pattern, so its claims can be unit-tested and cannot drift into overclaiming. Tests assert that no phrasing across every reachable pattern resolves to "is fake" or equivalent, that a clean result still says detectors miss things, and that the advice points at provenance — which beats any statistical detector.

## 2026-08-15 — Schema modules split to break a cycle

`FaceFinding` needs `EnvelopePenalty`, and `AnalysisReport` needs `FaceFinding`. Keeping the penalty schema in `analysis-report.ts` would have made the two modules circular, which breaks at runtime for Zod values even though TypeScript tolerates it at type level. `envelope.ts` now holds the penalty and envelope schemas and both import from it.

## 2026-08-15 — Expiry and user deletion are deliberately different

Two retention paths, because they answer different questions. The TTL sweep deletes the stored media but keeps the job row and the perceptual hash, so the user can still read the report they were given and a repeat upload can be recognised without retaining the image. User-initiated deletion removes everything including the hash.

The privacy policy documents both separately. An earlier draft described only the expiry behaviour and claimed the hash was kept "after deletion", which was wrong for the deletion endpoint — an inaccuracy in a compliance document, so the text now distinguishes the two.

The sweep marks a row deleted only after the object-store delete returns successfully. The reverse order would leave orphaned media that no later sweep would ever select, since the query filters on `media_deleted_at IS NULL`.

## 2026-08-15 — Consent is enforced server-side, not just in the UI

The checkbox gates the submit button, but `POST /api/analyze` independently rejects any request without `consent=true`, and does so before writing to object storage. A test asserts the consent check appears earlier in the handler than the `putMedia` call, since a gate that runs after the write is not a gate.

## 2026-08-15 — Clerk optional locally, mandatory in production

Requiring a Clerk account before any of the queue, storage, or report work could be exercised would have blocked the whole phase on an external signup. Instead `authDisabled()` returns true only when keys are absent *and* `NODE_ENV !== "production"` — it throws otherwise, so the bypass cannot reach production. In bypass mode requests are attributed to a fixed development user id rather than skipping the ownership checks, keeping the authorization path identical in both modes.

Job lookups are scoped by user id, so another user's job and a non-existent job are both a 404 and are indistinguishable from outside.

## 2026-08-15 — Worker is a separate process

The queue consumer runs as its own `tsx` process rather than inside a Next.js route handler, matching how it deploys. One consequence worth recording: it does not get Next's automatic `.env.local` loading, so it loads the file itself via `process.loadEnvFile` from a module imported before anything reads `process.env` — import bodies evaluate in order, whereas a bare statement at the top of the worker entry would still run after that module's own imports resolved.

## 2026-08-15 — `next lint` replaced with a direct ESLint invocation

`next lint` is deprecated, will be removed in Next.js 16, and prompts interactively when no ESLint config exists — which would hang CI rather than fail it. The app uses a flat `eslint.config.mjs` wrapping `next/core-web-vitals` through `FlatCompat`, invoked as `eslint .`.

## 2026-08-15 — YuNet replaces both face detectors named in the spec

The spec proposed RetinaFace or YOLOv8-face. Both block commercial use: Ultralytics YOLOv8 is AGPL-3.0 and that covers the trained models, not just the training code, so shipping it commercially means open-sourcing all of VeriFrame or buying an Enterprise License; InsightFace's code is MIT but its pretrained RetinaFace weights are released for non-commercial research only.

YuNet is MIT-licensed, ~230 KB, and runs through OpenCV's own `cv2.FaceDetectorYN`, so it adds no dependency beyond OpenCV, which the pipeline needs anyway. Recorded in `LICENSES.md` along with the rejected options.

Note OpenCV 5.x requires the dynamic-input-shape build of the model (`face_detection_yunet_2026may.onnx`) while 4.x needs the fixed-shape one; `faces.py` selects by OpenCV major version.

## 2026-08-15 — Phase 1 classifier: prithivMLmods ViT, with yermandy noted for Phase 3

Four candidates were checked for existence and license. `Wvolf/ViT_Deepfake_Detection` declares no license and was discarded — no license means no rights granted. `dima806/deepfake_vs_real_image_detection` is Apache-2.0 but is another fine-tune of the same `google/vit-base-patch16-224-in21k` base as the chosen model, so pairing them later would violate the architectural-diversity requirement, and its author warns of significant concept drift.

`prithivMLmods/Deep-Fake-Detector-v2-Model` (Apache-2.0) was chosen for Phase 1 because it loads through standard `transformers` and has a clean Grad-CAM path, getting the full pipeline working end-to-end quickly.

`yermandy/deepfake-detection` (MIT, CLIP ViT-L/14 + LN-tuning) is the strongest candidate found on the merits — it is the only one publishing a genuine cross-dataset protocol (trained on FaceForensics++, reporting 96.62% AUROC on Celeb-DF-v2 and 87.15% on DFDC) and is architecturally distinct from ViT-base. It needs custom loading code, so it is deferred to the Phase 3 ensemble rather than blocking Phase 1.

## 2026-08-15 — The band table is data, not code

`packages/core/src/bands.json` is the canonical table. `bands.ts` imports it and `services/inference/app/bands.py` reads the same file, so a threshold exists in exactly one place across both languages. Boundary semantics (lower bound inclusive, upper exclusive except for the final band) are asserted identically in the Vitest and pytest suites, because a disagreement would mean the same score is labelled differently in the API and the UI.

## 2026-08-15 — Absence of evidence is reported as inconclusive, not as clean

When no face is detected, Stream A cannot run. The service returns 0.5, which lands in "Mixed signals — inconclusive, manual review advised", with a full-width uncertainty interval and an explicit envelope penalty. Returning a low score would imply we looked and found nothing, which is a different and false claim.

## 2026-08-15 — The confidence penalty shrinks the score toward 0.5 and widens the interval

Out-of-envelope inputs accumulate multiplicative penalties, each with a human-readable reason. The combined multiplier is applied as `score = 0.5 + (raw - 0.5) * confidence` and also widens the uncertainty band. Shrinking toward the uninformative midpoint is the honest response to "we don't trust this input" — the alternative, reporting the raw score with a quiet caveat, keeps a confident-looking number on screen.

Every report also carries a permanent uncalibrated-score penalty until Phase 3 fits temperature scaling, since raw softmax outputs are overconfident.

## 2026-08-15 — Uncertainty from TTA spread is a stopgap, and labelled as one

The architecture calls for ensemble disagreement across architecturally different backbones as the primary uncertainty source. Phase 1 has a single backbone, so the spread across the four test-time augmentations substitutes. It is a strictly weaker signal — it measures sensitivity to flip and scale, not error decorrelation — and in practice is very small (~0.001 on clean input). It is labelled as a weak proxy in the report artifacts rather than presented as a real uncertainty estimate, and is replaced in Phase 3.

## 2026-08-15 — ONNX export is a single self-contained file

`torch.onnx.export` on torch 2.13 defaults to splitting weights into a sibling `.onnx.data`, which loads fine locally and produces a silently broken model if only the `.onnx` is copied to a deployment. At ~340 MB this model sits well inside protobuf's 2 GB ceiling, so `external_data=False` is the default and a test asserts no sibling files are produced. The torch path remains the default at runtime because Grad-CAM needs autograd; a test asserts the two backends agree to 1e-3.

## 2026-08-14 — Repo initialized fresh, scoped to project folder

The git repository originally present on this machine was rooted at the user's home directory (`C:\Users\Kaushik`) rather than the project folder, and was tracking unrelated projects and OS/profile directories. Rather than reuse or fix that repo, a new git repository was initialized directly inside the `Deepfake-Analyser` project folder so history and remotes stay scoped to VeriFrame only.

## 2026-08-14 — Phase 0 scope

Full monorepo skeleton built up front (pnpm + Turborepo workspaces for all apps/packages, Docker Compose, CI, `packages/core` fully implemented). `apps/web`, `apps/extension`, `packages/ui`, and `services/inference` are workspace stubs only — real implementation starts in their respective phases (2, 5, 2, 1) — so the workspace graph resolves and CI has something to run against without pretending unbuilt surfaces are done.
