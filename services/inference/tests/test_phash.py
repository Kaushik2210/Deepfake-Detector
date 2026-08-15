"""Perceptual hashing."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.pipeline.phash import hamming_distance, phash


def test_hash_is_16_hex_chars(real_face_bgr: np.ndarray) -> None:
    value = phash(real_face_bgr)
    assert len(value) == 16
    int(value, 16)  # parses as hex


def test_hash_is_deterministic(real_face_bgr: np.ndarray) -> None:
    assert phash(real_face_bgr) == phash(real_face_bgr)


def test_hash_survives_recompression(real_face_bgr: np.ndarray, jpeg_at_quality) -> None:
    """The cache key must survive the recompression media picks up in transit."""
    original = phash(real_face_bgr)
    recompressed = cv2.imdecode(np.frombuffer(jpeg_at_quality(40), np.uint8), cv2.IMREAD_COLOR)

    assert hamming_distance(original, phash(recompressed)) <= 4


def test_hash_survives_moderate_rescaling(real_face_bgr: np.ndarray) -> None:
    height, width = real_face_bgr.shape[:2]
    smaller = cv2.resize(real_face_bgr, (width // 2, height // 2), interpolation=cv2.INTER_AREA)

    assert hamming_distance(phash(real_face_bgr), phash(smaller)) <= 6


def test_different_images_hash_differently(
    real_face_bgr: np.ndarray, no_face_bgr: np.ndarray
) -> None:
    assert hamming_distance(phash(real_face_bgr), phash(no_face_bgr)) > 10


def test_hamming_distance_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        hamming_distance("abcd", "abcdef")
