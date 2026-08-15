"""Image analysis orchestrator: bytes in, AnalysisReport out."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from app.bands import report_footer_disclaimer, score_to_band
from app.config import get_settings
from app.models.registry import get_spatial_model
from app.pipeline import envelope as envelope_mod
from app.pipeline import gradcam, spatial
from app.pipeline.faces import crop_face, detect_faces
from app.pipeline.phash import phash
from app.schemas import (
    AnalysisReport,
    Envelope,
    EnvelopeFactors,
    EnvelopePenalty,
    HeatmapArtifact,
    MediaMeta,
    NoteArtifact,
    Provenance,
    StreamResult,
)

# Phase 1 runs one stream, so its fusion weight is trivially 1.0. Real weights are
# derived from per-stream validation AUC in Phase 3 — not hand-picked.
_SPATIAL_WEIGHT = 1.0

# Score returned when no evidence could be gathered. 0.5 lands in "Mixed signals /
# Inconclusive — manual review advised", which is what we actually mean; returning
# a low score would imply we looked and found nothing.
_NO_EVIDENCE_SCORE = 0.5


class DecodeError(ValueError):
    """Raised when the uploaded bytes are not a decodable image."""


def decode_image(raw: bytes) -> np.ndarray:
    array = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise DecodeError("could not decode the uploaded bytes as an image")
    return image


def _uncertainty_band(score: float, spread: float, confidence: float) -> tuple[float, float]:
    """Widen a point score into an interval.

    Two contributions: how much the model's own output moved across test-time
    augmentations, and how far outside the training envelope the input sits. Both
    are heuristic — this becomes a calibrated interval in Phase 3, once the eval
    harness has fitted temperature scaling on a held-out split.
    """
    half_width = spread * 2.0 + (1.0 - confidence) * 0.5
    return (
        round(max(0.0, score - half_width), 4),
        round(min(1.0, score + half_width), 4),
    )


def analyze_image(
    raw: bytes,
    filename: str | None = None,
    mime_type: str = "application/octet-stream",
    job_id: str | None = None,
) -> AnalysisReport:
    settings = get_settings()
    job_id = job_id or uuid.uuid4().hex

    image_bgr = decode_image(raw)
    height, width = image_bgr.shape[:2]

    faces = detect_faces(image_bgr)
    assessment = envelope_mod.assess(image_bgr, faces, raw_bytes=raw)
    confidence = assessment.confidence

    model_versions: dict[str, str] = {"face_detector": "YuNet (OpenCV zoo, MIT)"}
    streams: list[StreamResult] = []

    if faces:
        spatial_model = get_spatial_model()
        model_versions["spatial"] = spatial_model.version_string

        crops_bgr = [crop_face(image_bgr, face) for face in faces]
        crops_rgb = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in crops_bgr]
        boxes = [(f.x, f.y, f.w, f.h) for f in faces]

        face_scores = spatial.score_faces(crops_rgb, boxes, spatial_model)
        raw_score, spread = spatial.aggregate_face_scores(face_scores)

        # Heatmap for the face that drove the aggregate, so the evidence shown
        # explains the number reported.
        top_index = max(range(len(face_scores)), key=lambda i: face_scores[i].score)
        heatmap_path = gradcam.generate_heatmap(crops_rgb[top_index], spatial_model)

        artifacts: list = [
            HeatmapArtifact(
                label=(
                    f"Grad-CAM over face {top_index + 1} of {len(face_scores)} "
                    f"at {boxes[top_index]}"
                ),
                url=f"{settings.artifact_base_url}/{heatmap_path.name}",
            )
        ]

        if len(face_scores) > 1:
            per_face = ", ".join(
                f"face {i + 1} at {fs.box}: {fs.score:.3f}"
                for i, fs in enumerate(face_scores)
            )
            artifacts.append(
                NoteArtifact(
                    label="Per-face scores",
                    detail=(
                        f"{len(face_scores)} faces analysed. The image-level score is the "
                        f"maximum across them. {per_face}"
                    ),
                )
            )

        artifacts.append(
            NoteArtifact(
                label="Uncertainty source",
                detail=(
                    f"Spread across {len(face_scores[top_index].variant_scores)} test-time "
                    f"augmentations was {spread:.4f}. Phase 1 runs a single backbone, so this "
                    "substitutes for ensemble disagreement and is a weaker signal — it "
                    "measures sensitivity to flip and scale, not error decorrelation across "
                    "architectures."
                ),
            )
        )

        streams.append(
            StreamResult(
                name="spatial",
                score=round(raw_score, 4),
                weight=_SPATIAL_WEIGHT,
                models=[spatial_model.version_string],
                artifacts=artifacts,
            )
        )
    else:
        raw_score, spread = _NO_EVIDENCE_SCORE, 0.0
        assessment.penalties.append(
            (
                "No face was detected, so the spatial classifier could not run. This score "
                "reflects absence of evidence, not evidence of absence.",
                0.5,
            )
        )
        assessment.in_distribution = False
        confidence = assessment.confidence

    # Shrink toward 0.5 in proportion to how much we distrust the input. A score we
    # cannot stand behind should move toward "inconclusive", not stay confident.
    if faces:
        score = 0.5 + (raw_score - 0.5) * confidence
    else:
        score = _NO_EVIDENCE_SCORE

    score = round(min(1.0, max(0.0, score)), 4)
    lo, hi = _uncertainty_band(score, spread, confidence)

    now = datetime.now(UTC)

    return AnalysisReport(
        job_id=job_id,
        score=score,
        band=score_to_band(score).id,  # type: ignore[arg-type]
        uncertainty=(lo, hi),
        streams=streams,
        envelope=Envelope(
            in_distribution=assessment.in_distribution,
            penalties=[
                EnvelopePenalty(reason=reason, factor=factor)
                for reason, factor in assessment.penalties
            ],
            factors_checked=EnvelopeFactors(**assessment.factors),
        ),
        provenance=Provenance(phash=phash(image_bgr)),
        media_meta=MediaMeta(
            kind="image",
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(raw),
            width=width,
            height=height,
        ),
        model_versions=model_versions,
        processed_at=now.isoformat(),
        ttl_expires_at=(now + timedelta(hours=settings.media_ttl_hours)).isoformat(),
        disclaimer=report_footer_disclaimer(),
    )
