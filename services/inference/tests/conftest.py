"""Shared fixtures.

Fixture images are either generated in-process or taken from matplotlib's bundled
sample data, so the offline test suite needs no network and no committed binaries.
``grace_hopper.jpg`` is a US Navy photograph in the public domain.
"""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
import soundfile as sf


@pytest.fixture(scope="session")
def real_face_jpeg() -> bytes:
    """A real photograph containing one clearly visible face."""
    matplotlib_cbook = pytest.importorskip("matplotlib.cbook")
    sample = matplotlib_cbook.get_sample_data("grace_hopper.jpg")
    return Path(sample.name).read_bytes()


@pytest.fixture(scope="session")
def real_face_bgr(real_face_jpeg: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(real_face_jpeg, np.uint8), cv2.IMREAD_COLOR)


@pytest.fixture(scope="session")
def no_face_png() -> bytes:
    """A smooth gradient — decodable, but containing no face."""
    gradient = np.tile(np.linspace(0, 255, 320, dtype=np.uint8), (240, 1))
    image = cv2.cvtColor(gradient, cv2.COLOR_GRAY2BGR)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture(scope="session")
def no_face_bgr(no_face_png: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(no_face_png, np.uint8), cv2.IMREAD_COLOR)


def _write_clip(frames: list[np.ndarray], fps: float) -> bytes:
    import tempfile

    height, width = frames[0].shape[:2]
    path = tempfile.mktemp(suffix=".mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return Path(path).read_bytes()


@pytest.fixture(scope="session")
def real_face_video_bytes(real_face_bgr: np.ndarray) -> bytes:
    """A short synthetic clip: the real portrait, gently jittered frame to
    frame, so face/landmark tracking succeeds throughout without needing a
    genuine video file."""
    height, width = real_face_bgr.shape[:2]
    fps = 25.0
    n = int(4 * fps)  # 4 seconds

    frames = []
    for i in range(n):
        angle = 1.5 * np.sin(i / 20.0)
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        warped = cv2.warpAffine(
            real_face_bgr, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE
        )
        frames.append(warped)

    return _write_clip(frames, fps)


@pytest.fixture(scope="session")
def no_face_video_bytes(no_face_bgr: np.ndarray) -> bytes:
    """A clip that never contains a face."""
    fps = 25.0
    n = int(2 * fps)
    frames = [no_face_bgr for _ in range(n)]
    return _write_clip(frames, fps)


def _write_wav(waveform: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.fixture
def sine_wave_wav():
    """A pure tone -- decodable, voiced (not silent), not clipped."""

    def _make(duration_seconds: float = 3.0, sample_rate: int = 22050, freq: float = 220.0):
        t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
        waveform = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        return _write_wav(waveform, sample_rate)

    return _make


@pytest.fixture
def silent_wav():
    def _make(duration_seconds: float = 3.0, sample_rate: int = 16000) -> bytes:
        waveform = np.zeros(int(sample_rate * duration_seconds), dtype=np.float32)
        return _write_wav(waveform, sample_rate)

    return _make


@pytest.fixture
def clipped_wav():
    """A square wave: every sample sits at full scale."""

    def _make(duration_seconds: float = 2.0, sample_rate: int = 16000) -> bytes:
        n = int(sample_rate * duration_seconds)
        waveform = np.full(n, 0.999, dtype=np.float32)
        waveform[::2] = -0.999
        return _write_wav(waveform, sample_rate)

    return _make


@pytest.fixture
def jpeg_at_quality(real_face_bgr: np.ndarray):
    """Re-encode the sample photo at a chosen JPEG quality."""

    def _encode(quality: int) -> bytes:
        ok, buffer = cv2.imencode(
            ".jpg", real_face_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        )
        assert ok
        return buffer.tobytes()

    return _encode
