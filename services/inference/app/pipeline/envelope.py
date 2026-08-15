"""Out-of-distribution envelope checks and the confidence penalty.

Detectors degrade hard under distribution shift, so before a score is reported we
measure the input characteristics that are known to cause that degradation and
reduce reported confidence when they fall outside the envelope the model was
trained on. Every penalty carries a human-readable reason that the UI surfaces —
a silent penalty would defeat the point.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from app.config import get_settings
from app.pipeline.faces import DetectedFace

# Standard IJG luminance quantization table, used to invert a JPEG's tables back
# into an approximate quality setting.
_STD_LUMA_QUANT = np.array(
    [
        16, 11, 10, 16, 24, 40, 51, 61,
        12, 12, 14, 19, 26, 58, 60, 55,
        14, 13, 16, 24, 40, 57, 69, 56,
        14, 17, 22, 29, 51, 87, 80, 62,
        18, 22, 37, 56, 68, 109, 103, 77,
        24, 35, 55, 64, 81, 104, 113, 92,
        49, 64, 78, 87, 103, 121, 120, 101,
        72, 92, 95, 98, 112, 100, 103, 99,
    ],
    dtype=np.float64,
)


@dataclass
class EnvelopeAssessment:
    in_distribution: bool
    penalties: list[tuple[str, float]] = field(default_factory=list)
    factors: dict[str, str] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        """Combined multiplier in (0, 1]; 1.0 means fully inside the envelope."""
        multiplier = 1.0
        for _, factor in self.penalties:
            multiplier *= factor
        return multiplier


def estimate_jpeg_quality(raw_bytes: bytes) -> int | None:
    """Approximate a JPEG's quality setting by inverting its quantization table.

    Returns None for non-JPEG input or when the table isn't readable. This inverts
    the IJG scaling formula, so it is an estimate of the *last* encode only —
    an image recompressed several times can still report a high number.
    """
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            if img.format != "JPEG":
                return None
            tables = getattr(img, "quantization", None)
            if not tables:
                return None
            table = np.array(tables[0], dtype=np.float64)
    except Exception:
        return None

    if table.size != _STD_LUMA_QUANT.size:
        return None

    # Tq = clamp((S * Tstd + 50) / 100)  =>  S = (100 * Tq - 50) / Tstd
    with np.errstate(divide="ignore", invalid="ignore"):
        scales = (100.0 * table - 50.0) / _STD_LUMA_QUANT
    scales = scales[np.isfinite(scales) & (scales > 0)]
    if scales.size == 0:
        return None

    scale = float(np.median(scales))
    quality = 5000.0 / scale if scale > 100.0 else (200.0 - scale) / 2.0
    return int(round(min(100.0, max(1.0, quality))))


def blur_score(image_bgr: np.ndarray) -> float:
    """Variance of the Laplacian; lower means blurrier."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def mean_luma(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def assess_face(
    face_crop_bgr: np.ndarray,
    face: DetectedFace,
    jpeg_quality: int | None = None,
) -> list[tuple[str, float]]:
    """Penalties for one face, measured on that face's own crop.

    A group photo mixes a 200px front-row face with a 30px face at the back.
    Judging both by the image-level measurements would report the same
    confidence for two results that deserve very different confidence, so each
    face is measured independently.
    """
    settings = get_settings()
    penalties: list[tuple[str, float]] = []

    if face.h < settings.min_face_px:
        # Scale the penalty with how far under the threshold the face is: a 60px
        # face is a mild concern, a 20px face is barely evidence at all.
        severity = max(0.35, face.h / settings.min_face_px)
        penalties.append(
            (
                f"This face is only {face.w}x{face.h}px, below the "
                f"{settings.min_face_px}px the classifier expects. The crop is "
                "upsampled beyond training resolution, so this score is weak evidence.",
                round(severity, 3),
            )
        )

    if face_crop_bgr.size > 0:
        blur = blur_score(face_crop_bgr)
        if blur < settings.blur_threshold:
            penalties.append(
                (
                    f"This face is blurred (Laplacian variance {blur:.1f} < "
                    f"{settings.blur_threshold:.0f}), which suppresses the "
                    "high-frequency cues the detector relies on.",
                    0.7,
                )
            )

        luma = mean_luma(face_crop_bgr)
        if luma < settings.min_mean_luma or luma > settings.max_mean_luma:
            penalties.append(
                (
                    f"This face is poorly exposed (mean luma {luma:.1f}, expected "
                    f"{settings.min_mean_luma:.0f}-{settings.max_mean_luma:.0f}).",
                    0.8,
                )
            )

    if jpeg_quality is not None and jpeg_quality < settings.min_jpeg_quality:
        penalties.append(
            (
                f"The source image is heavily compressed (~JPEG quality {jpeg_quality}), "
                "which destroys the traces this detector depends on.",
                0.6,
            )
        )

    return penalties


