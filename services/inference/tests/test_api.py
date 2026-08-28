"""HTTP surface."""

from __future__ import annotations

import uuid

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


def test_health_reports_landmarker() -> None:
    body = client.get("/v1/health").json()
    assert "landmarker" in body["model_versions"]


def test_health_reports_audio() -> None:
    body = client.get("/v1/health").json()
    assert "audio" in body["model_versions"]


@pytest.mark.redis
def test_analyze_hash_returns_429_past_the_rate_limit(monkeypatch) -> None:
    from app.config import get_settings
    from app.pipeline import rate_limit

    monkeypatch.setattr(get_settings(), "rate_limit_hash_per_minute", 2)
    # Only this test's own keys -- a flushdb() would nuke whatever else shares
    # this Redis instance in a dev environment (e.g. the web app's BullMQ).
    for key in rate_limit._client().scan_iter("ratelimit:analyze_hash:*"):
        rate_limit._client().delete(key)

    # A random hash, not a degenerate one like "0"*16 -- a smooth/gradient
    # test image's real computed phash can land suspiciously close to
    # all-zero (low DCT-coefficient variance), which has caused a real
    # false-positive near-match against accumulated dev-DB test data before.
    body = {"phash": uuid.uuid4().hex[:16]}
    responses = [client.post("/v1/analyze/hash", json=body) for _ in range(3)]

    assert [r.status_code for r in responses[:2]] == [404, 404]
    assert responses[2].status_code == 429
    assert "Retry-After" in responses[2].headers


@pytest.mark.model
def test_full_report_shape_for_audio(sine_wave_wav) -> None:
    raw = sine_wave_wav(duration_seconds=3.0)
    response = client.post("/v1/analyze", files={"file": ("clip.wav", raw, "audio/wav")})
    assert response.status_code == 200

    body = response.json()
    assert body["media_meta"]["kind"] == "audio"
    assert {s["name"] for s in body["streams"]} == {"audio", "audio_frequency"}


def test_cors_allows_a_chrome_extension_origin() -> None:
    response = client.options(
        "/v1/analyze/hash",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef"
    )


def test_cors_rejects_an_arbitrary_web_origin() -> None:
    response = client.options(
        "/v1/analyze/hash",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.db
def test_analyze_by_hash_returns_404_for_an_unknown_hash() -> None:
    response = client.post("/v1/analyze/hash", json={"phash": "beef0000000000be"})
    assert response.status_code == 404


def test_analyze_by_hash_rejects_a_malformed_hash() -> None:
    """Regression guard.

    A wrong-length hash reaching the cache scan raised ValueError from
    hamming_distance() and surfaced as a 500. The caller here is untrusted --
    the extension's own client-side hash implementation -- so this must be a
    clean 422, not a crash.
    """
    for bad in ("too-short", "0" * 15, "0" * 17, "UPPERCASE0000000", "not-hex-chars!!!"):
        response = client.post("/v1/analyze/hash", json={"phash": bad})
        assert response.status_code == 422, f"{bad!r} should have been rejected"


@pytest.mark.db
def test_analyze_then_lookup_by_reported_phash(no_face_png: bytes) -> None:
    posted = client.post(
        "/v1/analyze", files={"file": ("noface.png", no_face_png, "image/png")}
    )
    report = posted.json()
    phash = report["provenance"]["phash"]
    assert phash

    looked_up = client.post("/v1/analyze/hash", json={"phash": phash})
    assert looked_up.status_code == 200
    assert looked_up.json()["job_id"] == report["job_id"]


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
