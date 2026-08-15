"""ONNX export and inference path for the spatial classifier.

Grad-CAM needs autograd, so the torch path stays the default for anything that
produces a heatmap. The ONNX path exists for throughput on scoring-only work and
is checked against torch for numerical agreement in the test suite.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from app.config import get_settings
from app.models.registry import SpatialModel, get_spatial_model, preprocess


class _LogitsOnly(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model
        # A freshly constructed wrapper defaults to training mode even when the
        # model inside it is already in eval, which would export dropout as active.
        self.eval()

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        return self.model(pixel_values=pixel_values).logits


def default_onnx_path() -> Path:
    settings = get_settings()
    safe_id = settings.spatial_model_id.replace("/", "__")
    return settings.model_cache_dir / f"{safe_id}.onnx"


def export_spatial_model(
    output_path: Path | None = None,
    spatial: SpatialModel | None = None,
    opset: int = 17,
    external_data: bool = False,
) -> Path:
    """Export the classifier to ONNX with a dynamic batch axis.

    Defaults to a single self-contained file. The exporter would otherwise split
    weights into a sibling ``.onnx.data``, which loads faster but silently
    produces a broken model if only the ``.onnx`` file is copied to a deployment.
    At roughly 340 MB this model sits well inside protobuf's 2 GB ceiling, so the
    split buys little and costs a failure mode.
    """
    spatial = spatial or get_spatial_model()
    output_path = output_path or default_onnx_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    size = get_settings().spatial_input_size
    dummy = torch.randn(1, 3, size, size)

    torch.onnx.export(
        _LogitsOnly(spatial.model),
        (dummy,),
        str(output_path),
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_shapes={"pixel_values": {0: torch.export.Dim("batch")}},
        opset_version=opset,
        external_data=external_data,
        dynamo=True,
    )

    return output_path


class OnnxSpatialSession:
    """ONNX Runtime session exposing the same scoring contract as the torch path."""

    def __init__(self, model_path: Path | None = None, spatial: SpatialModel | None = None) -> None:
        import onnxruntime

        self.spatial = spatial or get_spatial_model()
        self.model_path = model_path or default_onnx_path()
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"no ONNX export at {self.model_path}; run export_spatial_model() first"
            )
        self.session = onnxruntime.InferenceSession(
            str(self.model_path), providers=["CPUExecutionProvider"]
        )

    def logits(self, images_rgb: list[np.ndarray]) -> np.ndarray:
        pixel_values = preprocess(self.spatial, images_rgb).numpy()
        (out,) = self.session.run(["logits"], {"pixel_values": pixel_values})
        return out

    def score(self, images_rgb: list[np.ndarray]) -> list[float]:
        logits = self.logits(images_rgb)
        shifted = logits - logits.max(axis=-1, keepdims=True)
        exp = np.exp(shifted)
        probabilities = exp / exp.sum(axis=-1, keepdims=True)
        return [float(p) for p in probabilities[:, self.spatial.positive_index]]