def assess(
    image_bgr: np.ndarray,
    faces: list[DetectedFace],
    raw_bytes: bytes | None = None,
) -> EnvelopeAssessment:
    """Measure input characteristics and accumulate confidence penalties."""
    settings = get_settings()
    assessment = EnvelopeAssessment(in_distribution=True)

    height, width = image_bgr.shape[:2]
    assessment.factors["resolution"] = f"{width}x{height}"

    # --- Face size ---
    if faces:
        largest = faces[0]
        assessment.factors["face_size"] = f"{largest.w}x{largest.h}px"
        if largest.h < settings.min_face_px:
            assessment.penalties.append(
                (
                    f"Largest face is {largest.h}px tall, below the {settings.min_face_px}px "
                    "the classifier expects; the crop is upsampled beyond training resolution.",
                    0.6,
                )
            )
    else:
        assessment.factors["face_size"] = "no face detected"

    # --- Blur ---
    blur = blur_score(image_bgr)
    assessment.factors["blur"] = f"laplacian variance {blur:.1f}"
    if blur < settings.blur_threshold:
        assessment.penalties.append(
            (
                f"Image is blurred (Laplacian variance {blur:.1f} < "
                f"{settings.blur_threshold:.0f}); blur suppresses the high-frequency "
                "cues this detector relies on.",
                0.7,
            )
        )

    # --- Illumination ---
    luma = mean_luma(image_bgr)
    assessment.factors["illumination"] = f"mean luma {luma:.1f}"
    if luma < settings.min_mean_luma or luma > settings.max_mean_luma:
        assessment.penalties.append(
            (
                f"Unusual exposure (mean luma {luma:.1f}, expected "
                f"{settings.min_mean_luma:.0f}-{settings.max_mean_luma:.0f}).",
                0.8,
            )
        )

    # --- Compression ---
    quality = estimate_jpeg_quality(raw_bytes) if raw_bytes else None
    if quality is None:
        assessment.factors["compression_estimate"] = "not a JPEG or table unreadable"
    else:
        assessment.factors["compression_estimate"] = f"~JPEG quality {quality}"
        if quality < settings.min_jpeg_quality:
            assessment.penalties.append(
                (
                    f"Heavy compression (~JPEG quality {quality} < "
                    f"{settings.min_jpeg_quality}); compression destroys the spectral "
                    "traces manipulation detectors depend on.",
                    0.6,
                )
            )

    # --- Calibration status ---
    # The spec is explicit that raw softmax outputs are overconfident. Temperature
    # scaling is fitted in Phase 3; until then every score carries this penalty
    # rather than being presented as if it were calibrated.
    assessment.penalties.append(
        (
            "Scores are uncalibrated: temperature scaling is fitted in Phase 3 from the "
            "eval harness. Treat the magnitude as indicative only.",
            0.85,
        )
    )

    assessment.in_distribution = len(assessment.penalties) <= 1
    return assessment
