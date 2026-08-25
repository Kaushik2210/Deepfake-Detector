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
from app.pipeline.audio_io import prepare_for_model  # noqa: E402
from eval import calibrate, metrics  # noqa: E402
from eval.audio_datasets import (  # noqa: E402
    AUDIO_DATASETS,
    AudioDatasetSpec,
    AudioSample,
    load_audio_samples,
)
from eval.audio_report import write_audio_report  # noqa: E402

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class ScoredAudioSample:
    key: str
    label: int
    score: float
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
    score = score_waveform(model, tensor)
    return ScoredAudioSample(
        key=sample.key, label=sample.label, score=score, dataset=sample.dataset
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
                cached[row["key"]] = ScoredAudioSample(
                    key=row["key"], label=row["label"], score=row["score"], dataset=row["dataset"]
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
                            "score": scored.score,
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


def _arrays(run: AudioDatasetRun) -> tuple[np.ndarray, np.ndarray]:
    labels = np.array([s.label for s in run.samples])
    scores = np.array([s.score for s in run.samples])
    return labels, scores


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriFrame audio evaluation harness")
    parser.add_argument("--limit", type=int, default=600, help="samples per dataset")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--calibrate-on", default="asvspoof2019", choices=sorted(AUDIO_DATASETS)
    )
    parser.add_argument("--report-on", default="asvspoof2021", choices=sorted(AUDIO_DATASETS))
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

    print(f"Reporting split:   {args.report_on}", flush=True)
    reporting_run = run_dataset(AUDIO_DATASETS[args.report_on], args.limit, args.seed)

    calib_labels, calib_scores = _arrays(calibration_run)

    in_dataset_metrics: dict[str, dict] = {}
    stream_aucs: dict[str, float] = {}
    if len(calib_labels) >= 20 and calib_labels.min() != calib_labels.max():
        result = metrics.evaluate(calib_labels, calib_scores)
        in_dataset_metrics["audio"] = result.to_dict()
        stream_aucs["audio"] = result.auc

    weights = calibrate.derive_fusion_weights(stream_aucs)

    temperatures: dict[str, float] = {}
    if "audio" in stream_aucs:
        temperature, nll = calibrate.fit_temperature(calib_labels, calib_scores)
        temperatures["audio"] = temperature
        print(f"  audio: temperature {temperature:.3f} (NLL {nll:.4f})")

    report_labels, report_scores = _arrays(reporting_run)
    cross_dataset_metrics: dict[str, dict] = {}
    if len(report_labels) >= 20 and report_labels.min() != report_labels.max():
        raw_result = metrics.evaluate(report_labels, report_scores)
        calibrated_scores = (
            calibrate.apply_temperature(report_scores, temperatures["audio"])
            if "audio" in temperatures
            else report_scores
        )
        calibrated_result = metrics.evaluate(report_labels, calibrated_scores)
        cross_dataset_metrics["audio"] = {
            "raw": raw_result.to_dict(),
            "calibrated": calibrated_result.to_dict(),
        }

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
            s_labels, s_scores = _arrays(sweep)
            if len(s_labels) >= 20 and s_labels.min() != s_labels.max():
                robustness[str(snr)] = {"audio": round(metrics.auc_score(s_labels, s_scores), 4)}

    provenance_meta = {
        "generated_at": started.isoformat(),
        "calibration_dataset": args.calibrate_on,
        "reporting_dataset": args.report_on,
        "samples_per_dataset": args.limit,
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
                "scored": len(reporting_run.samples),
                "seconds": round(reporting_run.seconds, 1),
            },
        },
        "in_dataset_metrics": in_dataset_metrics,
        "cross_dataset_metrics": cross_dataset_metrics,
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
