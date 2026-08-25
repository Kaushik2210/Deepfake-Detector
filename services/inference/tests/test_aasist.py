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


def test_spoof_samples_score_higher_than_bonafide_on_real_data() -> None:
    """Regression test for the label-direction bug caught by the eval harness:
    _SPOOF_LOGIT_INDEX shipped inverted in stage 1 (AUC 0.0 -- a perfectly
    *backwards* classifier -- on the corpus AASIST was trained on) and was only
    caught by actually running scored, labelled samples through it, not by
    checking the score merely lands in [0, 1]. Pulls a handful of real
    ASVspoof2019 LA samples the same way the eval harness does."""
    from app.config import get_settings
    from app.pipeline.audio_io import prepare_for_model
    from eval.audio_datasets import AUDIO_DATASETS, load_audio_samples

    settings = get_settings()
    model = get_audio_model()

    samples = list(load_audio_samples(AUDIO_DATASETS["asvspoof2019"], limit=8, seed=0))
    bonafide_scores = []
    spoof_scores = []
    for sample in samples:
        tensor = prepare_for_model(
            sample.waveform, sample.sample_rate,
            settings.audio_target_sample_rate, settings.audio_target_samples,
        )
        score = score_waveform(model, tensor)
        (spoof_scores if sample.label == 1 else bonafide_scores).append(score)

    assert bonafide_scores and spoof_scores
    assert sum(spoof_scores) / len(spoof_scores) > sum(bonafide_scores) / len(bonafide_scores)
