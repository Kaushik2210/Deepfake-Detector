"""Evaluation harness CLI.

    python -m eval.run --limit 2000

Protocol, and why it is shaped this way:

- **Cross-dataset is mandatory.** Calibration is fitted on one corpus and every
  headline number is reported on a different one. In-dataset figures are printed
  too, but labelled as what they are — the number that flatters, and the number
  most published results quote.
- **Per-stream before fused.** Each stream is scored independently so its
  contribution is measured rather than assumed, and so fusion weights can be
  derived from those measurements.
- **Robustness sweep.** Detectors degrade under recompression and downscaling,
  which is the state most real media arrives in, so the degradation curve is part
  of the report rather than an appendix.

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

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import spatial  # noqa: E402
from app.pipeline.faces import crop_face, detect_faces  # noqa: E402
from app.pipeline.frequency import analyze_frequency  # noqa: E402
from app.pipeline.provenance import analyze_provenance  # noqa: E402
from eval import calibrate, metrics  # noqa: E402
from eval.datasets import DATASETS, DatasetSpec, Sample, load_samples  # noqa: E402
from eval.report import write_report  # noqa: E402

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class ScoredSample:
    label: int
    spatial: float | None
    frequency: float
    provenance_fired: bool
    faces_found: int
    dataset: str


@dataclass
class DatasetRun:
    spec: DatasetSpec
    samples: list[ScoredSample] = field(default_factory=list)
    skipped_no_face: int = 0
    seconds: float = 0.0


def score_sample(sample: Sample, encode_quality: int | None = None) -> ScoredSample:
    """Run every stream over one image."""
    image = sample.image_bgr

    if encode_quality is not None:
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), encode_quality])
        raw = buffer.tobytes() if ok else b""
        if ok:
            image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    else:
        ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        raw = buffer.tobytes() if ok else b""

    faces = detect_faces(image)

    spatial_score: float | None = None
    if faces:
        crops = [
            cv2.cvtColor(crop_face(image, face), cv2.COLOR_BGR2RGB) for face in faces[:3]
        ]
        scores = [spatial.score_crop(crop)[0] for crop in crops]
        spatial_score = float(max(scores))

    frequency = analyze_frequency(image, raw, render_plot=False).score
    provenance = analyze_provenance(raw, "image/jpeg") if raw else None

    return ScoredSample(
        label=sample.label,
        spatial=spatial_score,
        frequency=frequency,
        provenance_fired=bool(provenance and provenance.fired),
        faces_found=len(faces),
        dataset=sample.dataset,
    )


def _cache_path(spec: DatasetSpec, limit: int, seed: int, encode_quality: int | None) -> Path:
    """Where partial scores for this exact configuration are kept."""
    suffix = "orig" if encode_quality is None else f"q{encode_quality}"
    cache_dir = Path(__file__).resolve().parent / ".score_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{spec.key}_n{limit}_s{seed}_{suffix}.jsonl"


def _load_cached(path: Path) -> dict[str, ScoredSample]:
    if not path.is_file():
        return {}

    cached: dict[str, ScoredSample] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                cached[row["key"]] = ScoredSample(
                    label=row["label"],
                    spatial=row["spatial"],
                    frequency=row["frequency"],
                    provenance_fired=row["provenance_fired"],
                    faces_found=row["faces_found"],
                    dataset=row["dataset"],
                )
            except (json.JSONDecodeError, KeyError):
                # A line truncated by a hard kill; the sample is simply rescored.
                continue
    return cached


def run_dataset(
    spec: DatasetSpec,
    limit: int,
    seed: int,
    encode_quality: int | None = None,
    progress_every: int = 100,
) -> DatasetRun:
    """Score a split, resuming from any partial run of the same configuration.

    Reads are ranged HTTP requests against the hub, which rate-limits and times
    out; two earlier runs died hours in and lost everything. Each score is
    appended to a JSONL cache as it is produced, so a rerun picks up where the
    last one stopped. The sample order is deterministic for a given seed, so
    cache keys line up across runs.
    """
    run = DatasetRun(spec=spec)
    started = time.time()

    cache_file = _cache_path(spec, limit, seed, encode_quality)
    cached = _load_cached(cache_file)
    if cached:
        print(f"  [{spec.key}] resuming, {len(cached)} already scored", flush=True)

    reused = 0
    with cache_file.open("a", encoding="utf-8") as handle:
        for index, sample in enumerate(load_samples(spec, limit=limit, seed=seed), start=1):
            scored = cached.get(sample.key)
            if scored is not None:
                reused += 1
            else:
                scored = score_sample(sample, encode_quality)
                handle.write(
                    json.dumps(
                        {
                            "key": sample.key,
                            "label": scored.label,
                            "spatial": scored.spatial,
                            "frequency": scored.frequency,
                            "provenance_fired": scored.provenance_fired,
                            "faces_found": scored.faces_found,
                            "dataset": scored.dataset,
                        }
                    )
                    + "\n"
                )
                handle.flush()

            if scored.spatial is None:
                run.skipped_no_face += 1
            run.samples.append(scored)

            if progress_every and index % progress_every == 0:
                elapsed = time.time() - started
                print(
                    f"  [{spec.key}] {index} scored ({elapsed:.0f}s, "
                    f"{run.skipped_no_face} without a detectable face"
                    + (f", {reused} from cache" if reused else "")
                    + ")",
                    flush=True,
                )

    run.seconds = time.time() - started
    return run


def _arrays(run: DatasetRun, stream: str) -> tuple[np.ndarray, np.ndarray]:
    """Labels and scores for one stream, dropping samples it could not score."""
    labels: list[int] = []
    scores: list[float] = []

    for sample in run.samples:
        value = sample.spatial if stream == "spatial" else sample.frequency
        if value is None:
            continue
        labels.append(sample.label)
        scores.append(value)

    return np.array(labels), np.array(scores)


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriFrame evaluation harness")
    parser.add_argument("--limit", type=int, default=2000, help="samples per dataset")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--calibrate-on", default="deepfakeface", choices=sorted(DATASETS)
    )
    parser.add_argument("--report-on", default="df40faces", choices=sorted(DATASETS))
    parser.add_argument(
        "--robustness",
        default="90,60,30",
        help="comma-separated JPEG qualities for the degradation sweep, or 'none'",
    )
    parser.add_argument(
        "--robustness-limit",
        type=int,
        default=400,
        help="samples per quality level in the sweep (kept small; it reruns per level)",
    )
    parser.add_argument("--write-calibration", action="store_true")
    args = parser.parse_args()

    if args.calibrate_on == args.report_on:
        parser.error(
            "calibration and reporting datasets must differ: the cross-dataset "
            "protocol is what makes these numbers meaningful"
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)

    print(f"Calibration split: {args.calibrate_on}")
    calibration_run = run_dataset(DATASETS[args.calibrate_on], args.limit, args.seed)

    print(f"Reporting split:   {args.report_on}")
    reporting_run = run_dataset(DATASETS[args.report_on], args.limit, args.seed)

    # --- per-stream metrics on the calibration split, used to derive weights ---
    stream_metrics: dict[str, dict] = {}
    stream_aucs: dict[str, float] = {}

    for stream in ("spatial", "frequency"):
        labels, scores = _arrays(calibration_run, stream)
        if len(labels) < 20 or labels.min() == labels.max():
            continue
        result = metrics.evaluate(labels, scores)
        stream_metrics[stream] = result.to_dict()
        stream_aucs[stream] = result.auc

    weights = calibrate.derive_fusion_weights(stream_aucs)

    # --- temperature fitted on the calibration split only ---
    temperatures: dict[str, float] = {}
    for stream in stream_aucs:
        labels, scores = _arrays(calibration_run, stream)
        temperature, nll = calibrate.fit_temperature(labels, scores)
        temperatures[stream] = temperature
        print(f"  {stream}: temperature {temperature:.3f} (NLL {nll:.4f})")

    # --- reporting split, before and after calibration ---
    reporting_metrics: dict[str, dict] = {}
    for stream in stream_aucs:
        labels, scores = _arrays(reporting_run, stream)
        if len(labels) < 20 or labels.min() == labels.max():
            continue

        raw_result = metrics.evaluate(labels, scores)
        calibrated_scores = calibrate.apply_temperature(scores, temperatures[stream])
        calibrated_result = metrics.evaluate(labels, calibrated_scores)

        reporting_metrics[stream] = {
            "raw": raw_result.to_dict(),
            "calibrated": calibrated_result.to_dict(),
        }

    # --- robustness sweep on the reporting split ---
    robustness: dict[str, dict] = {}
    if args.robustness.lower() != "none":
        qualities = [int(q) for q in args.robustness.split(",") if q.strip()]
        sweep_limit = min(args.limit, args.robustness_limit)
        for quality in qualities:
            print(f"  robustness sweep at JPEG q{quality} ...")
            sweep = run_dataset(
                DATASETS[args.report_on],
                sweep_limit,
                args.seed,
                encode_quality=quality,
                progress_every=0,
            )
            entry: dict[str, float] = {}
            for stream in stream_aucs:
                labels, scores = _arrays(sweep, stream)
                if len(labels) >= 20 and labels.min() != labels.max():
                    entry[stream] = round(metrics.auc_score(labels, scores), 4)
            robustness[str(quality)] = entry

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
                "hf_id": DATASETS[key].hf_id,
                "licence": DATASETS[key].licence,
                "commercial_use": DATASETS[key].commercial_use,
                "description": DATASETS[key].description,
            }
            for key in (args.calibrate_on, args.report_on)
        },
        "coverage": {
            args.calibrate_on: {
                "scored": len(calibration_run.samples),
                "no_face_detected": calibration_run.skipped_no_face,
                "seconds": round(calibration_run.seconds, 1),
            },
            args.report_on: {
                "scored": len(reporting_run.samples),
                "no_face_detected": reporting_run.skipped_no_face,
                "seconds": round(reporting_run.seconds, 1),
            },
        },
        "in_dataset_metrics": stream_metrics,
        "cross_dataset_metrics": reporting_metrics,
        # Stream D reads embedded provenance, which these corpora do not carry.
        # Recorded explicitly so its absence from the metrics tables reads as
        # "could not be measured here" rather than "forgotten".
        "provenance_stream": {
            "measurable": False,
            "fired_on_calibration_split": sum(
                1 for s in calibration_run.samples if s.provenance_fired
            ),
            "fired_on_reporting_split": sum(
                1 for s in reporting_run.samples if s.provenance_fired
            ),
            "note": (
                "Stream D reads C2PA manifests and generator metadata. Neither corpus "
                "ships images carrying either, so no AUC can be computed for it here. "
                "That is a property of the evaluation data, not evidence the stream "
                "does not work — but it does mean its fusion weight cannot be derived "
                "from measurement, so it is excluded from weighted fusion and used "
                "only through its override path."
            ),
        },
        "temperature": temperatures,
        "fusion_weights": [
            {"stream": w.stream, "auc": w.auc, "weight": w.weight, "rationale": w.rationale}
            for w in weights
        ],
        "robustness_auc_by_jpeg_quality": robustness,
    }

    stamp = started.strftime("%Y-%m-%d")
    json_path = REPORTS_DIR / f"{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md_path = REPORTS_DIR / f"{stamp}.md"
    write_report(md_path, payload)

    if args.write_calibration:
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "packages" / "core" / "src" / "calibration.json"
        calibrate.write_calibration(
            target,
            temperatures,
            weights,
            {**provenance_meta, "report": f"services/inference/eval/reports/{stamp}.md"},
        )
        print(f"wrote {target}")

    print(f"\nwrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
