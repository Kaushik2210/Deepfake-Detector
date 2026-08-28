"""Audio frequency-domain forensics (hand-derived HNR + spectral-tail
measurements). No model weights needed -- pure signal processing."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.audio_frequency import (
    averaged_spectrum,
    harmonics_to_noise_ratio,
    measure,
    spectral_tail_irregularity,
)


class TestAveragedSpectrum:
    def test_returns_the_requested_bin_count(self) -> None:
        waveform = np.random.default_rng(0).standard_normal(16000).astype(np.float32)
        profile = averaged_spectrum(waveform, 16000, bins=64)
        assert profile.shape == (64,)

    def test_normalised_to_its_own_peak(self) -> None:
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        waveform = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        profile = averaged_spectrum(waveform, 16000)
        assert profile.max() == pytest.approx(1.0)
        assert profile.min() >= 0.0

    def test_a_pure_tone_peaks_near_its_own_frequency(self) -> None:
        sample_rate = 16000
        t = np.linspace(0, 1.0, sample_rate, endpoint=False)
        # A low tone should peak in the low-frequency bins.
        waveform = np.sin(2 * np.pi * 200 * t).astype(np.float32)
        profile = averaged_spectrum(waveform, sample_rate, bins=128)
        peak_bin = int(np.argmax(profile))
        assert peak_bin < len(profile) // 4


class TestSpectralTailIrregularity:
    def test_a_smoothly_decaying_profile_is_low(self) -> None:
        profile = np.linspace(1.0, 0.0, 128)
        assert spectral_tail_irregularity(profile) == pytest.approx(0.0, abs=1e-6)

    def test_a_bumpy_tail_is_positive(self) -> None:
        profile = np.linspace(1.0, 0.0, 128)
        rng = np.random.default_rng(0)
        profile[64:] += rng.uniform(0, 0.3, size=64)
        assert spectral_tail_irregularity(profile) > 0.0

    def test_too_short_a_profile_returns_zero(self) -> None:
        assert spectral_tail_irregularity(np.array([1.0, 0.5])) == 0.0


class TestHarmonicsToNoiseRatio:
    def test_a_pure_tone_has_a_high_ratio(self) -> None:
        sample_rate = 16000
        t = np.linspace(0, 1.0, sample_rate, endpoint=False)
        # A clean periodic tone in the voiced-speech pitch range.
        waveform = (0.5 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
        hnr = harmonics_to_noise_ratio(waveform, sample_rate)
        assert hnr is not None
        # Circular (unwindowed) autocorrelation loses some peak sharpness at
        # frame edges, so this is a qualitative check (clearly periodic reads
        # as clearly higher-HNR than noise), not a claim about the exact value.
        assert hnr > 3.0

    def test_white_noise_has_a_low_or_unmeasurable_ratio(self) -> None:
        sample_rate = 16000
        rng = np.random.default_rng(0)
        waveform = (0.3 * rng.standard_normal(sample_rate)).astype(np.float32)
        hnr = harmonics_to_noise_ratio(waveform, sample_rate)
        # Either it's measured low, or no frame had a clean enough peak at all
        # -- both are the correct outcome for pure noise, unlike a crash.
        assert hnr is None or hnr < 10.0

    def test_silence_is_unmeasurable(self) -> None:
        waveform = np.zeros(16000, dtype=np.float32)
        assert harmonics_to_noise_ratio(waveform, 16000) is None


class TestMeasure:
    def test_clean_tone_produces_a_score_in_range(self) -> None:
        sample_rate = 16000
        t = np.linspace(0, 2.0, sample_rate * 2, endpoint=False)
        waveform = (0.5 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)

        result = measure(waveform, sample_rate)

        assert result.score is not None
        assert 0.0 <= result.score <= 1.0
        assert "harmonics_to_noise_ratio_db" in result.measurements
        assert "spectral_tail_irregularity" in result.measurements

    def test_silence_produces_no_score_but_does_not_crash(self) -> None:
        waveform = np.zeros(16000, dtype=np.float32)
        result = measure(waveform, 16000)
        assert result.score is None
        assert "harmonics_to_noise_ratio_db" not in result.measurements

    def test_spectral_tail_irregularity_never_moves_the_score(self) -> None:
        """Regression guard: this measurement is deliberately reported but
        excluded from scoring, since it measured no better than chance on a
        real labelled probe (AUC 0.458) -- see DECISIONS.md. The scoring
        formula must only ever be driven by HNR."""
        import inspect

        from app.pipeline import audio_frequency

        source = inspect.getsource(audio_frequency.measure)
        assert "_hnr_to_score(hnr)" in source
        assert "_hnr_to_score(irregularity)" not in source
