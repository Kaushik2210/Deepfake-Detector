"""Model loading and version tracking for Stream A.

The classifier is ``prithivMLmods/Deep-Fake-Detector-v2-Model`` (Apache-2.0, ViT
base, ``id2label = {0: Realism, 1: Deepfake}``). The positive-class index is
resolved from the model's own label map rather than hardcoded, so swapping in a
different checkpoint can't silently invert every score in the product.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification

from app.config import get_settings

_LOAD_LOCK = threading.Lock()

# Substrings that mark the "manipulated" side of a binary label map, lowercased.
_POSITIVE_LABEL_HINTS = ("fake", "deepfake", "synthetic", "manipulated", "ai")


@dataclass
class SpatialModel:
    model: torch.nn.Module
    processor: object
    model_id: str
    revision: str
    positive_index: int
    id2label: dict[int, str]

    @property
    def version_string(self) -> str:
        return f"{self.model_id}@{self.revision}"


def _resolve_positive_index(id2label: dict[int, str]) -> int:
    """Find which logit index means 'manipulated'."""
    for index, label in id2label.items():
        if any(hint in label.lower() for hint in _POSITIVE_LABEL_HINTS):
            return int(index)
    raise ValueError(
        "could not identify the manipulated-class index from the model's id2label "
        f"({id2label!r}); refusing to guess, because guessing wrong inverts every score"
    )


def _resolve_revision(model_id: str, revision: str) -> str:
    """Pin a moving ref like 'main' to the commit it currently points at."""
    try:
        from huggingface_hub import model_info

        return model_info(model_id, revision=revision).sha or revision
    except Exception:
        # Offline or hub unavailable — report the ref we were given rather than failing.
        return revision


@lru_cache(maxsize=1)
def get_spatial_model() -> SpatialModel:
    settings = get_settings()

    with _LOAD_LOCK:
        processor = AutoImageProcessor.from_pretrained(
            settings.spatial_model_id,
            revision=settings.spatial_model_revision,
            cache_dir=settings.model_cache_dir,
        )
        model = AutoModelForImageClassification.from_pretrained(
            settings.spatial_model_id,
            revision=settings.spatial_model_revision,
            cache_dir=settings.model_cache_dir,
        )
        model.eval()

    id2label = {int(k): str(v) for k, v in model.config.id2label.items()}

    return SpatialModel(
        model=model,
        processor=processor,
        model_id=settings.spatial_model_id,
        revision=_resolve_revision(
            settings.spatial_model_id, settings.spatial_model_revision
        ),
        positive_index=_resolve_positive_index(id2label),
        id2label=id2label,
    )


def preprocess(spatial: SpatialModel, images_rgb: list[np.ndarray]) -> torch.Tensor:
    """Turn RGB uint8 arrays into the model's expected input tensor."""
    encoded = spatial.processor(images=images_rgb, return_tensors="pt")
    return encoded["pixel_values"]


def is_loaded() -> bool:
    return get_spatial_model.cache_info().currsize > 0
