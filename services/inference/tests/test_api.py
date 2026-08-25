"""HTTP surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_model_versions() -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] in {"ok", "degraded", "down"}
    assert "face_detector" in body["model_versions"]
    assert isinstance(body["models_loaded"], bool)


def test_rejects_unsupported_content_type() -> None:
    response = client.post(
        "/v1/analyze", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415


def test_rejects_empty_upload() -> None:
    response = client.post("/v1/analyze", files={"file": ("empty.png", b"", "image/png")})
    assert response.status_code == 400


def test_rejects_undecodable_image() -> None:
    response = client.post(
        "/v1/analyze", files={"file": ("broken.png", b"not a png", "image/png")}
    )
    assert response.status_code == 400


def test_unknown_job_id_returns_404() -> None:
    assert client.get("/v1/analyze/does-not-exist").status_code == 404


def test_unknown_artifact_returns_404() -> None:
    assert client.get("/artifacts/nope.png").status_code == 404


def test_artifact_route_rejects_path_traversal() -> None:
    response = client.get("/artifacts/..%2F..%2Fpyproject.toml")
    assert response.status_code == 404


def test_analyze_then_fetch_roundtrip(no_face_png: bytes) -> None:
    """The job id returned by POST must be retrievable through GET."""
    posted = client.post(
        "/v1/analyze", files={"file": ("noface.png", no_face_png, "image/png")}
    )
    assert posted.status_code == 200

    report = posted.json()
    fetched = client.get(f"/v1/analyze/{report['job_id']}")

    assert fetched.status_code == 200
    assert fetched.json() == report


def test_response_never_contains_a_binary_verdict(no_face_png: bytes) -> None:
    """Principle 1, enforced at the wire format."""
    response = client.post(
        "/v1/analyze", files={"file": ("noface.png", no_face_png, "image/png")}
    )
    body = response.json()

    assert body["band"] in {"low", "weak", "mixed", "strong", "very_strong"}
    assert "verdict" not in body
    assert isinstance(body["uncertainty"], list) and len(body["uncertainty"]) == 2


@pytest.mark.model
def test_full_report_shape_for_a_real_face(real_face_jpeg: bytes) -> None:
    response = client.post(
        "/v1/analyze", files={"file": ("face.jpg", real_face_jpeg, "image/jpeg")}
    )
    assert response.status_code == 200

    body = response.json()
    required = {
        "job_id", "score", "band", "uncertainty", "streams", "envelope",
        "provenance", "media_meta", "model_versions", "processed_at",
        "ttl_expires_at", "disclaimer",
    }
    assert required <= set(body)


def test_rejects_undecodable_video() -> None:
    response = client.post(
        "/v1/analyze", files={"file": ("broken.mp4", b"not a video", "video/mp4")}
    )
    assert response.status_code == 400


def test_rejects_empty_video_upload() -> None:
    response = client.post("/v1/analyze", files={"file": ("empty.mp4", b"", "video/mp4")})
    assert response.status_code == 400


def test_rejects_video_over_the_byte_limit(monkeypatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VERIFRAME_MAX_VIDEO_BYTES", "100")
    try:
        response = client.post(
            "/v1/analyze",
            files={"file": ("clip.mp4", b"x" * 200, "video/mp4")},
        )
        assert response.status_code == 413
    finally:
        get_settings.cache_clear()


@pytest.mark.model
def test_analyze_accepts_a_real_video_end_to_end(real_face_video_bytes: bytes) -> None:
    response = client.post(
        "/v1/analyze",
        files={"file": ("clip.mp4", real_face_video_bytes, "video/mp4")},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["media_meta"]["kind"] == "video"
    assert body["band"] in {"low", "weak", "mixed", "strong", "very_strong"}

    fetched = client.get(f"/v1/analyze/{body['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


@pytest.mark.model
def test_video_over_duration_limit_returns_422(real_face_video_bytes: bytes, monkeypatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VERIFRAME_MAX_VIDEO_DURATION_SECONDS", "1")
    try:
        response = client.post(
            "/v1/analyze",
            files={"file": ("clip.mp4", real_face_video_bytes, "video/mp4")},
        )
        assert response.status_code == 422
    finally:
        get_settings.cache_clear()


@pytest.mark.model
def test_heatmap_artifact_is_actually_served(real_face_jpeg: bytes) -> None:
    """A heatmap URL that 404s is the same failure as having no heatmap."""
    response = client.post(
        "/v1/analyze", files={"file": ("face.jpg", real_face_jpeg, "image/jpeg")}
    )
    body = response.json()

    heatmaps = [
        artifact
        for stream in body["streams"]
        for artifact in stream["artifacts"]
        if artifact["type"] == "heatmap"
    ]
    assert heatmaps

    filename = heatmaps[0]["url"].rsplit("/", 1)[-1]
    served = client.get(f"/artifacts/{filename}")

    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
