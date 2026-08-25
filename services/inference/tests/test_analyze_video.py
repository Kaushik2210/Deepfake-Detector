"""End-to-end video analysis. Model-marked: needs the classifier and landmarker."""

from __future__ import annotations

import pytest

from app.bands import score_to_band
from app.pipeline.analyze_video import VideoTooLongError, analyze_video
from app.pipeline.video_io import VideoDecodeError

pytestmark = pytest.mark.model


def test_rejects_undecodable_bytes() -> None:
    with pytest.raises(VideoDecodeError):
        analyze_video(b"not a video")


def test_rejects_a_clip_over_the_duration_limit(real_face_video_bytes: bytes, monkeypatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VERIFRAME_MAX_VIDEO_DURATION_SECONDS", "1")
    try:
        with pytest.raises(VideoTooLongError):
            analyze_video(real_face_video_bytes, mime_type="video/mp4")
    finally:
        get_settings.cache_clear()


def test_full_report_shape(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, filename="clip.mp4", mime_type="video/mp4")

    assert report.media_meta.kind == "video"
    assert report.media_meta.duration_seconds == pytest.approx(4.0, abs=0.2)
    assert report.band == score_to_band(report.score).id
    lo, hi = report.uncertainty
    assert 0.0 <= lo <= report.score <= hi <= 1.0
    assert report.disclaimer


def test_produces_one_finding_per_frame_with_a_detected_face(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    assert len(report.faces) > 0
    for finding in report.faces:
        assert finding.timestamp is not None
        assert finding.band == score_to_band(finding.score).id


def test_finding_indices_are_sequential_from_one(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    indices = [f.index for f in report.faces]
    assert indices == sorted(indices)
    assert indices[0] == 1


def test_only_top_k_frames_carry_a_heatmap(real_face_video_bytes: bytes) -> None:
    from app.config import get_settings

    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    with_heatmap = [f for f in report.faces if f.heatmap_url]
    assert len(with_heatmap) <= get_settings().video_sparse_heatmap_top_k
    assert len(with_heatmap) > 0


def test_reports_all_four_streams(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    names = {s.name for s in report.streams}
    assert names == {"spatial", "frequency", "provenance", "temporal"}


def test_spatial_stream_has_a_timeline_and_face_map(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    spatial = next(s for s in report.streams if s.name == "spatial")
    artifact_types = {a.type for a in spatial.artifacts}
    assert "timeline" in artifact_types
    assert "face_map" in artifact_types
    assert "heatmap" in artifact_types

    timeline = next(a for a in spatial.artifacts if a.type == "timeline")
    assert len(timeline.points) == len(report.faces)


def test_temporal_stream_never_moves_the_fused_score(real_face_video_bytes: bytes) -> None:
    """Stream C has no eval-derived weight yet, so it must not affect the
    result -- only spatial/frequency/provenance may."""
    from app.pipeline import fusion

    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    assert fusion.stream_weights().get("temporal", 0.0) == 0.0
    temporal = next(s for s in report.streams if s.name == "temporal")
    assert temporal.weight == 0.0


def test_no_face_anywhere_reports_inconclusive(no_face_video_bytes: bytes) -> None:
    report = analyze_video(no_face_video_bytes, mime_type="video/mp4")
    assert report.score == 0.5
    assert report.band == "mixed"
    assert report.faces == []
    assert not any(s.name == "spatial" for s in report.streams)
    assert any("No face was detected" in p.reason for p in report.envelope.penalties)


def test_no_face_video_still_reports_frequency_and_temporal_as_context(
    no_face_video_bytes: bytes,
) -> None:
    report = analyze_video(no_face_video_bytes, mime_type="video/mp4")
    names = {s.name for s in report.streams}
    assert "frequency" in names
    assert "temporal" in names


def test_conclusion_is_present_and_video_appropriate(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    assert report.conclusion is not None
    assert report.conclusion.faces_analyzed == len(report.faces)


def test_model_versions_include_landmarker(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    assert "landmarker" in report.model_versions
    assert "spatial" in report.model_versions


def test_perceptual_hash_is_present(real_face_video_bytes: bytes) -> None:
    report = analyze_video(real_face_video_bytes, mime_type="video/mp4")
    assert report.provenance.phash is not None
