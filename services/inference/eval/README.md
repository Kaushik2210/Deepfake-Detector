# Evaluation harness

Produces the only accuracy numbers VeriFrame is allowed to show. Every figure in the product traces to a file in `reports/`; nothing is hand-entered.

```bash
python -m eval.run --limit 1200 --write-calibration
```

Outputs `reports/<date>.md` and `reports/<date>.json`. With `--write-calibration` it also writes fitted temperatures and fusion weights to `packages/core/src/calibration.json`, which the inference service loads at runtime.

## Protocol

**Cross-dataset is mandatory and enforced in code.** Calibration is fitted on one corpus and every headline figure is reported on a different one; passing the same corpus for both is a CLI error. In-dataset figures are printed too, at the bottom, labelled as the numbers that flatter — the gap between them is the whole reason the protocol exists.

**Per-stream before fused.** Each stream is scored independently so its contribution is measured, not assumed. Fusion weights are derived from those measurements: proportional to how far a stream's AUC sits above chance, normalised, with zero for anything at or below chance. A stream is allowed to measure as useless.

**Robustness sweep.** The reporting corpus is re-encoded at several JPEG qualities and re-scored. Most media arrives recompressed, so degradation is part of the headline rather than an appendix.

## What the harness refuses to do

- **It will not report an unmeasurable metric.** TPR at FPR=0.1% needs roughly 1,000 authentic samples to see a single false positive. Below that, the row reads "not measurable" and shows the arithmetic, because an omitted row reads as "fine".
- **It will not hide sampling error.** AUC carries a bootstrap 95% confidence interval.
- **It will not invert a below-chance stream** to extract signal. That is fitting to the validation split, not measuring.

## Datasets

Streamed from the Hugging Face hub at run time and never committed. Both are ZIP archives read through HTTP range requests, so only the sampled images are transferred rather than the full 5.4 GB.

| Corpus | Licence | Role |
|---|---|---|
| `OpenRL/DeepFakeFace` | Apache-2.0 | calibration |
| `pujanpaudel/deepfake_face_classification` | **CC BY-NC 4.0** | reporting |

The reporting corpus is **non-commercial**. It is used for evaluation only — it contributes no weights and no code to the shipped product. If VeriFrame is commercialised it must be replaced and the numbers regenerated. See `LICENSES.md`.

## Runtime

Dominated by network, not CPU: thousands of small ranged reads against the hub, which rate-limits. A 1,200-per-corpus run with a robustness sweep takes a few hours on a home connection. Scoring itself is ~1.3 s per image on 12 CPU cores.

## Known limitation: contamination cannot be ruled out

The classifier's training data is not fully published, so overlap with these evaluation corpora is possible. If it exists, the figures are optimistic. This is stated at the top of every generated report.

## Known limitation: validation AUC and cross-dataset AUC can disagree

The completed run (`reports/2026-08-21.md`) is a live example: the frequency stream scored much higher than spatial on the calibration split (0.713 vs 0.534 AUC) and so received most of the fusion weight, but on the held-out reporting split spatial generalised better (0.663 vs 0.589 AUC) — the stream weighted more heavily is the one that transfers worse. This is the two corpora being different enough that tuning to one does not transfer to the other, and it is exactly what the mandatory cross-dataset protocol exists to expose.

Weights are still derived from the calibration split rather than the reporting split, deliberately: deriving them from the reporting split would mean the corpus backing the headline numbers had also been used to tune the model, which is the specific thing this protocol prevents. The correct fix is a third corpus — fit on one split, select the fitting procedure on a second, report only on a third untouched by either — which is future work, not yet implemented. See `DECISIONS.md`, 2026-08-21.
