"""Video analysis orchestrator: bytes in, AnalysisReport out.

Reuses the same face-detection, spatial classifier, frequency stream,
provenance stream, aggregation, and fusion machinery ``analyze.py`` uses for
images -- applied per sampled frame instead of once. See ``video_io.py`` for
why two different frame-sampling densities are used, and ``temporal.py`` for
why Stream C's score does not move the fused result yet.
"""

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
from app.pipeline.faces import DetectedFace, crop_face, detect_faces
from app.pipeline.frequency import analyze_frequency
from app.pipeline.phash import phash
from app.pipeline.provenance import analyze_provenance
from app.pipeline.temporal import analyze_temporal
from app.pipeline.video_io import (
    close_video,
    open_video,
    sample_dense_window,
    sample_sparse_frames,
)
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
    StreamResult,
    TimelineArtifact,
    TimelinePoint,
)

_NO_EVIDENCE_SCORE = 0.5


class VideoTooLongError(ValueError):
    """Raised when a video exceeds the configured duration limit."""


def _apply_confidence(raw_score: float, confidence: float) -> float:
    return 0.5 + (raw_score - 0.5) * confidence


def _uncertainty_band(score: float, spread: float, confidence: float) -> tuple[float, float]:
    half_width = spread * 2.0 + (1.0 - confidence) * 0.5
    return (
        round(max(0.0, score - half_width), 4),
        round(min(1.0, score + half_width), 4),
    )


def _largest_face(faces: list[DetectedFace]) -> DetectedFace | None:
    """This phase tracks one primary subject per frame, not every face in a
    multi-person clip -- documented as a limitation in the video README."""
    return max(faces, key=lambda f: f.area) if faces else None


