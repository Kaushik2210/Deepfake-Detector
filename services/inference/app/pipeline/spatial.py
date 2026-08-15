"""Stream A — spatial classifier over detected face crops.

Phase 1 runs a single backbone, so the "ensemble disagreement" uncertainty source
the architecture calls for is not available yet. We substitute the spread across
test-time augmentations, which is a strictly weaker signal: it captures a model's
sensitivity to flips and scale but not the error decorrelation you get from
genuinely different architectures. It is labelled as such everywhere it surfaces,
and is replaced by real ensemble variance in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import torch

from app.models.registry import SpatialModel, get_spatial_model, preprocess

# Horizontal flip x two scales, per the test-time augmentation spec.
_TTA_SCALES = (1.0, 0.875)


@dataclass
class FaceScore:
    """Score for one face crop, averaged over TTA variants."""

    score: float
    spread: float
    variant_scores: list[float]
    box: tuple[int, int, int, int]


def _tta_variants(crop_rgb: np.ndarray) -> list[np.ndarray]:
    """Build the TTA set: each scale, each with and without a horizontal flip."""
    variants: list[np.ndarray] = []
    height, width = crop_rgb.shape[:2]

    for scale in _TTA_SCALES:
        if scale == 1.0:
            scaled = crop_rgb
        else:
            new_w = max(1, int(width * scale))
            new_h = max(1, int(height * scale))
            scaled = cv2.resize(crop_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
        variants.append(scaled)
        variants.append(np.ascontiguousarray(scaled[:, ::-1]))

    return variants


@torch.inference_mode()
def score_crop(
    crop_rgb: np.ndarray, spatial: SpatialModel | None = None
) -> tuple[float, float, list[float]]:
    """Return (mean manipulation probability, spread across TTA, per-variant scores).

    Logits are averaged across augmentations before softmax, as specified — that is
    not the same as averaging probabilities and is the more stable of the two.
    """
    spatial = spatial or get_spatial_model()

    variants = _tta_variants(crop_rgb)
    pixel_values = preprocess(spatial, variants)
    logits = spatial.model(pixel_values=pixel_values).logits

    mean_logits = logits.mean(dim=0, keepdim=True)
    mean_score = float(torch.softmax(mean_logits, dim=-1)[0, spatial.positive_index])

    per_variant = torch.softmax(logits, dim=-1)[:, spatial.positive_index]
    variant_scores = [float(v) for v in per_variant]
    spread = float(per_variant.std(unbiased=False))

    return mean_score, spread, variant_scores


def score_faces(
    crops_rgb: list[np.ndarray],
    boxes: list[tuple[int, int, int, int]],
    spatial: SpatialModel | None = None,
) -> list[FaceScore]:
    spatial = spatial or get_spatial_model()
    results: list[FaceScore] = []

    for crop, box in zip(crops_rgb, boxes, strict=True):
        score, spread, variants = score_crop(crop, spatial)
        results.append(
            FaceScore(score=score, spread=spread, variant_scores=variants, box=box)
        )

    return results


def aggregate_face_scores(face_scores: list[FaceScore]) -> tuple[float, float]:
    """Collapse per-face scores into one image-level score plus its spread.

    Takes the maximum: an image containing one manipulated face among several
    genuine ones is still a manipulated image. The trade-off is that false
    positives grow with face count, so per-face scores are always reported
    alongside the aggregate rather than being hidden behind it.
    """
    if not face_scores:
        raise ValueError("cannot aggregate an empty list of face scores")

    top = max(face_scores, key=lambda f: f.score)
    return top.score, top.spread
