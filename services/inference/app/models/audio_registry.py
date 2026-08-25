"""Model loading for the audio anti-spoofing stream.

The classifier is AASIST (NAVER/Clova AI, MIT license, code and pretrained
weights both -- see LICENSES.md), trained on ASVspoof2019 LA (ODC-By, commercial
use permitted). Unlike Stream A's checkpoint this is not a ``transformers``
model -- it is vendored research code (``app/models/aasist.py``) plus a raw
``.pth`` state dict, downloaded once into the model cache the same way
``ensure_yunet_model`` handles YuNet.
"""

from __future__ import annotations

import threading
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import torch

from app.config import get_settings
from app.models.aasist import AASIST_CONFIG, AasistModel

_LOAD_LOCK = threading.Lock()

# AASIST's own output head is a 2-way logit: index 0 = bonafide, index 1 = spoof
# -- fixed by how the upstream checkpoint was trained (main.py's
# produce_evaluation_file reads batch_out[:, 1] as the spoof score), not
# something to infer from a label map the way Stream A does.
_SPOOF_LOGIT_INDEX = 1


@dataclass
class AudioModel:
    model: torch.nn.Module
    checkpoint_url: str

    @property
    def version_string(self) -> str:
        return f"AASIST ({self.checkpoint_url})"


def ensure_aasist_checkpoint() -> Path:
    """Download AASIST.pth into the model cache if it isn't there yet."""
    settings = get_settings()
    dest = settings.model_cache_dir / "AASIST.pth"

    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(  # noqa: S310 - fixed, non-user-supplied URL
            settings.audio_model_checkpoint_url, tmp
        )
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)

    return dest


@lru_cache(maxsize=1)
def get_audio_model() -> AudioModel:
    settings = get_settings()

    with _LOAD_LOCK:
        checkpoint_path = ensure_aasist_checkpoint()
        model = AasistModel(AASIST_CONFIG)
        state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()

    return AudioModel(model=model, checkpoint_url=settings.audio_model_checkpoint_url)


def is_loaded() -> bool:
    return get_audio_model.cache_info().currsize > 0


def score_waveform(model: AudioModel, waveform: torch.Tensor) -> float:
    """Spoof probability in [0, 1] for one already-preprocessed waveform.

    ``waveform`` must already be mono, 16kHz, and tiled/truncated to
    ``AASIST_CONFIG["nb_samp"]`` samples -- see ``pipeline/audio_io.py``.
    """
    with torch.no_grad():
        _, logits = model.model(waveform.unsqueeze(0))
        probabilities = torch.softmax(logits, dim=-1)
        return float(probabilities[0, _SPOOF_LOGIT_INDEX].item())
