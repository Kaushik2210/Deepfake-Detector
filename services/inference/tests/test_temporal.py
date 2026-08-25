"""Stream C sub-signals, tested with synthetic landmark data.

Each sub-function takes a parallel (frames, landmarks) pair, so these are
tested directly with hand-built ``LandmarkFrame`` objects rather than needing
MediaPipe's real model -- fast, deterministic, and offline.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.landmarks import FaceRegion, LandmarkFrame
from app.pipeline.temporal import (
    _blink_analysis,
    _head_pose_jitter,
    _optical_flow_discontinuity,
    _rppg,
    analyze_temporal,
    find_pulse_peak,
)
from app.pipeline.video_io import SampledFrame

_VALID_REGION = FaceRegion(x0=5, y0=5, x1=15, y1=15)
_FRAME_SIZE = 64


def _points_for_bbox(cx: float, cy: float, half: float = 15.0) -> np.ndarray:
    """A cheap stand-in for 478 real landmarks: a ring around a bounding box,
    including the eye/mouth index positions the module reads for ROI geometry."""
    pts = np.tile([cx, cy], (478, 1)).astype(np.float64)
    ring = np.array(
        [
            [cx - half, cy - half],
            [cx + half, cy - half],
            [cx - half, cy + half],
            [cx + half, cy + half],
        ]
    )
    pts[:4] = ring
    # Eye/mouth index constants used by landmarks.py's ROI placement.
    for idx in (33, 160, 158, 133, 153, 144):
        pts[idx] = [cx - half * 0.4, cy - half * 0.3]
    for idx in (362, 385, 387, 263, 373, 380):
        pts[idx] = [cx + half * 0.4, cy - half * 0.3]
    for idx in (61, 291, 13, 14):
        pts[idx] = [cx, cy + half * 0.5]
    return pts


def _frame(index: int, timestamp: float, value: int = 128) -> SampledFrame:
    image = np.full((_FRAME_SIZE, _FRAME_SIZE, 3), value, dtype=np.uint8)
    return SampledFrame(index=index, frame_number=index, timestamp=timestamp, image_bgr=image)


def _landmark(
    blink_left: float = 0.0,
    blink_right: float = 0.0,
    pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
    cx: float = 32.0,
    cy: float = 32.0,
) -> LandmarkFrame:
    return LandmarkFrame(
        points_px=_points_for_bbox(cx, cy),
        blink_left=blink_left,
        blink_right=blink_right,
        pose_euler_deg=pose,
        forehead=_VALID_REGION,
        left_cheek=_VALID_REGION,
        right_cheek=_VALID_REGION,
    )


class TestBlinkAnalysis:
    def test_reports_not_measurable_below_minimum_frame_count(self) -> None:
        frames = [_frame(i, i / 30.0) for i in range(5)]
        landmarks = [_landmark() for _ in frames]
        score, meas, notes = _blink_analysis(frames, landmarks)
        assert score is None
        assert notes

    def test_counts_a_single_blink_event(self) -> None:
        fps = 30.0
        n = 130  # span (n-1)/fps must clear the 4s minimum, not just n/fps
        frames = [_frame(i, i / fps) for i in range(n)]
        # Closed (blink) for frames 40-45, open elsewhere.
        landmarks = [
            _landmark(blink_left=0.9 if 40 <= i <= 45 else 0.05, blink_right=0.0)
            for i in range(n)
        ]
        score, meas, notes = _blink_analysis(frames, landmarks)
        assert score is not None
        assert meas["blink_count"] == 1
        assert meas["mean_blink_duration_s"] == pytest.approx(6 / fps, abs=0.05)

    def test_zero_blinks_over_a_long_window_is_flagged_as_weak_signal(self) -> None:
        n = 150
        frames = [_frame(i, i / 30.0) for i in range(n)]
        landmarks = [_landmark(blink_left=0.02, blink_right=0.02) for _ in range(n)]
        score, meas, notes = _blink_analysis(frames, landmarks)
        assert meas["blink_count"] == 0
        assert score is not None and score > 0.5
        assert any("dated" in note or "weak" in note for note in notes)

    def test_multiple_blinks_are_each_counted_separately(self) -> None:
        n = 150
        frames = [_frame(i, i / 30.0) for i in range(n)]
        closed_ranges = [(10, 13), (60, 64), (110, 112)]
        landmarks = [
            _landmark(blink_left=0.9 if any(lo <= i <= hi for lo, hi in closed_ranges) else 0.0)
            for i in range(n)
        ]
        _, meas, _ = _blink_analysis(frames, landmarks)
        assert meas["blink_count"] == 3


class TestHeadPoseJitter:
    def test_not_measurable_with_too_few_valid_pairs(self) -> None:
        frames = [_frame(i, i / 30.0) for i in range(3)]
        landmarks = [_landmark(pose=(0, 0, 0)), None, _landmark(pose=(0, 0, 0))]
        score, meas = _head_pose_jitter(frames, landmarks)
        assert score is None

    def test_stable_pose_scores_low(self) -> None:
        n = 30
        frames = [_frame(i, i / 30.0) for i in range(n)]
        landmarks = [_landmark(pose=(0.0, 0.0, 0.0)) for _ in range(n)]
        score, meas = _head_pose_jitter(frames, landmarks)
        assert score is not None
        assert meas["pose_velocity_p95_deg_per_s"] == pytest.approx(0.0, abs=1e-6)
        assert score < 0.5

    def test_erratic_pose_scores_higher_than_stable_pose(self) -> None:
        n = 30
        frames = [_frame(i, i / 30.0) for i in range(n)]
        stable = [_landmark(pose=(0.0, 0.0, 0.0)) for _ in range(n)]
        erratic = [
            _landmark(pose=(0.0, 180.0 * ((-1) ** i), 0.0)) for i in range(n)
        ]
        stable_score, _ = _head_pose_jitter(frames, stable)
        erratic_score, _ = _head_pose_jitter(frames, erratic)
        assert erratic_score > stable_score

    def test_ignores_frames_where_landmarks_were_not_found(self) -> None:
        # Jitter needs *consecutive* valid pairs, so a few isolated gaps (not
        # alternating every frame, which would leave zero consecutive pairs).
        n = 30
        gaps = {5, 15, 25}
        frames = [_frame(i, i / 30.0) for i in range(n)]
        landmarks = [None if i in gaps else _landmark(pose=(0.0, 0.0, 0.0)) for i in range(n)]
        score, meas = _head_pose_jitter(frames, landmarks)
        assert score is not None


class TestOpticalFlowDiscontinuity:
    def test_returns_none_when_no_consecutive_pair_has_landmarks(self) -> None:
        frames = [_frame(i, i / 30.0) for i in range(5)]
        landmarks = [None] * 5
        score, meas = _optical_flow_discontinuity(frames, landmarks)
        assert score is None

    def test_uniform_translation_produces_a_ratio_near_one(self) -> None:
        """Byte-identical frames give exactly zero interior flow, which the
        function correctly refuses to divide by (covered by the 'no motion at
        all' test below). Pure i.i.d. noise is also unsuitable here: Farneback
        has no well-defined motion to estimate from independent random pixels,
        which makes that comparison unstable regardless of what the function
        does. A coherent whole-crop translation is the well-defined case for
        'no boundary-specific artifact': everything moves by the same amount,
        interior and boundary alike, so their flow magnitudes should agree."""
        rng = np.random.default_rng(1)
        texture = rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)
        n = 10
        frames = []
        for i in range(n):
            shifted = np.roll(texture, shift=i, axis=1)[:64, :64]
            frames.append(
                SampledFrame(index=i, frame_number=i, timestamp=i / 30.0, image_bgr=shifted)
            )
        landmarks = [_landmark() for _ in range(n)]
        score, meas = _optical_flow_discontinuity(frames, landmarks)
        assert score is not None
        assert meas["boundary_interior_flow_ratio"] == pytest.approx(1.0, abs=0.5)

    def test_zero_motion_is_not_measurable_rather_than_divided_by_zero(self) -> None:
        n = 10
        frames = [_frame(i, i / 30.0, value=100) for i in range(n)]
        landmarks = [_landmark() for _ in range(n)]
        score, meas = _optical_flow_discontinuity(frames, landmarks)
        assert score is None

    def test_score_is_bounded(self) -> None:
        n = 8
        rng = np.random.default_rng(0)
        frames = []
        for i in range(n):
            image = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
            frames.append(
                SampledFrame(index=i, frame_number=i, timestamp=i / 30.0, image_bgr=image)
            )
        landmarks = [_landmark() for _ in range(n)]
        score, _ = _optical_flow_discontinuity(frames, landmarks)
        assert score is None or 0.0 <= score <= 1.0


class TestFindPulsePeak:
    """Tests the bandpass/periodogram peak-finding directly on a 1D signal,
    bypassing CHROM's channel combination -- CHROM is specifically designed to
    cancel any signal that varies with a fixed ratio across R/G/B, so a naive
    sinusoid injected proportionally into pixel colours is mathematically the
    wrong shape of test signal for validating this half of the pipeline (see
    DECISIONS.md). This is the part that actually does the frequency-domain
    work, so it is tested here where it can be driven directly."""

    def test_recovers_a_known_frequency(self) -> None:
        fps = 30.0
        duration = 10.0
        n = int(fps * duration)
        target_hz = 1.5  # 90 BPM

        t = np.arange(n) / fps
        pulse = 5.0 * np.sin(2 * np.pi * target_hz * t)

        peak = find_pulse_peak(pulse, fps)

        assert peak is not None
        assert peak.freq_hz == pytest.approx(target_hz, abs=0.15)
        assert peak.bpm == pytest.approx(target_hz * 60, abs=9.0)
        assert peak.coherence > 0.5

    @pytest.mark.parametrize("target_hz", [0.9, 1.5, 2.4, 3.2])
    def test_recovers_several_frequencies_across_the_pulse_band(self, target_hz: float) -> None:
        fps = 30.0
        n = int(fps * 10.0)
        t = np.arange(n) / fps
        pulse = np.sin(2 * np.pi * target_hz * t)

        peak = find_pulse_peak(pulse, fps)

        assert peak is not None
        assert peak.freq_hz == pytest.approx(target_hz, abs=0.15)

    def test_white_noise_has_low_coherence(self) -> None:
        rng = np.random.default_rng(3)
        fps = 30.0
        pulse = rng.normal(size=int(fps * 10.0))

        peak = find_pulse_peak(pulse, fps)

        assert peak is not None
        assert peak.coherence < 0.5

    def test_returns_none_below_nyquist_for_the_pulse_band(self) -> None:
        # 1 Hz sample rate -> 0.5 Hz Nyquist, below the 0.7 Hz band floor.
        pulse = np.sin(2 * np.pi * 0.3 * np.arange(20))
        assert find_pulse_peak(pulse, fps=1.0) is None

    def test_returns_none_for_a_degenerate_signal(self) -> None:
        assert find_pulse_peak(np.zeros(300), fps=30.0) is None
        assert find_pulse_peak(np.array([]), fps=30.0) is None
        assert find_pulse_peak(np.array([1.0]), fps=30.0) is None


class TestRppg:
    def test_not_measurable_below_minimum_window(self) -> None:
        frames = [_frame(i, i / 25.0) for i in range(10)]
        landmarks = [_landmark() for _ in frames]
        score, meas, notes = _rppg(frames, landmarks)
        assert score is None
        assert notes

    def test_non_periodic_noise_is_reported_as_no_coherent_pulse(self) -> None:
        """Noise with no periodicity should score neutral, not be read as
        evidence either way -- distinct from the degenerate all-zero-variance
        case below, which cannot even locate a candidate peak."""
        rng = np.random.default_rng(2)
        n = 200
        frames = []
        for i in range(n):
            noise = rng.integers(-3, 4, (64, 64, 3))
            image = np.clip(128 + noise, 0, 255).astype(np.uint8)
            frames.append(
                SampledFrame(index=i, frame_number=i, timestamp=i / 25.0, image_bgr=image)
            )
        landmarks = [_landmark() for _ in range(n)]
        score, meas, notes = _rppg(frames, landmarks)
        assert score == 0.5
        assert any("No coherent pulse" in note for note in notes)

    def test_perfectly_flat_signal_is_not_measurable(self) -> None:
        """Zero variance means no candidate peak exists at all, which is a
        different -- and more honest -- outcome than 'found one, not coherent'."""
        n = 200
        frames = [_frame(i, i / 25.0, value=128) for i in range(n)]
        landmarks = [_landmark() for _ in range(n)]
        score, meas, notes = _rppg(frames, landmarks)
        assert score is None

    def test_intermittent_tracking_is_reported_as_not_measurable(self) -> None:
        n = 150
        frames = [_frame(i, i / 25.0) for i in range(n)]
        # Face lost more than 30% of the time.
        landmarks = [_landmark() if i % 2 == 0 else None for i in range(n)]
        score, meas, notes = _rppg(frames, landmarks)
        assert score is None


class TestAnalyzeTemporalIntegration:
    def test_too_few_frames_is_not_measurable(self) -> None:
        result = analyze_temporal([_frame(i, i / 30.0) for i in range(3)])
        assert result.measurable is False
        assert result.score == 0.5

    def test_score_never_leaves_the_signals_that_could_not_be_computed_silent(self) -> None:
        """Every reachable code path must explain itself, even the boring ones."""
        result = analyze_temporal([_frame(i, i / 30.0) for i in range(3)])
        assert len(result.notes) > 0

    def test_result_score_is_always_in_bounds(self) -> None:
        for n in (0, 3, 10, 50):
            result = analyze_temporal([_frame(i, i / 30.0) for i in range(n)])
            assert 0.0 <= result.score <= 1.0
