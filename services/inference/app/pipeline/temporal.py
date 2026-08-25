"""Stream C — temporal and biological signals (video only).

Four sub-signals, all unsupervised heuristics with hand-derived thresholds, not
trained classifiers — the same caveat Stream B carries, for the same reason: no
video evaluation dataset exists yet to measure or calibrate them against. Their
combined score is reported for evidence, but carries fusion weight 0.0 by
default until an eval run measures it, exactly how Stream B behaved before
Phase 3 fitted it.

Lip-sync / audio-visual desync, the fifth signal the architecture calls for, is
not implemented. Wav2Lip's weights are non-commercial (trained on the
BBC-licensed LRS2 corpus) and SyncNet's weights carry no stated license from
the same research lineage — both rejected for the same reason the second
ensemble backbone was in Phase 3. See LICENSES.md.

Physiological reference ranges cited below (blink rate, blink duration, pulse
band) are widely reported approximations from the vision-science and rPPG
literature, not fitted to any dataset this project has measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy import signal as scipy_signal

from app.config import get_settings
from app.pipeline.landmarks import FaceRegion, LandmarkFrame, detect
from app.pipeline.video_io import SampledFrame

# --- Blink ---
_BLINK_CLOSED_THRESHOLD = 0.5
# Typical waking blink rate is often cited as ~12-20/min, but focused
# screen/camera attention commonly halves that -- so only *zero* blinks over a
# long-enough window is treated as noteworthy, and even then only mildly.
_ZERO_BLINK_MIN_SECONDS = 4.0

# --- Head pose ---
# Sustained angular velocity above this is treated as atypically fast for
# ordinary head motion. Chosen as a round, documented guess, not fitted.
_POSE_JITTER_THRESHOLD_DEG_PER_SEC = 150.0

# --- rPPG ---
_PULSE_BAND_HZ = (0.7, 4.0)  # ~42-240 BPM, the usual rPPG working range
_PLAUSIBLE_BPM = (45.0, 150.0)
_MIN_COHERENCE_FOR_SIGNAL = 0.25


@dataclass
class TemporalResult:
    score: float
    measurable: bool
    measurements: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    signal_plot: bytes | None = None  # PNG bytes of the rPPG trace, if computed


def _face_crop_bounds(points_px: np.ndarray, width: int, height: int, pad: float = 0.15):
    x_min, y_min = points_px[:, 0].min(), points_px[:, 1].min()
    x_max, y_max = points_px[:, 0].max(), points_px[:, 1].max()
    w, h = x_max - x_min, y_max - y_min
    x0 = max(0, int(x_min - pad * w))
    y0 = max(0, int(y_min - pad * h))
    x1 = min(width, int(x_max + pad * w))
    y1 = min(height, int(y_max + pad * h))
    return x0, y0, x1, y1


def _optical_flow_discontinuity(
    frames: list[SampledFrame], landmarks: list[LandmarkFrame | None]
) -> tuple[float | None, dict[str, float]]:
    """Compare flow magnitude at the face-hull boundary against its interior.

    Face-swap blending seams tend to move slightly differently from the face
    they're composited onto, showing up as elevated flow right at the boundary
    relative to the interior. This is a coarse proxy for that, not a trained
    detector -- ordinary motion blur or fast head turns produce the same
    pattern, so it is one weak vote among several.
    """
    ratios: list[float] = []

    for i in range(1, len(frames)):
        prev_lm, curr_lm = landmarks[i - 1], landmarks[i]
        if prev_lm is None or curr_lm is None:
            continue

        height, width = frames[i].image_bgr.shape[:2]
        x0, y0, x1, y1 = _face_crop_bounds(curr_lm.points_px, width, height)
        if x1 - x0 < 20 or y1 - y0 < 20:
            continue

        prev_gray = cv2.cvtColor(frames[i - 1].image_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(frames[i].image_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        if prev_gray.shape != curr_gray.shape:
            continue

        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        magnitude = np.linalg.norm(flow, axis=2)

        hull_points = cv2.convexHull(
            (curr_lm.points_px - [x0, y0]).astype(np.int32)
        )
        interior_mask = np.zeros(magnitude.shape, dtype=np.uint8)
        cv2.fillConvexPoly(interior_mask, hull_points, 1)

        boundary_mask = cv2.dilate(interior_mask, np.ones((9, 9), np.uint8)) - interior_mask
        if interior_mask.sum() < 10 or boundary_mask.sum() < 10:
            continue

        interior_flow = float(magnitude[interior_mask.astype(bool)].mean())
        boundary_flow = float(magnitude[boundary_mask.astype(bool)].mean())
        if interior_flow < 1e-6:
            continue

        ratios.append(boundary_flow / interior_flow)

    if not ratios:
        return None, {}

    mean_ratio = float(np.mean(ratios))
    # Squash around a ratio of 1.5 (boundary moving 50% faster than interior)
    # into (0, 1); this is a shape choice, not a fitted calibration.
    score = float(1.0 / (1.0 + np.exp(-(mean_ratio - 1.5) * 2.0)))
    return score, {
        "boundary_interior_flow_ratio": round(mean_ratio, 4),
        "pairs_measured": len(ratios),
    }


def _blink_analysis(
    frames: list[SampledFrame], landmarks: list[LandmarkFrame | None]
) -> tuple[float | None, dict[str, float], list[str]]:
    valid = [
        (f.timestamp, max(lm.blink_left, lm.blink_right))
        for f, lm in zip(frames, landmarks, strict=True)
        if lm is not None
    ]
    if len(valid) < get_settings().video_min_dense_frames_for_blink:
        return None, {}, [
            "Too little of the clip had a tracked face to estimate a blink rate."
        ]

    timestamps = [t for t, _ in valid]
    span_seconds = timestamps[-1] - timestamps[0]
    if span_seconds < _ZERO_BLINK_MIN_SECONDS:
        return None, {}, ["Sampled window too short to estimate blink rate."]

    closed = [v > _BLINK_CLOSED_THRESHOLD for _, v in valid]
    events = 0
    durations: list[float] = []
    run_start: float | None = None
    for i, is_closed in enumerate(closed):
        if is_closed and run_start is None:
            run_start = timestamps[i]
        elif not is_closed and run_start is not None:
            durations.append(timestamps[i] - run_start)
            run_start = None
            events += 1
    if run_start is not None:
        durations.append(timestamps[-1] - run_start)
        events += 1

    rate_per_min = events / (span_seconds / 60.0)
    measurements = {
        "blink_count": events,
        "window_seconds": round(span_seconds, 2),
        "estimated_rate_per_min": round(rate_per_min, 2),
    }
    if durations:
        measurements["mean_blink_duration_s"] = round(float(np.mean(durations)), 3)

    notes: list[str] = []
    score = 0.5

    if events == 0 and span_seconds >= _ZERO_BLINK_MIN_SECONDS:
        score = 0.58
        notes.append(
            f"No blink was detected across {span_seconds:.1f}s of tracked video. Absent "
            "blinking was a documented weakness of early GAN-based face synthesis, but "
            "modern generators reproduce it, and people genuinely blink less while "
            "concentrating on camera -- this is a weak, dated signal at best."
        )
    elif events > 0:
        notes.append(
            f"{events} blink(s) detected, estimated rate {rate_per_min:.1f}/min over "
            f"{span_seconds:.1f}s. This is not itself evidence of authenticity: "
            "blink synthesis is well solved by modern methods."
        )

    return score, measurements, notes


def _head_pose_jitter(
    frames: list[SampledFrame], landmarks: list[LandmarkFrame | None]
) -> tuple[float | None, dict[str, float]]:
    velocities: list[float] = []

    for i in range(1, len(frames)):
        prev_lm, curr_lm = landmarks[i - 1], landmarks[i]
        if prev_lm is None or curr_lm is None:
            continue
        dt = frames[i].timestamp - frames[i - 1].timestamp
        if dt <= 0:
            continue
        delta = np.array(curr_lm.pose_euler_deg) - np.array(prev_lm.pose_euler_deg)
        angular_distance = float(np.linalg.norm(delta))
        velocities.append(angular_distance / dt)

    if len(velocities) < 5:
        return None, {}

    p95 = float(np.percentile(velocities, 95))
    score = float(np.clip(0.5 + (p95 - _POSE_JITTER_THRESHOLD_DEG_PER_SEC) / 400.0, 0.0, 1.0))
    return score, {"pose_velocity_p95_deg_per_s": round(p95, 2)}


@dataclass(frozen=True)
class PulsePeak:
    freq_hz: float
    bpm: float
    coherence: float


def find_pulse_peak(pulse: np.ndarray, fps: float) -> PulsePeak | None:
    """Bandpass, then locate the strongest frequency in the pulse band.

    Factored out from ``_rppg`` so the frequency-domain logic can be tested
    directly against a known synthetic signal, independent of the CHROM
    channel combination that precedes it -- CHROM is specifically designed to
    cancel any signal that varies with a fixed ratio across R/G/B, so a naive
    synthetic pulse injected that way into pixel colours is the wrong shape of
    test signal for validating this half of the pipeline.
    """
    if pulse.size < 2 or fps <= 0:
        return None

    nyquist = fps / 2.0
    if nyquist <= _PULSE_BAND_HZ[0]:
        return None

    low = _PULSE_BAND_HZ[0] / nyquist
    high = min(_PULSE_BAND_HZ[1], nyquist * 0.99) / nyquist
    b_coef, a_coef = scipy_signal.butter(3, [low, high], btype="band")
    filtered = scipy_signal.filtfilt(b_coef, a_coef, pulse)

    freqs, power = scipy_signal.periodogram(filtered, fs=fps)
    band_mask = (freqs >= _PULSE_BAND_HZ[0]) & (freqs <= _PULSE_BAND_HZ[1])
    if not band_mask.any() or power[band_mask].sum() <= 0:
        return None

    band_power = power[band_mask]
    band_freqs = freqs[band_mask]
    peak_idx = int(np.argmax(band_power))
    peak_freq = float(band_freqs[peak_idx])
    coherence = float(band_power[peak_idx] / band_power.sum())

    return PulsePeak(freq_hz=peak_freq, bpm=peak_freq * 60.0, coherence=coherence)


def _rppg(
    frames: list[SampledFrame], landmarks: list[LandmarkFrame | None]
) -> tuple[float | None, dict[str, float], list[str]]:
    settings = get_settings()
    if len(frames) < settings.video_min_dense_frames_for_rppg:
        return None, {}, ["Sampled window too short to resolve a pulse signal."]

    def _region_mean(image_bgr: np.ndarray, region: FaceRegion) -> np.ndarray | None:
        if not region.valid:
            return None
        patch = image_bgr[region.y0 : region.y1, region.x0 : region.x1]
        if patch.size == 0:
            return None
        return patch.reshape(-1, 3).mean(axis=0)  # BGR

    samples: list[np.ndarray] = []
    used_timestamps: list[float] = []
    for frame, lm in zip(frames, landmarks, strict=True):
        if lm is None:
            continue
        means = [
            m
            for m in (
                _region_mean(frame.image_bgr, lm.forehead),
                _region_mean(frame.image_bgr, lm.left_cheek),
                _region_mean(frame.image_bgr, lm.right_cheek),
            )
            if m is not None
        ]
        if not means:
            continue
        samples.append(np.mean(means, axis=0))
        used_timestamps.append(frame.timestamp)

    fraction_tracked = len(samples) / len(frames)
    if len(samples) < settings.video_min_dense_frames_for_rppg or fraction_tracked < 0.7:
        return None, {"fraction_tracked": round(fraction_tracked, 2)}, [
            "Face tracking was too intermittent across the sampled window to build a "
            "usable pulse signal."
        ]

    bgr = np.array(samples)  # (n, 3) in B, G, R order
    b, g, r = bgr[:, 0], bgr[:, 1], bgr[:, 2]

    # CHROM (de Haan & Jeanne, 2013): a linear combination of colour channels
    # designed to cancel motion-driven luminance changes while preserving the
    # subtle pulse-driven chrominance signal.
    xc = 3 * r - 2 * g
    yc = 1.5 * r + g - 1.5 * b
    xc = xc - xc.mean()
    yc = yc - yc.mean()
    alpha = float(np.std(xc) / np.std(yc)) if np.std(yc) > 1e-9 else 1.0
    pulse = xc - alpha * yc

    duration = used_timestamps[-1] - used_timestamps[0]
    if duration <= 0:
        return None, {}, ["Could not establish a usable sample rate for the pulse signal."]
    effective_fps = len(pulse) / duration

    peak = find_pulse_peak(pulse, effective_fps)
    if peak is None:
        return None, {"effective_fps": round(effective_fps, 2)}, [
            "Could not resolve a candidate pulse frequency for this window."
        ]

    coherence = peak.coherence
    bpm = peak.bpm

    measurements = {
        "estimated_bpm": round(bpm, 1),
        "coherence": round(coherence, 3),
        "effective_fps": round(effective_fps, 2),
        "fraction_tracked": round(fraction_tracked, 2),
    }

    notes: list[str] = []
    plausible = _PLAUSIBLE_BPM[0] <= bpm <= _PLAUSIBLE_BPM[1]

    if coherence >= _MIN_COHERENCE_FOR_SIGNAL and plausible:
        # A clean, physiologically plausible pulse is mildly reassuring: it is
        # uncommon for this to appear by chance. Weak evidence toward "real",
        # so the score is nudged below neutral rather than left at it.
        score = 0.5 - min(0.15, (coherence - _MIN_COHERENCE_FOR_SIGNAL) * 0.5)
        notes.append(
            f"A coherent pulse-like signal was found at ~{bpm:.0f} BPM (coherence "
            f"{coherence:.2f}). This is mildly consistent with a genuine subject, but "
            "compression and lighting frequently destroy this signal even in real "
            "video, so its absence below carries little weight either way."
        )
    else:
        # No usable pulse is the common case, including on real video, so this
        # stays neutral rather than counting against the subject.
        score = 0.5
        notes.append(
            f"No coherent pulse signal was found (best candidate ~{bpm:.0f} BPM, "
            f"coherence {coherence:.2f}, below the {_MIN_COHERENCE_FOR_SIGNAL:.2f} "
            "threshold used here). This is common even in genuine footage and is not "
            "treated as evidence of manipulation."
        )

    return score, measurements, notes


def render_signal_plot(pulse: np.ndarray, fps: float, output_path) -> None:
    """A simple line-chart PNG of the filtered rPPG trace, cv2-drawn for
    consistency with the frequency spectrum plot rather than adding a plotting
    dependency."""
    width, height, pad = 600, 200, 30
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    if pulse.size < 2:
        cv2.imwrite(str(output_path), canvas)
        return

    normalised = (pulse - pulse.min()) / max(pulse.max() - pulse.min(), 1e-9)
    xs = np.linspace(pad, width - pad, len(normalised)).astype(int)
    ys = (height - pad - normalised * (height - 2 * pad)).astype(int)
    points = np.stack([xs, ys], axis=1)
    cv2.polylines(canvas, [points], False, (180, 90, 30), 2, cv2.LINE_AA)
    cv2.putText(
        canvas, "rPPG trace (filtered)", (pad, 18),
        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA,
    )
    cv2.imwrite(str(output_path), canvas)


def analyze_temporal(dense_frames: list[SampledFrame]) -> TemporalResult:
    """Run Stream C over a dense, evenly-spaced frame window."""
    if len(dense_frames) < 5:
        return TemporalResult(
            score=0.5,
            measurable=False,
            notes=["Too few frames were available to run temporal analysis."],
        )

    landmarks = [detect(f.image_bgr) for f in dense_frames]
    tracked = sum(1 for lm in landmarks if lm is not None)

    if tracked < max(5, len(dense_frames) // 3):
        return TemporalResult(
            score=0.5,
            measurable=False,
            measurements={
                "frames_tracked": tracked,
                "frames_sampled": len(dense_frames),
            },
            notes=[
                f"A face was tracked in only {tracked} of {len(dense_frames)} sampled "
                "frames, too intermittent for temporal analysis."
            ],
        )

    measurements: dict[str, float] = {
        "frames_tracked": tracked,
        "frames_sampled": len(dense_frames),
    }
    notes: list[str] = []
    sub_scores: list[float] = []

    flow_score, flow_meas = _optical_flow_discontinuity(dense_frames, landmarks)
    measurements.update(flow_meas)
    if flow_score is not None:
        sub_scores.append(flow_score)
        notes.append(
            f"Optical flow at the face boundary vs. interior: ratio "
            f"{flow_meas.get('boundary_interior_flow_ratio', float('nan')):.2f}. An "
            "unsupervised heuristic, not a trained detector -- fast head turns and "
            "motion blur produce the same pattern as a blending seam would."
        )

    blink_score, blink_meas, blink_notes = _blink_analysis(dense_frames, landmarks)
    measurements.update(blink_meas)
    notes.extend(blink_notes)
    if blink_score is not None:
        sub_scores.append(blink_score)

    pose_score, pose_meas = _head_pose_jitter(dense_frames, landmarks)
    measurements.update(pose_meas)
    if pose_score is not None:
        sub_scores.append(pose_score)
        notes.append(
            f"Head-pose frame-to-frame jitter, 95th percentile "
            f"{pose_meas.get('pose_velocity_p95_deg_per_s', float('nan')):.0f} deg/s. "
            "A heuristic threshold, not derived from a validated distribution of "
            "natural head motion."
        )

    rppg_score, rppg_meas, rppg_notes = _rppg(dense_frames, landmarks)
    measurements.update(rppg_meas)
    notes.extend(rppg_notes)
    if rppg_score is not None:
        sub_scores.append(rppg_score)

    notes.append(
        "Lip-sync / audio-visual desync is not evaluated: the standard pretrained "
        "models for it (Wav2Lip, SyncNet) either carry a non-commercial licence or "
        "have no stated licence on their weights. See LICENSES.md."
    )
    notes.append(
        "None of these four signals has been measured against a labelled video "
        "dataset, so this stream's score does not move the reported result -- it is "
        "shown as supporting evidence only, the same treatment frequency analysis had "
        "before it was calibrated in Phase 3."
    )

    if not sub_scores:
        return TemporalResult(
            score=0.5,
            measurable=False,
            measurements=measurements,
            notes=notes + ["None of the sub-signals could be computed for this clip."],
        )

    combined = float(np.clip(np.mean(sub_scores), 0.0, 1.0))
    return TemporalResult(
        score=round(combined, 4),
        measurable=True,
        measurements={
            k: (round(v, 4) if isinstance(v, float) else v) for k, v in measurements.items()
        },
        notes=notes,
    )
