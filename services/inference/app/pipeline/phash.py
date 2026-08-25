"""Perceptual hash (pHash).

Used as the cache key for repeat lookups so the cache stores a hash rather than
the media itself (privacy principle 4). Implemented on OpenCV's DCT instead of
pulling in an image-hashing dependency for ~20 lines of work.
"""

from __future__ import annotations

import cv2
import numpy as np

_HASH_SIZE = 8
_DCT_SIZE = 32


def hash_from_grid(gray: np.ndarray) -> str:
    """The DCT-and-threshold math, given an already `_DCT_SIZE`x`_DCT_SIZE`
    grayscale grid.

    Split out from `phash()` so this half -- the part that must match the TS
    port in packages/core/src/phash.ts exactly -- can be exercised directly
    with a known array, independent of the resize step. See
    `packages/core/src/__tests__/phash.test.ts` for the cross-language check.
    """
    dct = cv2.dct(np.float32(gray))
    low_freq = dct[:_HASH_SIZE, :_HASH_SIZE]

    # Exclude the DC term from the median: it carries overall brightness, not structure.
    coefficients = low_freq.flatten()
    median = np.median(coefficients[1:])

    bits = coefficients > median
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)

    return f"{value:016x}"


def phash(image_bgr: np.ndarray) -> str:
    """64-bit perceptual hash, returned as 16 lowercase hex characters."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (_DCT_SIZE, _DCT_SIZE), interpolation=cv2.INTER_AREA)
    return hash_from_grid(resized)


def hamming_distance(a: str, b: str) -> int:
    """Bit distance between two pHashes; smaller means more perceptually similar."""
    if len(a) != len(b):
        raise ValueError(f"hash length mismatch: {len(a)} vs {len(b)}")
    return bin(int(a, 16) ^ int(b, 16)).count("1")
