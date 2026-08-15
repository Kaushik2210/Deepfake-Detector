"""Grad-CAM heatmaps for the ViT classifier.

Principle 2: a score with no visual explanation is a failure. Every report that
carries a spatial score also carries the heatmap that produced it.

Two ViT-specific details matter here. Hugging Face classification heads return a
dataclass rather than a tensor, so the model is wrapped to expose bare logits; and
transformer activations are a sequence of tokens, so they are reshaped back onto
the patch grid before the CAM is computed.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np
import torch
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

from app.config import get_settings
from app.models.registry import SpatialModel, get_spatial_model, preprocess


class _LogitsOnly(torch.nn.Module):
    """Unwraps a Hugging Face classification output down to its logits tensor."""

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        return self.model(pixel_values=pixel_values).logits


def _reshape_transform(tensor: torch.Tensor) -> torch.Tensor:
    """Drop the CLS token and fold the patch sequence back into a square grid."""
    tokens = tensor[:, 1:, :]
    batch, num_tokens, channels = tokens.shape

    side = int(round(num_tokens**0.5))
    if side * side != num_tokens:
        raise ValueError(f"patch token count {num_tokens} is not a perfect square")

    result = tokens.reshape(batch, side, side, channels)
    return result.permute(0, 3, 1, 2)


def _encoder_blocks(model: torch.nn.Module) -> torch.nn.ModuleList:
    """Locate the transformer block list.

    transformers <5 nests these at ``vit.encoder.layer``; transformers 5 flattened
    it to ``vit.layers``. Both are checked so an upgrade in either direction
    doesn't silently break heatmap generation.
    """
    base = getattr(model, "vit", model)

    for path in (("encoder", "layer"), ("layers",)):
        node: torch.nn.Module | None = base
        for attribute in path:
            node = getattr(node, attribute, None)
            if node is None:
                break
        if isinstance(node, torch.nn.ModuleList) and len(node) > 0:
            return node

    raise AttributeError(
        f"could not locate transformer blocks on {type(model).__name__}; "
        "Grad-CAM target layer selection needs updating for this architecture"
    )


def _target_layers(spatial: SpatialModel) -> list[torch.nn.Module]:
    """Last block's pre-attention norm — the usual ViT choice for Grad-CAM."""
    last_block = _encoder_blocks(spatial.model)[-1]

    norm = getattr(last_block, "layernorm_before", None)
    if norm is None:
        raise AttributeError(
            f"transformer block {type(last_block).__name__} has no layernorm_before"
        )
    return [norm]


def generate_heatmap(
    crop_rgb: np.ndarray,
    spatial: SpatialModel | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Render a Grad-CAM overlay for one face crop and return the file it wrote."""
    spatial = spatial or get_spatial_model()
    settings = get_settings()
    output_dir = output_dir or settings.artifact_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pixel_values = preprocess(spatial, [crop_rgb])
    wrapped = _LogitsOnly(spatial.model)

    cam = GradCAM(
        model=wrapped,
        target_layers=_target_layers(spatial),
        reshape_transform=_reshape_transform,
    )
    grayscale = cam(
        input_tensor=pixel_values,
        targets=[ClassifierOutputTarget(spatial.positive_index)],
    )[0]

    # Overlay onto the crop resized to the CAM's own resolution.
    size = (grayscale.shape[1], grayscale.shape[0])
    base = cv2.resize(crop_rgb, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    overlay = show_cam_on_image(base, grayscale, use_rgb=True)

    path = output_dir / f"gradcam_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    return path
