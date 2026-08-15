"""Image analysis orchestrator: bytes in, AnalysisReport out."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np

from app.bands import report_footer_disclaimer, score_to_band
from app.config import get_settings
from app.models.registry import get_spatial_model
from app.pipeline import conclusion as conclusion_mod
from app.pipeline import envelope as envelope_mod
from app.pipeline import face_map, fusion, gradcam, spatial
from app.pipeline.aggregate import aggregate
from app.pipeline.faces import crop_face, detect_faces
from app.pipeline.frequency import analyze_frequency
from app.pipeline.phash import phash
from app.pipeline.provenance import analyze_provenance
from app.schemas import (
    AnalysisReport,
    C2paInfo,
    Envelope,
    EnvelopeFactors,
    EnvelopePenalty,
    FaceBox,
    FaceFinding,
    FaceMapArtifact,
    HeatmapArtifact,
    MediaMeta,
    NoteArtifact,
    Provenance,
    SpectrumPlotArtifact,
    StreamResult,
)


def _stream_weight(name: str, fallback: float) -> float:
    """Weight for a stream, from fitted calibration when available."""
    return fusion.stream_weights().get(name, fallback)

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


def _apply_confidence(raw_score: float, confidence: float) -> float:
    """Shrink toward 0.5 in proportion to how much we distrust the reading."""
    return 0.5 + (raw_score - 0.5) * confidence


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

    model_versions: dict[str, str] = {"face_detector": "YuNet (OpenCV zoo, MIT)"}
    streams: list[StreamResult] = []
    findings: list[FaceFinding] = []

    # --- Stream B: frequency forensics. Runs on the whole frame, so unlike the
    # spatial stream it produces a result even when no face is present. ---
    frequency = analyze_frequency(image_bgr, raw)
    frequency_artifacts: list = []
    if frequency.spectrum_plot:
        frequency_artifacts.append(
            SpectrumPlotArtifact(
                label="Radially averaged FFT power spectrum",
                url=f"{settings.artifact_base_url}/{frequency.spectrum_plot.name}",
            )
        )
    for note in frequency.notes:
        frequency_artifacts.append(NoteArtifact(label="Frequency analysis", detail=note))
    frequency_artifacts.append(
        NoteArtifact(
            label="Measurements",
            detail=", ".join(f"{k} {v}" for k, v in frequency.measurements.items()),
        )
    )

    streams.append(
        StreamResult(
            name="frequency",
            score=frequency.score,
            weight=round(_stream_weight("frequency", 0.0), 4),
            models=["signal statistics (no trained model)"],
            artifacts=frequency_artifacts,
        )
    )

    # --- Stream D: provenance. Highest precision when it fires, silent otherwise. ---
    prov = analyze_provenance(raw, mime_type)
    streams.append(
        StreamResult(
            name="provenance",
            # Provenance is not a probability; it acts through the override path
            # in fusion, so it reports a neutral score rather than a fabricated one.
            score=0.5,
            weight=0.0,
            models=["C2PA manifest reader, EXIF/XMP inspection"],
            artifacts=[
                NoteArtifact(label="Provenance", detail=note) for note in prov.notes
            ],
        )
    )

    if not faces:
        assessment.penalties.append(
            (
                "No face was detected, so the spatial classifier could not run. This score "
                "reflects absence of evidence, not evidence of absence.",
                0.5,
            )
        )
        assessment.in_distribution = False

        confidence = assessment.confidence

        # The frequency stream ran, but it must not move the score here. Its
        # thresholds were derived from face imagery and it has no validated
        # standalone performance on anything else, so letting it pull the result
        # down to "likely benign" would claim we checked when we could not.
        # Provenance is different: it reads recorded facts, needs no face, and is
        # high-precision, so its override still applies.
        fused = fusion.fuse(
            [fusion.StreamInput("frequency", _NO_EVIDENCE_SCORE)],
            generator_marker=prov.generator_marker,
            c2pa_valid=bool(prov.c2pa.present and prov.c2pa.valid),
            c2pa_signer=prov.c2pa.signer,
        )
        fusion_notes = [
            "No face was found, so the spatial classifier could not run. The frequency "
            "measurements are reported below but do not move this score: they are "
            "calibrated on face imagery and have no validated standalone accuracy.",
            *fused.notes,
        ]

        score = round(min(1.0, max(0.0, fused.score)), 4)
        lo, hi = _uncertainty_band(score, 0.0, confidence)
        conclusion = conclusion_mod.build_no_face_conclusion()
    else:
        spatial_model = get_spatial_model()
        model_versions["spatial"] = spatial_model.version_string

        crops_bgr = [crop_face(image_bgr, face) for face in faces]
        crops_rgb = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in crops_bgr]
        boxes = [(f.x, f.y, f.w, f.h) for f in faces]

        face_scores = spatial.score_faces(crops_rgb, boxes, spatial_model)
        jpeg_quality = envelope_mod.estimate_jpeg_quality(raw)

        # Each face gets its own envelope, heatmap, and band. A back-row face
        # scoring high is not the same finding as a front-row face scoring high,
        # and the report should not flatten that difference.
        for index, (face, crop_bgr, crop_rgb, result) in enumerate(
            zip(faces, crops_bgr, crops_rgb, face_scores, strict=True), start=1
        ):
            face_penalties = envelope_mod.assess_face(crop_bgr, face, jpeg_quality)
            face_confidence = 1.0
            for _, factor in face_penalties:
                face_confidence *= factor

            face_score = round(_apply_confidence(result.score, face_confidence), 4)
            face_lo, face_hi = _uncertainty_band(face_score, result.spread, face_confidence)

            heatmap_path = gradcam.generate_heatmap(crop_rgb, spatial_model)

            findings.append(
                FaceFinding(
                    index=index,
                    box=FaceBox(x=face.x, y=face.y, w=face.w, h=face.h),
                    score=face_score,
                    band=score_to_band(face_score).id,  # type: ignore[arg-type]
                    uncertainty=(face_lo, face_hi),
                    detector_confidence=round(min(1.0, max(0.0, face.confidence)), 4),
                    penalties=[
                        EnvelopePenalty(reason=reason, factor=factor)
                        for reason, factor in face_penalties
                    ],
                    heatmap_url=f"{settings.artifact_base_url}/{heatmap_path.name}",
                )
            )

        aggregation = aggregate(
            [f.score for f in findings], [r.spread for r in face_scores]
        )
        assessment.penalties.extend(aggregation.penalties)
        if aggregation.penalties:
            assessment.in_distribution = False

        confidence = assessment.confidence

        # Fuse the spatial aggregate with the frequency stream using weights
        # fitted from validation AUC, then let provenance override if it fired.
        fused = fusion.fuse(
            [
                fusion.StreamInput("spatial", aggregation.score),
                fusion.StreamInput("frequency", frequency.score),
            ],
            generator_marker=prov.generator_marker,
            c2pa_valid=bool(prov.c2pa.present and prov.c2pa.valid),
            c2pa_signer=prov.c2pa.signer,
        )
        fusion_notes = list(fused.notes)

        score = round(min(1.0, max(0.0, _apply_confidence(fused.score, confidence))), 4)
        # Cross-stream disagreement is the real uncertainty source the
        # architecture called for; TTA spread is kept as a floor.
        spread = max(fused.disagreement, aggregation.spread)
        lo, hi = _uncertainty_band(score, spread, confidence)

        conclusion = conclusion_mod.build_conclusion(aggregation, score)

        map_path = face_map.generate_face_map(
            image_bgr, faces, [f.band for f in findings]
        )

        artifacts: list = [
            FaceMapArtifact(
                label=(
                    f"{len(findings)} {'face' if len(findings) == 1 else 'faces'} analysed, "
                    "numbered to match the per-face results"
                ),
                url=f"{settings.artifact_base_url}/{map_path.name}",
            )
        ]

        top = max(findings, key=lambda f: f.score)
        if top.heatmap_url:
            artifacts.append(
                HeatmapArtifact(
                    label=f"Grad-CAM for face {top.index}, the highest-scoring face",
                    url=top.heatmap_url,
                )
            )

        artifacts.append(
            NoteArtifact(
                label="Uncertainty source",
                detail=(
                    f"Disagreement across streams was {fused.disagreement:.4f}; spread "
                    f"across {len(face_scores[0].variant_scores)} test-time "
                    "augmentations was "
                    f"{aggregation.spread:.4f}. The wider of the two sets the reported "
                    "range. Only one spatial backbone is loaded, so this is still not "
                    "the full error decorrelation an ensemble of different "
                    "architectures would give."
                ),
            )
        )

        streams.append(
            StreamResult(
                name="spatial",
                score=round(aggregation.score, 4),
                weight=round(_stream_weight("spatial", 1.0), 4),
                models=[spatial_model.version_string],
                artifacts=artifacts,
            )
        )

    # Fusion notes explain how the streams were combined and whether provenance
    # overrode them, which belongs with the evidence rather than buried.
    for note in fusion_notes:
        for stream in streams:
            if stream.name == "frequency":
                stream.artifacts.append(NoteArtifact(label="Fusion", detail=note))
                break

    now = datetime.now(UTC)

    return AnalysisReport(
        job_id=job_id,
        score=score,
        band=score_to_band(score).id,  # type: ignore[arg-type]
        uncertainty=(lo, hi),
        streams=streams,
        faces=findings,
        conclusion=conclusion,  # type: ignore[arg-type]
        envelope=Envelope(
            in_distribution=assessment.in_distribution,
            penalties=[
                EnvelopePenalty(reason=reason, factor=factor)
                for reason, factor in assessment.penalties
            ],
            factors_checked=EnvelopeFactors(**assessment.factors),
        ),
        provenance=Provenance(
            c2pa=C2paInfo(
                present=prov.c2pa.present,
                valid=prov.c2pa.valid,
                signer=prov.c2pa.signer,
                trusted_signer=prov.c2pa.trusted_signer,
            )
            if prov.c2pa.present
            else None,
            exif_consistent=prov.exif_consistent,
            known_generator_watermark=prov.generator_marker,
            phash=phash(image_bgr),
        ),
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
