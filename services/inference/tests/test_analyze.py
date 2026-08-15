"""End-to-end analysis behaviour.

Tests that need the real classifier weights are marked ``model`` and deselected in
CI with ``-m "not model"``; the rest run offline.
"""

from __future__ import annotations

import pytest

from app.bands import score_to_band
from app.pipeline.analyze import DecodeError, analyze_image


def test_rejects_undecodable_bytes() -> None:
    with pytest.raises(DecodeError):
        analyze_image(b"this is not an image")


def test_no_face_reports_inconclusive_not_clean(no_face_png: bytes) -> None:
    """Absence of evidence must not be reported as evidence of absence."""
    report = analyze_image(no_face_png, filename="noface.png", mime_type="image/png")

    assert report.score == 0.5
    assert report.band == "mixed"
    assert report.streams == []
    assert not report.envelope.in_distribution
    assert any("No face was detected" in p.reason for p in report.envelope.penalties)


def test_no_face_uncertainty_is_wide(no_face_png: bytes) -> None:
    report = analyze_image(no_face_png, mime_type="image/png")
    lo, hi = report.uncertainty
    assert hi - lo > 0.5, "an uninformative result must not report a narrow interval"


def test_report_always_carries_the_disclaimer(no_face_png: bytes) -> None:
    """Principle 6."""
    report = analyze_image(no_face_png, mime_type="image/png")
    assert "not proof" in report.disclaimer
    assert "forensic evidence" in report.disclaimer


def test_report_records_media_meta_and_phash(no_face_png: bytes) -> None:
    report = analyze_image(no_face_png, filename="noface.png", mime_type="image/png")

    assert report.media_meta.kind == "image"
    assert report.media_meta.filename == "noface.png"
    assert report.media_meta.size_bytes == len(no_face_png)
    assert (report.media_meta.width, report.media_meta.height) == (320, 240)
    assert report.provenance.phash is not None


def test_ttl_is_in_the_future(no_face_png: bytes) -> None:
    report = analyze_image(no_face_png, mime_type="image/png")
    assert report.ttl_expires_at > report.processed_at


def test_band_always_agrees_with_score(no_face_png: bytes) -> None:
    report = analyze_image(no_face_png, mime_type="image/png")
    assert report.band == score_to_band(report.score).id


@pytest.mark.model
def test_real_face_produces_an_evidence_backed_spatial_stream(real_face_jpeg: bytes) -> None:
    """Principle 2: a score without a visual explanation is a failure."""
    report = analyze_image(real_face_jpeg, filename="face.jpg", mime_type="image/jpeg")

    assert len(report.streams) == 1
    stream = report.streams[0]
    assert stream.name == "spatial"
    assert stream.models

    heatmaps = [a for a in stream.artifacts if a.type == "heatmap"]
    assert heatmaps, "spatial stream reported a score with no heatmap"
    assert heatmaps[0].url.endswith(".png")


@pytest.mark.model
def test_uncertainty_brackets_the_score(real_face_jpeg: bytes) -> None:
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")
    lo, hi = report.uncertainty

    assert 0.0 <= lo <= report.score <= hi <= 1.0


@pytest.mark.model
def test_heavier_compression_widens_uncertainty(jpeg_at_quality) -> None:
    """An out-of-envelope input must report less confidence, not the same confidence."""
    clean = analyze_image(jpeg_at_quality(95), mime_type="image/jpeg")
    degraded = analyze_image(jpeg_at_quality(20), mime_type="image/jpeg")

    clean_width = clean.uncertainty[1] - clean.uncertainty[0]
    degraded_width = degraded.uncertainty[1] - degraded.uncertainty[0]

    assert degraded_width > clean_width
    assert not degraded.envelope.in_distribution


@pytest.mark.model
def test_every_face_gets_its_own_band_interval_and_heatmap(real_face_jpeg: bytes) -> None:
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")

    assert len(report.faces) >= 1
    for face in report.faces:
        assert face.band == score_to_band(face.score).id
        lo, hi = face.uncertainty
        assert 0.0 <= lo <= face.score <= hi <= 1.0
        assert face.heatmap_url, f"face {face.index} reported a score with no heatmap"
        assert face.box.w > 0 and face.box.h > 0


@pytest.mark.model
def test_face_indices_are_sequential_from_one(real_face_jpeg: bytes) -> None:
    """Indices must match the numbers drawn on the face map."""
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")
    assert [f.index for f in report.faces] == list(range(1, len(report.faces) + 1))


@pytest.mark.model
def test_report_carries_a_face_map_when_faces_are_found(real_face_jpeg: bytes) -> None:
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")
    artifacts = [a for s in report.streams for a in s.artifacts]
    assert any(a.type == "face_map" for a in artifacts)


@pytest.mark.model
def test_conclusion_counts_match_the_faces_reported(real_face_jpeg: bytes) -> None:
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")

    assert report.conclusion is not None
    assert report.conclusion.faces_analyzed == len(report.faces)


def test_no_face_still_produces_a_conclusion(no_face_png: bytes) -> None:
    report = analyze_image(no_face_png, mime_type="image/png")

    assert report.faces == []
    assert report.conclusion is not None
    assert report.conclusion.faces_analyzed == 0
    assert "could not find" in report.conclusion.detail.lower()


@pytest.mark.model
def test_model_version_is_pinned_to_a_commit(real_face_jpeg: bytes) -> None:
    """Reported numbers must trace to an exact checkpoint."""
    report = analyze_image(real_face_jpeg, mime_type="image/jpeg")
    assert "spatial" in report.model_versions
    assert "@" in report.model_versions["spatial"]
