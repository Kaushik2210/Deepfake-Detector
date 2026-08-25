"""Audio decoding, resampling, and fixed-length preprocessing. No model weights needed."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.audio_io import (
    AudioDecodeError,
    decode_audio,
    fit_to_length,
    prepare_for_model,
    resample,
)


class TestDecodeAudio:
    def test_decodes_a_valid_wav(self, sine_wave_wav) -> None:
        waveform, sample_rate = decode_audio(sine_wave_wav(duration_seconds=2.0, sample_rate=22050))
        assert sample_rate == 22050
        assert waveform.ndim == 1
        assert waveform.shape[0] == pytest.approx(2.0 * 22050, abs=1)
        assert waveform.dtype == np.float32

    def test_mixes_stereo_down_to_mono(self) -> None:
        import io

        import soundfile as sf

        stereo = np.stack(
            [np.full(1000, 0.5, dtype=np.float32), np.full(1000, -0.5, dtype=np.float32)],
            axis=1,
        )
        buffer = io.BytesIO()
        sf.write(buffer, stereo, 16000, format="WAV")

        waveform, sample_rate = decode_audio(buffer.getvalue())
        assert waveform.ndim == 1
        assert waveform.shape[0] == 1000
        # Average of +0.5 and -0.5 is ~0.
        assert waveform.mean() == pytest.approx(0.0, abs=1e-3)

    def test_raises_on_garbage_bytes(self) -> None:
        with pytest.raises(AudioDecodeError):
            decode_audio(b"this is not audio")

    def test_raises_on_empty_bytes(self) -> None:
        with pytest.raises(AudioDecodeError):
            decode_audio(b"")


class TestResample:
    def test_same_rate_is_a_no_op(self) -> None:
        waveform = np.random.default_rng(0).standard_normal(1000).astype(np.float32)
        assert np.array_equal(resample(waveform, 16000, 16000), waveform)

    def test_resamples_to_target_length_ratio(self) -> None:
        waveform = np.zeros(16000, dtype=np.float32)
        resampled = resample(waveform, 16000, 8000)
        # Downsampling by 2x should roughly halve the sample count.
        assert resampled.shape[0] == pytest.approx(8000, abs=2)

    def test_preserves_a_pure_tone_frequency(self) -> None:
        sample_rate = 22050
        t = np.linspace(0, 1.0, sample_rate, endpoint=False)
        waveform = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)

        resampled = resample(waveform, sample_rate, 16000)
        spectrum = np.abs(np.fft.rfft(resampled))
        freqs = np.fft.rfftfreq(resampled.shape[0], d=1 / 16000)
        peak_freq = freqs[np.argmax(spectrum)]

        assert peak_freq == pytest.approx(440.0, abs=5.0)


class TestFitToLength:
    def test_truncates_longer_input(self) -> None:
        waveform = np.arange(1000, dtype=np.float32)
        fitted = fit_to_length(waveform, 400)
        assert fitted.shape[0] == 400
        assert np.array_equal(fitted, waveform[:400])

    def test_tiles_shorter_input(self) -> None:
        waveform = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        fitted = fit_to_length(waveform, 8)
        assert fitted.shape[0] == 8
        # Tiled and truncated: [1,2,3, 1,2,3, 1,2].
        assert np.array_equal(fitted, np.array([1, 2, 3, 1, 2, 3, 1, 2], dtype=np.float32))

    def test_exact_length_is_unchanged(self) -> None:
        waveform = np.arange(10, dtype=np.float32)
        assert np.array_equal(fit_to_length(waveform, 10), waveform)


class TestPrepareForModel:
    def test_produces_the_exact_target_shape(self) -> None:
        waveform = np.random.default_rng(0).standard_normal(9000).astype(np.float32)
        tensor = prepare_for_model(
            waveform, sample_rate=22050, target_sr=16000, target_samples=64600
        )
        assert tuple(tensor.shape) == (64600,)
        assert tensor.dtype.is_floating_point