def analyze_video(
    raw: bytes,
    filename: str | None = None,
    mime_type: str = "video/mp4",
    job_id: str | None = None,
) -> AnalysisReport:
    settings = get_settings()
    job_id = job_id or uuid.uuid4().hex

    cap, info, tmp_path = open_video(raw)
    try:
        if info.duration_seconds > settings.max_video_duration_seconds:
            raise VideoTooLongError(
                f"video is {info.duration_seconds:.1f}s, longer than the "
                f"{settings.max_video_duration_seconds:.0f}s limit"
            )

        sparse_frames = sample_sparse_frames(cap, info, settings.video_sparse_frame_cap)
        dense_frames = sample_dense_window(
            cap,
            info,
            settings.video_dense_window_max_seconds,
            settings.video_dense_window_target_fps,
            settings.video_dense_window_max_frames,
        )
    finally:
        close_video(cap, tmp_path)

    model_versions: dict[str, str] = {
        "face_detector": "YuNet (OpenCV zoo, MIT)",
        "landmarker": "MediaPipe FaceLandmarker (Google, Apache-2.0)",
    }
    streams: list[StreamResult] = []
    findings: list[FaceFinding] = []
    timeline_points: list[TimelinePoint] = []

    frames_with_face = 0
    spatial_model = None

    frequency_frame_scores: list[float] = []
    frequency_notes_sample: list[str] = []
    spectrum_artifact_frame = None

    for sf in sparse_frames:
        image_bgr = sf.image_bgr
        faces = detect_faces(image_bgr)
        primary = _largest_face(faces)

        freq_result = analyze_frequency(
            image_bgr, render_plot=(spectrum_artifact_frame is None)
        )
        frequency_frame_scores.append(freq_result.score)
        if spectrum_artifact_frame is None and freq_result.spectrum_plot:
            spectrum_artifact_frame = freq_result.spectrum_plot
        if not frequency_notes_sample:
            frequency_notes_sample = freq_result.notes

        if primary is None:
            continue

        frames_with_face += 1
        if spatial_model is None:
            spatial_model = get_spatial_model()
            model_versions["spatial"] = spatial_model.version_string

        crop_bgr = crop_face(image_bgr, primary)
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        raw_score, spread, variant_scores = spatial.score_crop(crop_rgb, spatial_model)

        face_penalties = envelope_mod.assess_face(crop_bgr, primary, jpeg_quality=None)
        face_confidence = 1.0
        for _, factor in face_penalties:
            face_confidence *= factor

        face_score = round(_apply_confidence(raw_score, face_confidence), 4)
        face_lo, face_hi = _uncertainty_band(face_score, spread, face_confidence)

        timeline_points.append(TimelinePoint(t=round(sf.timestamp, 3), score=face_score))

        findings.append(
            FaceFinding(
                index=sf.index,
                box=FaceBox(x=primary.x, y=primary.y, w=primary.w, h=primary.h),
                score=face_score,
                band=score_to_band(face_score).id,  # type: ignore[arg-type]
                uncertainty=(face_lo, face_hi),
                detector_confidence=round(min(1.0, max(0.0, primary.confidence)), 4),
                penalties=[
                    EnvelopePenalty(reason=reason, factor=factor)
                    for reason, factor in face_penalties
                ],
                heatmap_url=None,
                timestamp=round(sf.timestamp, 3),
            )
        )

    # Heatmaps are generated for only the top-K highest-scoring frames: at up to
    # 24 sampled frames, a heatmap per frame (each an extra backward pass) risks
    # the runtime budget this cap exists to protect. Every frame's score is still
    # reported via the timeline regardless.
    if findings:
        top_indices = {
            f.index
            for f in sorted(findings, key=lambda x: x.score, reverse=True)[
                : settings.video_sparse_heatmap_top_k
            ]
        }
        sparse_by_index = {sf.index: sf for sf in sparse_frames}
        for finding in findings:
            if finding.index not in top_indices:
                continue
            sf = sparse_by_index[finding.index]
            faces_here = detect_faces(sf.image_bgr)
            primary = _largest_face(faces_here)
            if primary is None or spatial_model is None:
                continue
            crop_rgb = cv2.cvtColor(crop_face(sf.image_bgr, primary), cv2.COLOR_BGR2RGB)
            heatmap_path = gradcam.generate_heatmap(crop_rgb, spatial_model)
            finding.heatmap_url = f"{settings.artifact_base_url}/{heatmap_path.name}"

    frequency_score = float(np.mean(frequency_frame_scores)) if frequency_frame_scores else 0.5
    frequency_artifacts: list = []
    if spectrum_artifact_frame:
        frequency_artifacts.append(
            NoteArtifact(
                label="Frequency analysis",
                detail=(
                    f"Averaged over {len(frequency_frame_scores)} sampled frames; "
                    "spectrum plot shown is from one representative frame."
                ),
            )
        )
    for note in frequency_notes_sample:
        frequency_artifacts.append(NoteArtifact(label="Frequency analysis", detail=note))

    streams.append(
        StreamResult(
            name="frequency",
            score=round(frequency_score, 4),
            weight=round(fusion.stream_weights().get("frequency", 0.0), 4),
            models=["signal statistics (no trained model)"],
            artifacts=frequency_artifacts,
        )
    )

    prov = analyze_provenance(raw, mime_type)
    streams.append(
        StreamResult(
            name="provenance",
            score=0.5,
            weight=0.0,
            models=["C2PA manifest reader, EXIF/XMP inspection"],
            artifacts=[NoteArtifact(label="Provenance", detail=note) for note in prov.notes],
        )
    )

    temporal_result = analyze_temporal(dense_frames)
    temporal_artifacts: list = [
        NoteArtifact(
            label="Temporal analysis",
            detail=(
                f"Measured over a {len(dense_frames)}-frame dense window "
                f"({dense_frames[-1].timestamp - dense_frames[0].timestamp:.1f}s span)."
                if dense_frames
                else "No dense window could be sampled from this clip."
            ),
        )
    ]
    for note in temporal_result.notes:
        temporal_artifacts.append(NoteArtifact(label="Temporal analysis", detail=note))
    streams.append(
        StreamResult(
            name="temporal",
            score=temporal_result.score,
            weight=round(fusion.stream_weights().get("temporal", 0.0), 4),
            models=["MediaPipe FaceLandmarker + unsupervised signal heuristics"],
            artifacts=temporal_artifacts,
        )
    )

    # Per-frame size/blur/illumination penalties are already captured on each
    # FaceFinding via assess_face(). This top-level pass only needs the
    # permanent "scores are uncalibrated" penalty and a resolution reading, so
    # it is called with an empty face list rather than picking one frame's face
    # to stand in for the whole clip.
    representative = sparse_frames[0].image_bgr if sparse_frames else np.zeros((1, 1, 3), np.uint8)
    envelope_assessment = envelope_mod.assess(representative, [], raw_bytes=None)
    envelope_assessment.factors["resolution"] = f"{info.width}x{info.height}"
    if sparse_frames:
        envelope_assessment.factors["blur"] += " (measured on the first sampled frame)"
        envelope_assessment.factors["illumination"] += " (measured on the first sampled frame)"

    if not findings:
        envelope_assessment.penalties.append(
            (
                "No face was detected in any sampled frame, so the spatial classifier "
                "could not run. This reflects absence of evidence, not evidence of absence.",
                0.5,
            )
        )
        envelope_assessment.in_distribution = False

        confidence = envelope_assessment.confidence
        fused = fusion.fuse(
            [fusion.StreamInput("frequency", _NO_EVIDENCE_SCORE)],
            generator_marker=prov.generator_marker,
            c2pa_valid=bool(prov.c2pa.present and prov.c2pa.valid),
            c2pa_signer=prov.c2pa.signer,
        )
        fusion_notes = [
            "No face was found in any sampled frame. Frequency and temporal "
            "measurements are reported below but do not move this score.",
            *fused.notes,
        ]
        score = round(min(1.0, max(0.0, fused.score)), 4)
        lo, hi = _uncertainty_band(score, 0.0, confidence)
        conclusion = conclusion_mod.build_no_face_conclusion()
    else:
        aggregation = aggregate([f.score for f in findings], [0.0] * len(findings))
        envelope_assessment.penalties.extend(aggregation.penalties)
        if aggregation.penalties:
            envelope_assessment.in_distribution = False

        confidence = envelope_assessment.confidence
        fused = fusion.fuse(
            [
                fusion.StreamInput("spatial", aggregation.score),
                fusion.StreamInput("frequency", frequency_score),
            ],
            generator_marker=prov.generator_marker,
            c2pa_valid=bool(prov.c2pa.present and prov.c2pa.valid),
            c2pa_signer=prov.c2pa.signer,
        )
        fusion_notes = list(fused.notes)

        score = round(min(1.0, max(0.0, _apply_confidence(fused.score, confidence))), 4)
        spread = max(fused.disagreement, 0.0)
        lo, hi = _uncertainty_band(score, spread, confidence)

        conclusion = conclusion_mod.build_conclusion(aggregation, score)

        top = max(findings, key=lambda f: f.score)
        spatial_artifacts: list = [
            TimelineArtifact(
                label=f"Score across {len(sparse_frames)} sampled frames",
                points=timeline_points,
            )
        ]

        finding_by_index = {f.index: f for f in findings}
        sparse_by_index_for_map = {sf.index: sf for sf in sparse_frames}

        map_frame = max(
            (sf for sf in sparse_frames if sf.index in finding_by_index),
            key=lambda sf: finding_by_index[sf.index].score,
            default=None,
        )
        if map_frame is not None:
            faces_here = detect_faces(map_frame.image_bgr)
            if faces_here:
                map_band = score_to_band(finding_by_index[map_frame.index].score).id
                map_path = face_map.generate_face_map(
                    map_frame.image_bgr, faces_here, [map_band]
                )
                spatial_artifacts.insert(
                    0,
                    FaceMapArtifact(
                        label=f"Highest-scoring sampled frame, at t={map_frame.timestamp:.1f}s",
                        url=f"{settings.artifact_base_url}/{map_path.name}",
                    ),
                )
        if top.heatmap_url:
            top_frame = sparse_by_index_for_map[top.index]
            spatial_artifacts.append(
                HeatmapArtifact(
                    label=(
                        "Grad-CAM for the highest-scoring sampled frame "
                        f"(t={top_frame.timestamp:.1f}s)"
                    ),
                    url=top.heatmap_url,
                )
            )
        spatial_artifacts.append(
            NoteArtifact(
                label="Sampling",
                detail=(
                    f"{len(sparse_frames)} of {info.frame_count} frames analysed "
                    f"(uniform time buckets with a scene-change-biased pick within "
                    f"each). {frames_with_face} of those had a detectable face. Only "
                    f"the top {min(settings.video_sparse_heatmap_top_k, len(findings))} "
                    "highest-scoring frames carry a heatmap, to keep runtime bounded."
                ),
            )
        )
        spatial_artifacts.append(
            NoteArtifact(
                label="Multi-person clips",
                detail=(
                    "Only the largest detected face per frame is tracked. A clip with "
                    "several people is not analysed per-person across time; each "
                    "sampled frame's primary subject may differ from the last."
                ),
            )
        )

        streams.insert(
            0,
            StreamResult(
                name="spatial",
                score=round(aggregation.score, 4),
                weight=round(fusion.stream_weights().get("spatial", 1.0), 4),
                models=[spatial_model.version_string] if spatial_model else [],
                artifacts=spatial_artifacts,
            ),
        )

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
            in_distribution=envelope_assessment.in_distribution,
            penalties=[
                EnvelopePenalty(reason=reason, factor=factor)
                for reason, factor in envelope_assessment.penalties
            ],
            factors_checked=EnvelopeFactors(**envelope_assessment.factors),
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
            phash=phash(sparse_frames[0].image_bgr) if sparse_frames else None,
        ),
        media_meta=MediaMeta(
            kind="video",
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(raw),
            duration_seconds=round(info.duration_seconds, 2),
            width=info.width,
            height=info.height,
        ),
        model_versions=model_versions,
        processed_at=now.isoformat(),
        ttl_expires_at=(now + timedelta(hours=settings.media_ttl_hours)).isoformat(),
        disclaimer=report_footer_disclaimer(),
    )
