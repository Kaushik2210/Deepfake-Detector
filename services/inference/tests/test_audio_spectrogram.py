"""Spectrogram artifact rendering. No model weights needed."""

from __future__ import annotations

import numpy as np

from app.pipeline.audio_spectrogram import render_spectrogram


def test_renders_a_readable_png(tmp_path) -> None:
    sample_rate = 16000
    t = np.linspace(0, 2.0, sample_rate * 2, endpoint=False)
    waveform = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    path = render_spectrogram(waveform, sample_rate, tmp_path)

    assert path.is_file()
    assert path.suffix == ".png"
    assert path.stat().st_size > 0


def test_handles_very_short_audio_without_crashing(tmp_path) -> None:
    waveform = np.array([0.1, -0.1, 0.2, -0.2], dtype=np.float32)
    path = render_spectrogram(waveform, 16000, tmp_path)
    assert path.is_file()
