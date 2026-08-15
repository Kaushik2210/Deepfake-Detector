"""Envelope checks and the confidence penalty."""

from __future__ import annotations

import cv2
import numpy as np

from app.pipeline import envelope
from app.pipeline.faces import DetectedFace


def test_jpeg_quality_estimate_tracks_actual_quality(jpeg_at_quality) -> None:
    """The estimate should be monotonic and land near the requested quality."""
    estimates = {q: envelope.estimate_jpeg_quality(jpeg_at_quality(q)) for q in (30, 60, 90)}

    for quality, estimate in estimates.items():
        assert estimate is not None, f"no estimate for q{quality}"
        assert abs(estimate - quality) <= 10, f"q{quality} estimated as {estimate}"

    assert estimates[30] < estimates[60] < estimates[90]


def test_jpeg_quality_estimate_returns_none_for_png(no_face_png: bytes) -> None:
    assert envelope.estimate_jpeg_quality(no_face_png) is None


def test_blur_score_drops_when_image_is_blurred(real_face_bgr: np.ndarray) -> None:
    blurred = cv2.GaussianBlur(real_face_bgr, (21, 21), 0)
    assert envelope.blur_score(blurred) < envelope.blur_score(real_face_bgr)


def test_uncalibrated_penalty_is_always_present(real_face_bgr: np.ndarray) -> None:
    """Principle 5: we never present an uncalibrated score as if it were calibrated."""
    assessment = envelope.assess(real_face_bgr, [DetectedFace(0, 0, 200, 200, 0.9)])
    assert any("uncalibrated" in reason.lower() for reason, _ in assessment.penalties)


def test_clean_input_stays_in_distribution(real_face_bgr: np.ndarray) -> None:
    assessment = envelope.assess(real_face_bgr, [DetectedFace(0, 0, 200, 200, 0.9)])
    assert assessment.in_distribution
    assert assessment.confidence < 1.0  # the calibration penalty still applies


def test_small_face_triggers_a_penalty(real_face_bgr: np.ndarray) -> None:
    tiny = DetectedFace(x=0, y=0, w=20, h=20, confidence=0.9)
    assessment = envelope.assess(real_face_bgr, [tiny])

    assert not assessment.in_distribution
    assert any("below the" in reason for reason, _ in assessment.penalties)


def test_blurred_input_triggers_a_penalty(real_face_bgr: np.ndarray) -> None:
    blurred = cv2.GaussianBlur(real_face_bgr, (31, 31), 0)
    assessment = envelope.assess(blurred, [DetectedFace(0, 0, 200, 200, 0.9)])

    assert not assessment.in_distribution
    assert any("blurred" in reason.lower() for reason, _ in assessment.penalties)


def test_dark_input_triggers_an_exposure_penalty(real_face_bgr: np.ndarray) -> None:
    dark = (real_face_bgr * 0.1).astype(np.uint8)
    assessment = envelope.assess(dark, [DetectedFace(0, 0, 200, 200, 0.9)])

    assert any("exposure" in reason.lower() for reason, _ in assessment.penalties)


def test_penalties_compound_multiplicatively(real_face_bgr: np.ndarray) -> None:
    dark_blurred = cv2.GaussianBlur((real_face_bgr * 0.1).astype(np.uint8), (31, 31), 0)
    assessment = envelope.assess(dark_blurred, [DetectedFace(0, 0, 20, 20, 0.9)])

    assert len(assessment.penalties) >= 3
    assert assessment.confidence < 0.5


def test_every_penalty_carries_a_human_readable_reason(no_face_bgr: np.ndarray) -> None:
    """Principle 3: a silent penalty defeats the purpose."""
    assessment = envelope.assess(no_face_bgr, [])
    for reason, factor in assessment.penalties:
        assert len(reason) > 20, f"reason too terse to surface in UI: {reason!r}"
        assert 0.0 < factor <= 1.0
