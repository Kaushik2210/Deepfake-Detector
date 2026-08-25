"""AASIST checkpoint loading and scoring. Model-marked: downloads AASIST.pth."""

from __future__ import annotations

import pytest
import torch

from app.models.audio_registry import get_audio_model, score_waveform

pytestmark = pytest.mark.model


def test_checkpoint_loads_without_key_mismatch() -> None:
    """Regression test: the vendored module's attribute names must exactly match
    the upstream checkpoint's state_dict keys, or load_state_dict raises."""
    model = get_audio_model()
    assert model.model.training is False


def test_score_waveform_is_a_probability() -> None:
    model = get_audio_model()
    waveform = torch.zeros(64600)
    score = score_waveform(model, waveform)
    assert 0.0 <= score <= 1.0


def test_score_waveform_is_deterministic_in_eval_mode() -> None:
    model = get_audio_model()
    waveform = torch.randn(64600)
    first = score_waveform(model, waveform)
    second = score_waveform(model, waveform)
    assert first == second
