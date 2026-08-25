# Evaluation harness

Produces the only accuracy numbers VeriFrame is allowed to show. Every figure in the product traces to a file in `reports/`; nothing is hand-entered.

```bash
python -m eval.run --limit 1200 --write-calibration
```

```bash
python -m eval.audio_run --limit 600 --write-calibration
```

Outputs `reports/<date>.md` / `reports/<date>.json` (images) and `reports/audio-<date>.md` / `reports/audio-<date>.json` (audio). With `--write-calibration` either one writes its fitted temperature and fusion weight into `packages/core/src/calibration.json`, which the inference service loads at runtime — the two harnesses merge into that file rather than overwrite each other (see `calibrate.write_calibration`).

## Protocol

**Cross-dataset is mandatory and enforced in code.** Calibration is fitted on one corpus and every headline figure is reported on a different one; passing the same corpus for both is a CLI error. In-dataset figures are printed too, at the bottom, labelled as the numbers that flatter — the gap between them is the whole reason the protocol exists.

**Per-stream before fused.** Each stream is scored independently so its contribution is measured, not assumed. Fusion weights are derived from those measurements: proportional to how far a stream's AUC sits above chance, normalised, with zero for anything at or below chance. A stream is allowed to measure as useless.

**Robustness sweep.** The reporting corpus is re-encoded at several JPEG qualities and re-scored (audio: white Gaussian noise added at several SNR levels instead, since audio has no direct equivalent of JPEG recompression, but background noise plays the same "this is what real deployment conditions actually look like" role). Most media arrives degraded somehow, so that is part of the headline rather than an appendix.

## What the harness refuses to do

- **It will not report an unmeasurable metric.** TPR at FPR=0.1% needs roughly 1,000 authentic samples to see a single false positive. Below that, the row reads "not measurable" and shows the arithmetic, because an omitted row reads as "fine".
- **It will not hide sampling error.** AUC carries a bootstrap 95% confidence interval.
- **It will not invert a below-chance stream** to extract signal. That is fitting to the validation split, not measuring.

## Datasets

Streamed from the Hugging Face hub at run time and never committed.

**Images** — both are ZIP archives read through HTTP range requests (`datasets.py`), so only the sampled images are transferred rather than the full 5.4 GB.

| Corpus | Licence | Role |
|---|---|---|
| `OpenRL/DeepFakeFace` | Apache-2.0 | calibration |
| `pujanpaudel/deepfake_face_classification` | **CC BY-NC 4.0** | reporting |

The reporting corpus is **non-commercial**. It is used for evaluation only — it contributes no weights and no code to the shipped product. If VeriFrame is commercialised it must be replaced and the numbers regenerated. See `LICENSES.md`.

**Audio** (`audio_datasets.py`) — the two corpora needed genuinely different loading strategies, discovered by trying each:

| Corpus | Licence | Role | Loaded via |
|---|---|---|---|
| `Bisher/ASVspoof_2019_LA` | ODC-By | calibration | `datasets.load_dataset(..., streaming=True)` — proper parquet chunking |
| `Bisher/ASVspoof_2021_DF` | ODbL (primary source) | reporting | `HfFileSystem` + `zipfile`, same pattern as the image corpora above |

The 2021 repo's entire payload is one 36.7 GB ZIP behind a custom loading script; `streaming=True` cannot avoid downloading the whole thing for a repo shaped that way. Read the same way the image corpora's ZIPs already are instead — ranged reads for the central directory plus individual members, never the archive as a whole. Both datasets are decoded through this project's own `soundfile`-based `audio_io.decode_audio`, not `datasets`'s default (which needs `torchcodec`, which needs a system FFmpeg install this project avoids for the shipped service).

Unusually, **both audio splits are commercial-use-clean** — no replacement-before-commercialisation caveat needed the way the image reporting split has. Verified against Zenodo's own record metadata after an initial search-engine summary got the licence wrong; see `LICENSES.md` and `DECISIONS.md`.

## Runtime

Dominated by network, not CPU. Images: thousands of small ranged reads against the hub, which rate-limits — a 1,200-per-corpus run with a robustness sweep takes a few hours on a home connection; scoring itself is ~1.3 s per image on 12 CPU cores. Audio: the 2019 (parquet) split scores in roughly 1-1.5s/sample; the 2021 (ZIP) split is much slower per sample (~13s observed, unauthenticated) since each member is its own ranged HTTP read, and a meaningful fraction of requested samples fail to score at all (a 60-per-corpus run scored 60/60 on 2019 but only 31/60 on 2021) — increase `--limit` to compensate rather than expect the requested count to land exactly. The robustness sweep's default `--robustness-limit` (200) is too optimistic for this yield rate at small `--limit`; a 20-sample sweep on the 2021 split produced too few successes to report anything.

## Known limitation: contamination cannot be ruled out

The classifier's training data is not fully published, so overlap with these evaluation corpora is possible. If it exists, the figures are optimistic. This is stated at the top of every generated report.

## Known limitation: validation AUC and cross-dataset AUC can disagree

The completed run (`reports/2026-08-21.md`) is a live example: the frequency stream scored much higher than spatial on the calibration split (0.713 vs 0.534 AUC) and so received most of the fusion weight, but on the held-out reporting split spatial generalised better (0.663 vs 0.589 AUC) — the stream weighted more heavily is the one that transfers worse. This is the two corpora being different enough that tuning to one does not transfer to the other, and it is exactly what the mandatory cross-dataset protocol exists to expose.

Weights are still derived from the calibration split rather than the reporting split, deliberately: deriving them from the reporting split would mean the corpus backing the headline numbers had also been used to tune the model, which is the specific thing this protocol prevents. The correct fix is a third corpus — fit on one split, select the fitting procedure on a second, report only on a third untouched by either — which is future work, not yet implemented. See `DECISIONS.md`, 2026-08-21.

## Audio: the harness caught a real inversion bug before it was trusted

The completed run (`reports/audio-2026-08-25.md`) is a live example of exactly what a mandatory eval harness is for. The audio classifier shipped with its spoof/bonafide output index backwards (sourced from a wrong AI-generated summary of the upstream model's eval script). Running the calibration split — the corpus AASIST was trained on, where a working classifier should score close to perfectly — produced AUC **0.0**, not a mediocre number but a *perfectly inverted* one (mean score 0.017 on spoof samples, 0.998 on bonafide). That shape gave the bug away: a broken classifier looks like noise around 0.5 AUC, not a clean 0.0. Fixed against the model's actual training code and rerun: in-dataset AUC **1.000**, cross-dataset AUC **0.962** (EER 6.5%) on ASVspoof2021. See `DECISIONS.md` for the full story, including three earlier wrong AI-generated claims caught the same way while building this harness (a dataset's licence, and twice a dataset's actual repo ID).
