"""Audio envelope checks. No model weights needed."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.audio_envelope import assess, clipping_ratio, silence_ratio


class TestClippingRatio:
    def test_clean_tone_reports_zero(self) -> None:
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        waveform = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        assert clipping_ratio(waveform) == 0.0

    def test_full_scale_waveform_reports_high_ratio(self) -> None:
        waveform = np.full(1000, 0.9999, dtype=np.float32)
        assert clipping_ratio(waveform) == pytest.approx(1.0)

    def test_empty_waveform_is_zero(self) -> None:
        assert clipping_ratio(np.array([], dtype=np.float32)) == 0.0


class TestSilenceRatio:
    def test_silence_reports_high_ratio(self) -> None:
        waveform = np.zeros(16000, dtype=np.float32)
        assert silence_ratio(waveform) == pytest.approx(1.0)

    def test_loud_tone_reports_low_ratio(self) -> None:
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        waveform = (0.8 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        assert silence_ratio(waveform) == pytest.approx(0.0)

    def test_short_waveform_uses_whole_signal_rms(self) -> None:
        assert silence_ratio(np.zeros(10, dtype=np.float32)) == 1.0


class TestAssess:
    def test_clean_full_length_clip_has_only_the_calibration_penalty(self) -> None:
        sample_rate = 16000
        t = np.linspace(0, 5.0, sample_rate * 5, endpoint=False)
        waveform = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

        assessment = assess(waveform, sample_rate, duration_seconds=5.0)

        assert assessment.in_distribution is True
        assert len(assessment.penalties) == 1
        assert "uncalibrated" in assessment.penalties[0][0]

    def test_short_clip_is_penalised_for_repetition(self) -> None:
        sample_rate = 16000
        waveform = np.random.default_rng(0).standard_normal(sample_rate).astype(np.float32) * 0.3

        assessment = assess(waveform, sample_rate, duration_seconds=1.0)

        reasons = [reason for reason, _ in assessment.penalties]
        assert any("repeating" in r for r in reasons)
        assert assessment.in_distribution is False

    def test_silent_clip_is_penalised(self) -> None:
        sample_rate = 16000
        waveform = np.zeros(sample_rate * 5, dtype=np.float32)

        assessment = assess(waveform, sample_rate, duration_seconds=5.0)

        reasons = [reason for reason, _ in assessment.penalties]
        assert any("near-silent" in r for r in reasons)

    def test_clipped_clip_is_penalised(self) -> None:
        sample_rate = 16000
        waveform = np.full(sample_rate * 5, 0.9999, dtype=np.float32)
        waveform[::2] = -0.9999

        assessment = assess(waveform, sample_rate, duration_seconds=5.0)

        reasons = [reason for reason, _ in assessment.penalties]
        assert any("clipped" in r for r in reasons)

    def test_factors_are_recorded(self) -> None:
        sample_rate = 16000
        waveform = np.zeros(sample_rate * 2, dtype=np.float32)

        assessment = assess(waveform, sample_rate, duration_seconds=2.0)

        assert "2.00s" in assessment.factors["duration"]
        assert "16000Hz" in assessment.factors["sample_rate"]
        assert "clipping" in assessment.factors
        assert "silence_ratio" in assessment.factors
