"""End-to-end audio analysis. Model-marked: needs the AASIST checkpoint."""

from __future__ import annotations

import pytest

from app.bands import score_to_band
from app.pipeline.analyze_audio import AudioTooLongError, analyze_audio
from app.pipeline.audio_io import AudioDecodeError

pytestmark = pytest.mark.model


def test_rejects_undecodable_bytes() -> None:
    with pytest.raises(AudioDecodeError):
        analyze_audio(b"not audio")


def test_rejects_a_clip_over_the_duration_limit(sine_wave_wav, monkeypatch) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("VERIFRAME_MAX_AUDIO_DURATION_SECONDS", "1")
    try:
        raw = sine_wave_wav(duration_seconds=5.0)
        with pytest.raises(AudioTooLongError):
            analyze_audio(raw, mime_type="audio/wav")
    finally:
        get_settings.cache_clear()


def test_full_report_shape(sine_wave_wav) -> None:
    raw = sine_wave_wav(duration_seconds=3.0)
    report = analyze_audio(raw, filename="clip.wav", mime_type="audio/wav")

    assert report.media_meta.kind == "audio"
    assert report.media_meta.duration_seconds == pytest.approx(3.0, abs=0.1)
    assert report.band == score_to_band(report.score).id
    lo, hi = report.uncertainty
    assert 0.0 <= lo <= report.score <= hi <= 1.0
    assert report.disclaimer
    assert report.faces == []
    assert report.conclusion is None


def test_produces_the_aasist_and_frequency_streams(sine_wave_wav) -> None:
    raw = sine_wave_wav(duration_seconds=3.0)
    report = analyze_audio(raw, mime_type="audio/wav")

    names = {s.name for s in report.streams}
    assert names == {"audio", "audio_frequency"}
    for stream in report.streams:
        assert 0.0 <= stream.score <= 1.0
        assert stream.artifacts

    audio_stream = next(s for s in report.streams if s.name == "audio")
    spectrogram_artifacts = [a for a in audio_stream.artifacts if a.type == "spectrum_plot"]
    assert len(spectrogram_artifacts) == 1


def test_short_clip_is_flagged_out_of_distribution(sine_wave_wav) -> None:
    raw = sine_wave_wav(duration_seconds=0.5)
    report = analyze_audio(raw, mime_type="audio/wav")
    assert report.envelope.in_distribution is False


def test_deterministic_for_the_same_input(sine_wave_wav) -> None:
    raw = sine_wave_wav(duration_seconds=3.0)
    first = analyze_audio(raw, mime_type="audio/wav")
    second = analyze_audio(raw, mime_type="audio/wav")
    assert {s.name: s.score for s in first.streams} == {s.name: s.score for s in second.streams}
