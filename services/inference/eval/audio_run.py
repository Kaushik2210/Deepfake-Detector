"""Audio evaluation harness CLI.

    python -m eval.audio_run --limit 600

Same mandatory protocol as eval/run.py: calibration is fitted on one corpus and
every headline figure is reported on a different one. Audio has no exact
equivalent of "downscale/recompress a JPEG", so the robustness sweep instead
adds Gaussian noise at a few SNR levels -- background noise is the audio
condition that plays the same role real-world recompression plays for images:
almost every phone call or voice note carries some.

Datasets are never written into the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.models.audio_registry import get_audio_model, score_waveform  # noqa: E402
from app.pipeline import audio_frequency as audio_frequency_mod  # noqa: E402
from app.pipeline.audio_io import prepare_for_model  # noqa: E402
from eval import calibrate, metrics  # noqa: E402
from eval.audio_datasets import (  # noqa: E402
    AUDIO_DATASETS,
    AudioDatasetSpec,
    AudioSample,
    load_audio_samples,
)
from eval.audio_report import write_audio_report  # noqa: E402
from eval.splits import stratified_half_split  # noqa: E402

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

STREAMS = ("audio", "audio_frequency")


@dataclass
class ScoredAudioSample:
    key: str
    label: int
    scores: dict[str, float]
    dataset: str


@dataclass
class AudioDatasetRun:
    spec: AudioDatasetSpec
    samples: list[ScoredAudioSample] = field(default_factory=list)
    seconds: float = 0.0


def add_noise(waveform: np.ndarray, snr_db: float, seed: int = 0) -> np.ndarray:
    """Additive white Gaussian noise at a target signal-to-noise ratio."""
    rng = np.random.default_rng(seed)
    signal_power = float(np.mean(waveform.astype(np.float64) ** 2))
    if signal_power <= 0:
        return waveform
    noise_power = signal_power / (10 ** (snr_db / 10))
    noise = rng.normal(0.0, np.sqrt(noise_power), size=waveform.shape).astype(np.float32)
    return (waveform + noise).astype(np.float32)


def score_sample(sample: AudioSample, snr_db: float | None = None) -> ScoredAudioSample:
    settings = get_settings()
    waveform = sample.waveform if snr_db is None else add_noise(sample.waveform, snr_db)

    model = get_audio_model()
    tensor = prepare_for_model(
        waveform, sample.sample_rate, settings.audio_target_sample_rate,
        settings.audio_target_samples,
    )
    scores = {"audio": score_waveform(model, tensor)}

    freq_result = audio_frequency_mod.measure(waveform, sample.sample_rate)
    if freq_result.score is not None:
        scores["audio_frequency"] = freq_result.score

    return ScoredAudioSample(
        key=sample.key, label=sample.label, scores=scores, dataset=sample.dataset
    )


def _cache_path(spec: AudioDatasetSpec, limit: int, seed: int, snr_db: float | None) -> Path:
    suffix = "orig" if snr_db is None else f"snr{snr_db}"
    cache_dir = Path(__file__).resolve().parent / ".audio_score_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{spec.key}_n{limit}_s{seed}_{suffix}.jsonl"


def _load_cached(path: Path) -> dict[str, ScoredAudioSample]:
    if not path.is_file():
        return {}

    cached: dict[str, ScoredAudioSample] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                # Older cache files (before the audio_frequency stream existed)
                # wrote a single "score" field; read those as audio-only.
                scores = row["scores"] if "scores" in row else {"audio": row["score"]}
                cached[row["key"]] = ScoredAudioSample(
                    key=row["key"], label=row["label"], scores=scores, dataset=row["dataset"]
                )
            except (json.JSONDecodeError, KeyError):
                continue
    return cached


def run_dataset(
    spec: AudioDatasetSpec,
    limit: int,
    seed: int,
    snr_db: float | None = None,
    progress_every: int = 50,
) -> AudioDatasetRun:
    """Score a split, resuming from any partial run of the same configuration."""
    run = AudioDatasetRun(spec=spec)
    started = time.time()

    cache_file = _cache_path(spec, limit, seed, snr_db)
    cached = _load_cached(cache_file)
    if cached:
        print(f"  [{spec.key}] resuming, {len(cached)} already scored", flush=True)

    reused = 0
    with cache_file.open("a", encoding="utf-8") as handle:
        for index, sample in enumerate(
            load_audio_samples(spec, limit=limit, seed=seed), start=1
        ):
            scored = cached.get(sample.key)
            if scored is not None:
                reused += 1
            else:
                scored = score_sample(sample, snr_db)
                handle.write(
                    json.dumps(
                        {
                            "key": scored.key,
                            "label": scored.label,
                            "scores": scored.scores,
                            "dataset": scored.dataset,
                        }
                    )
                    + "\n"
                )
                handle.flush()

            run.samples.append(scored)

            if progress_every and index % progress_every == 0:
                elapsed = time.time() - started
                print(
                    f"  [{spec.key}] {index} scored ({elapsed:.0f}s)"
                    + (f", {reused} from cache" if reused else ""),
                    flush=True,
                )

    run.seconds = time.time() - started
    return run


def _arrays(run: AudioDatasetRun, stream: str) -> tuple[np.ndarray, np.ndarray]:
    """Labels and scores for one stream, dropping samples it could not score
    (audio_frequency has no score for a clip with no measurable periodicity)."""
    labels: list[int] = []
    scores: list[float] = []
    for sample in run.samples:
        value = sample.scores.get(stream)
        if value is None:
            continue
        labels.append(sample.label)
        scores.append(value)
    return np.array(labels), np.array(scores)


def _fused_scores(
    run: AudioDatasetRun, weights: dict[str, float]
) -> tuple[np.ndarray, np.ndarray]:
    """Per-sample fused score using this run's own just-derived weights.

    Not fusion.fuse() itself: that function reads weights from
    packages/core/src/calibration.json on disk, which is exactly the file this
    run may not have written to yet (only does with --write-calibration) --
    using it here would mean evaluating against whatever weights happened to
    already be on disk, not the weights this specific run measured. Audio
    never hits fuse()'s generator-marker/C2PA override paths (those are
    image/video-only), so a plain weighted average is a faithful stand-in for
    what fuse() would compute given the same weights.
    """
    total = sum(w for w in weights.values() if w > 0)
    labels: list[int] = []
    fused_scores: list[float] = []
    for sample in run.samples:
        if total <= 0:
            available = [(n, s) for n, s in sample.scores.items() if n in STREAMS]
            if not available:
                continue
            fused = max(available, key=lambda ns: weights.get(ns[0], 0.0))[1]
        else:
            contributing = [
                (weights[n], sample.scores[n])
                for n in STREAMS
                if n in sample.scores and weights.get(n, 0.0) > 0
            ]
            if not contributing:
                continue
            fused = sum(w * s for w, s in contributing) / sum(w for w, _ in contributing)
        labels.append(sample.label)
        fused_scores.append(fused)
    return np.array(labels), np.array(fused_scores)


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriFrame audio evaluation harness")
    parser.add_argument("--limit", type=int, default=600, help="samples per dataset")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--calibrate-on", default="asvspoof2019", choices=sorted(AUDIO_DATASETS)
    )
    parser.add_argument("--report-on", default="asvspoof2021", choices=sorted(AUDIO_DATASETS))
    parser.add_argument(
        "--report-limit",
        type=int,
        default=None,
        help=(
            "total samples drawn from the reporting corpus (defaults to --limit), "
            "split in half by label: one half selects the fusion weights via a "
            "genuine cross-dataset AUC, the other is the untouched final reporting "
            "split -- see DECISIONS.md"
        ),
    )
    parser.add_argument(
        "--robustness",
        default="25,15,5",
        help="comma-separated SNR dB levels for the noise sweep, or 'none'",
    )
    parser.add_argument("--robustness-limit", type=int, default=200)
    parser.add_argument("--write-calibration", action="store_true")
    args = parser.parse_args()

    if args.calibrate_on == args.report_on:
        parser.error(
            "calibration and reporting datasets must differ: the cross-dataset "
            "protocol is what makes these numbers meaningful"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)

    print(f"Calibration split: {args.calibrate_on}", flush=True)
    calibration_run = run_dataset(AUDIO_DATASETS[args.calibrate_on], args.limit, args.seed)

    report_limit = args.report_limit or args.limit
    print(f"Reporting pool:    {args.report_on} (n={report_limit}, split in half)", flush=True)
    report_pool = run_dataset(AUDIO_DATASETS[args.report_on], report_limit, args.seed)

    # The reporting corpus is split once, stratified by label, into two disjoint
    # halves: `validation_run` selects the fusion weights (a genuine cross-dataset
    # AUC, since it comes from a different corpus than calibration), and
    # `final_run` is touched exactly once, after weights are already fixed, for
    # the headline numbers. See DECISIONS.md -- deriving weights from the
    # calibration split's in-distribution AUC is what previously produced a
    # fusion weight that made cross-dataset AUC *worse*, because in-distribution
    # AUC does not predict cross-dataset generalisation.
    validation_samples, final_samples = stratified_half_split(
        report_pool.samples, label_fn=lambda s: s.label
    )
    validation_run = AudioDatasetRun(spec=report_pool.spec, samples=validation_samples)
    final_run = AudioDatasetRun(spec=report_pool.spec, samples=final_samples)

    in_dataset_metrics: dict[str, dict] = {}
    calib_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for stream in STREAMS:
        labels, scores = _arrays(calibration_run, stream)
        calib_arrays[stream] = (labels, scores)
        if len(labels) >= 20 and labels.min() != labels.max():
            in_dataset_metrics[stream] = metrics.evaluate(labels, scores).to_dict()

    validation_metrics: dict[str, dict] = {}
    stream_aucs: dict[str, float] = {}
    for stream in STREAMS:
        labels, scores = _arrays(validation_run, stream)
        if len(labels) >= 20 and labels.min() != labels.max():
            result = metrics.evaluate(labels, scores)
            validation_metrics[stream] = result.to_dict()
            stream_aucs[stream] = result.auc

    weights = calibrate.derive_fusion_weights(stream_aucs)
    weight_by_stream = {w.stream: w.weight for w in weights}

    temperatures: dict[str, float] = {}
    for stream, (labels, scores) in calib_arrays.items():
        if len(labels) < 20 or labels.min() == labels.max():
            continue
        temperature, nll = calibrate.fit_temperature(labels, scores)
        temperatures[stream] = temperature
        print(f"  {stream}: temperature {temperature:.3f} (NLL {nll:.4f})")

    cross_dataset_metrics: dict[str, dict] = {}
    for stream in STREAMS:
        labels, scores = _arrays(final_run, stream)
        if len(labels) < 20 or labels.min() == labels.max():
            continue
        raw_result = metrics.evaluate(labels, scores)
        calibrated_scores = (
            calibrate.apply_temperature(scores, temperatures[stream])
            if stream in temperatures
            else scores
        )
        calibrated_result = metrics.evaluate(labels, calibrated_scores)
        cross_dataset_metrics[stream] = {
            "raw": raw_result.to_dict(),
            "calibrated": calibrated_result.to_dict(),
        }

    # The actual question this second stream exists to answer: does fusing it
    # with AASIST improve on AASIST alone, on the final held-out split -- the one
    # that played no part in choosing the fusion weight? Reported honestly either
    # way -- see DECISIONS.md for the answer this run gave.
    fused_labels, fused_scores = _fused_scores(final_run, weight_by_stream)
    fused_metrics: dict | None = None
    if len(fused_labels) >= 20 and fused_labels.min() != fused_labels.max():
        fused_metrics = metrics.evaluate(fused_labels, fused_scores).to_dict()
        audio_only_auc = cross_dataset_metrics.get("audio", {}).get("raw", {}).get("auc")
        if audio_only_auc is not None:
            delta = fused_metrics["auc"] - audio_only_auc
            print(
                f"  fusion vs. AASIST alone on {args.report_on}: "
                f"{audio_only_auc:.4f} -> {fused_metrics['auc']:.4f} "
                f"({'+' if delta >= 0 else ''}{delta:.4f})",
                flush=True,
            )

    robustness: dict[str, dict] = {}
    if args.robustness.lower() != "none":
        snr_levels = [float(x) for x in args.robustness.split(",") if x.strip()]
        sweep_limit = min(args.limit, args.robustness_limit)
        for snr in snr_levels:
            print(f"  robustness sweep at {snr:g}dB SNR ...")
            sweep = run_dataset(
                AUDIO_DATASETS[args.report_on],
                sweep_limit,
                args.seed,
                snr_db=snr,
                progress_every=0,
            )
            entry: dict[str, float] = {}
            for stream in STREAMS:
                s_labels, s_scores = _arrays(sweep, stream)
                if len(s_labels) >= 20 and s_labels.min() != s_labels.max():
                    entry[stream] = round(metrics.auc_score(s_labels, s_scores), 4)
            if entry:
                robustness[str(snr)] = entry

    provenance_meta = {
        "generated_at": started.isoformat(),
        "calibration_dataset": args.calibrate_on,
        "reporting_dataset": args.report_on,
        "samples_per_dataset": args.limit,
        "report_pool_samples": len(report_pool.samples),
        "validation_samples": len(validation_run.samples),
        "final_reporting_samples": len(final_run.samples),
        "seed": args.seed,
    }

    payload = {
        "provenance": provenance_meta,
        "datasets": {
            key: {
                "hf_id": AUDIO_DATASETS[key].hf_id,
                "licence": AUDIO_DATASETS[key].licence,
                "commercial_use": AUDIO_DATASETS[key].commercial_use,
                "description": AUDIO_DATASETS[key].description,
            }
            for key in (args.calibrate_on, args.report_on)
        },
        "coverage": {
            args.calibrate_on: {
                "scored": len(calibration_run.samples),
                "seconds": round(calibration_run.seconds, 1),
            },
            args.report_on: {
                "scored": len(report_pool.samples),
                "validation_scored": len(validation_run.samples),
                "final_reporting_scored": len(final_run.samples),
                "seconds": round(report_pool.seconds, 1),
            },
        },
        "in_dataset_metrics": in_dataset_metrics,
        "weight_validation_metrics": validation_metrics,
        "cross_dataset_metrics": cross_dataset_metrics,
        "fused_cross_dataset_metrics": fused_metrics,
        "temperature": temperatures,
        "fusion_weights": [
            {"stream": w.stream, "auc": w.auc, "weight": w.weight, "rationale": w.rationale}
            for w in weights
        ],
        "robustness_auc_by_snr_db": robustness,
    }

    stamp = started.strftime("%Y-%m-%d")
    json_path = REPORTS_DIR / f"audio-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md_path = REPORTS_DIR / f"audio-{stamp}.md"
    write_audio_report(md_path, payload)

    if args.write_calibration:
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "packages" / "core" / "src" / "calibration.json"
        calibrate.write_calibration(
            target,
            temperatures,
            weights,
            {**provenance_meta, "report": f"services/inference/eval/reports/audio-{stamp}.md"},
        )
        print(f"wrote {target}")

    print(f"\nwrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
