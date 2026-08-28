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

Dominated by network, not CPU. Images: thousands of small ranged reads against the hub, which rate-limits — a 1,200-per-corpus run with a robustness sweep takes a few hours on a home connection; scoring itself is ~1.3 s per image on 12 CPU cores. Audio: the 2019 (parquet) split scores in roughly 1-1.5s/sample; the 2021 (ZIP) split is much slower per sample (~3-4s observed, unauthenticated, plus periodic connection resets that retry with backoff) since each member is its own ranged HTTP read against a single 36.7 GB archive, and re-listing that archive's central directory (needed at the start of every draw, cache hits included) is itself a slow, occasionally flaky network call.

A 60-per-corpus run once scored 60/60 on 2019 but only 31/60 on 2021 — not a data-availability limit but a bug: the candidate plan was capped at the target count *before* any decode was attempted, so a decode failure permanently lost that slot with nothing to backfill it. Fixed in `audio_datasets.py`'s `_load_asvspoof2021` by trying every shuffled candidate in plan order until the quota is actually met, the same way the streaming 2019 loader naturally does — a 100-per-corpus run after the fix scored 100/100 on both. The default `--robustness-limit` (200) can still be too high for a short session given the 2021 split's per-draw overhead; pass a smaller value or fewer `--robustness` levels to keep a run's wall-clock time bounded.

`--report-limit` controls the total pool drawn from the reporting corpus, split in half by label into a weight-validation set and a final reporting set (see the fix note below) — it defaults to `--limit` if omitted.

## Known limitation: contamination cannot be ruled out

The classifier's training data is not fully published, so overlap with these evaluation corpora is possible. If it exists, the figures are optimistic. This is stated at the top of every generated report.

## Fixed: fusion weights are derived from a held-out validation split, not the calibration split

The completed run (`reports/2026-08-21.md`) was a live example of the problem: the frequency stream scored much higher than spatial on the calibration split (0.713 vs 0.534 AUC) and so received most of the fusion weight, but on the held-out reporting split spatial generalised better (0.663 vs 0.589 AUC) — the stream weighted more heavily was the one that transferred worse. Deriving weights from the reporting split directly was not an option either: that would mean the corpus backing the headline numbers had also been used to tune the model, the specific thing the cross-dataset protocol exists to prevent.

The fix, implemented in `eval/splits.py` and wired into both harnesses: the reporting corpus is split once, stratified by label, into a weight-validation half (a genuine cross-dataset measurement, since it comes from a different corpus than calibration — used only to derive fusion weights) and a final reporting half (touched exactly once, after weights are already fixed, for the headline numbers). This is not literally the third corpus described below as the methodologically purest fix — it is the same held-out guarantee obtained from the one reporting corpus that already exists, split in two instead of used whole for both jobs. Re-running audio with this fix (`reports/audio-2026-08-28.md`) confirms it works: fusing `audio_frequency` at its old calibration-split-derived weight cost -0.0294 AUC versus AASIST alone; at its new validation-split-derived weight it costs only -0.0064. See `DECISIONS.md`, 2026-08-28, for the full numbers. The image harness has not yet been re-run with this fix as of this note.

A literal third, independent corpus — fit calibration on one, select the fitting procedure on a second, report only on a third untouched by either — remains the methodologically purest version of this fix and is still not implemented; it is blocked on finding a second commercially-licensed reporting-quality corpus per media kind (see `LICENSES.md`'s rejected-candidates lists, which is most of why this project has exactly two usable corpora per media kind rather than three).

## Audio: the harness caught a real inversion bug before it was trusted

The completed run (`reports/audio-2026-08-25.md`) is a live example of exactly what a mandatory eval harness is for. The audio classifier shipped with its spoof/bonafide output index backwards (sourced from a wrong AI-generated summary of the upstream model's eval script). Running the calibration split — the corpus AASIST was trained on, where a working classifier should score close to perfectly — produced AUC **0.0**, not a mediocre number but a *perfectly inverted* one (mean score 0.017 on spoof samples, 0.998 on bonafide). That shape gave the bug away: a broken classifier looks like noise around 0.5 AUC, not a clean 0.0. Fixed against the model's actual training code and rerun: in-dataset AUC **1.000**, cross-dataset AUC **0.962** (EER 6.5%) on ASVspoof2021. See `DECISIONS.md` for the full story, including three earlier wrong AI-generated claims caught the same way while building this harness (a dataset's licence, and twice a dataset's actual repo ID).

## Audio: a hand-derived second stream that measured well and still made things worse

Phase 7 added `audio_frequency` (harmonics-to-noise ratio, `app/pipeline/audio_frequency.py`) as a second, independently-designed audio signal, fused with AASIST the same way every other multi-stream media kind in this project fuses its streams. An early run (n=60, calibration-split-derived weights, superseded — the numbers below are from the current `reports/audio-2026-08-28.md`) reported the harness doing exactly its job: the new stream measured AUC 0.907 in-dataset but only 0.685 cross-dataset, and fusing it at its calibration-derived weight *reduced* cross-dataset AUC from 0.962 to 0.933. Identical shape to the validation/cross-dataset disagreement above — the frequency stream in the image pipeline generalised worse despite scoring higher on its own calibration split, this stream did too — confirming the pattern independently in a different modality with a completely different measurement, and motivating the validation-split fix described above. Re-run with that fix (n=100/50/50, current `reports/audio-2026-08-28.md`), `audio_frequency`'s validation-split AUC (0.6528) is a much closer estimate of its true cross-dataset value than the old in-distribution number was, its fusion weight dropped from 0.4485 to 0.243 accordingly, and the fused-vs-alone gap shrank from -0.0294 to -0.0064 AUC. Still a net negative on this held-out split — reported honestly either way, per principle 5 — but a much smaller one, purely from fitting the weight against the right kind of measurement. See `DECISIONS.md`, 2026-08-28.
