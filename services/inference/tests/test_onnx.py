"""ONNX export path.

All marked ``model``: they need the real weights.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.models.onnx_export import OnnxSpatialSession, export_spatial_model
from app.models.registry import get_spatial_model

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def exported_model(tmp_path_factory):
    return export_spatial_model(tmp_path_factory.mktemp("onnx") / "spatial.onnx")


def test_export_writes_a_loadable_model(exported_model) -> None:
    import onnx

    assert exported_model.is_file()
    onnx.checker.check_model(onnx.load(str(exported_model)))


def test_export_is_self_contained(exported_model) -> None:
    """The .onnx file must carry its own weights.

    The exporter can split weights into a sibling .onnx.data, which produces a
    model that loads fine locally and breaks the moment only the .onnx is shipped.
    """
    siblings = [
        p for p in exported_model.parent.iterdir() if p.name.startswith(exported_model.name + ".")
    ]
    assert not siblings, f"weights spilled into external files: {[p.name for p in siblings]}"
    assert exported_model.stat().st_size > 100_000_000


def test_onnx_scores_match_torch(exported_model, real_face_bgr: np.ndarray) -> None:
    """The two backends must not disagree, or the same media scores differently by route.

    Compared against a single un-augmented forward pass rather than ``score_crop``,
    which averages over test-time augmentations and so is not the same quantity.
    """
    import torch

    from app.models.registry import preprocess

    crop_rgb = cv2.cvtColor(cv2.resize(real_face_bgr, (224, 224)), cv2.COLOR_BGR2RGB)
    spatial = get_spatial_model()

    with torch.inference_mode():
        pixel_values = preprocess(spatial, [crop_rgb])
        logits = spatial.model(pixel_values=pixel_values).logits
        torch_score = float(torch.softmax(logits, dim=-1)[0, spatial.positive_index])

    onnx_score = OnnxSpatialSession(exported_model).score([crop_rgb])[0]

    assert onnx_score == pytest.approx(torch_score, abs=1e-3)


def test_onnx_supports_batches(exported_model, real_face_bgr: np.ndarray) -> None:
    crop_rgb = cv2.cvtColor(cv2.resize(real_face_bgr, (224, 224)), cv2.COLOR_BGR2RGB)

    session = OnnxSpatialSession(exported_model)
    scores = session.score([crop_rgb, crop_rgb])

    assert len(scores) == 2
    assert scores[0] == pytest.approx(scores[1], abs=1e-5)


def test_missing_export_raises_clearly(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="run export_spatial_model"):
        OnnxSpatialSession(tmp_path / "absent.onnx")
