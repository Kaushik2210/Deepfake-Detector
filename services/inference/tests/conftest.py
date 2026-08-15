"""Shared fixtures.

Fixture images are either generated in-process or taken from matplotlib's bundled
sample data, so the offline test suite needs no network and no committed binaries.
``grace_hopper.jpg`` is a US Navy photograph in the public domain.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest


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
