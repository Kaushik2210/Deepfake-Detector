# Decisions

Running log of architectural choices and their rationale. Newest first.

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
