"""Audio frequency-domain forensics -- a second, independent signal alongside
AASIST, in the same spirit as frequency.py's role for images: unsupervised,
hand-derived signal statistics rather than a trained model, contributing a
fusion weight only if the eval harness actually measures it carrying signal.

Designed from first principles for this project, not ported from a paper or
library: neural vocoders (the waveform-synthesis stage of most modern TTS/VC
pipelines) reconstruct audio from a compressed intermediate representation
(mel-spectrogram, codec tokens), and that reconstruction process tends to
leave two kinds of trace an unsupervised measurement can pick up on --
irregularity in how spectral energy falls off at high frequencies (mirroring
exactly what frequency.py's spectral_tail_irregularity already looks for in
images, applied to audio's own 1D spectrum instead of a 2D radial one), and
an unnaturally clean or unnaturally noisy harmonic structure relative to
genuine voiced speech, measured via a normalised-autocorrelation-based
harmonics-to-noise ratio (the standard Boersma HNR formula, implemented here
directly from the formula rather than a library).

Whether either measurement actually carries signal for this task is an
empirical question, not an assumption -- see DECISIONS.md for the harness run
that answers it, and eval/audio_run.py for how the fusion weight is derived
from that measurement rather than hand-picked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import stft


def averaged_spectrum(waveform: np.ndarray, sample_rate: int, bins: int = 128) -> np.ndarray:
    """Magnitude spectrum averaged across the whole clip's time frames,
    normalised to its own peak -- audio's direct analogue of frequency.py's
    azimuthal_power_spectrum, just 1D (frequency) instead of 2D (radial)
    since audio has no second spatial axis to average over."""
    nperseg = min(1024, max(64, waveform.size // 4 or 64))
    freqs, _, zxx = stft(waveform, fs=sample_rate, nperseg=nperseg)
    magnitude = np.abs(zxx)
    profile = magnitude.mean(axis=1)

    # Resample onto a fixed bin count so downstream comparisons don't depend
    # on clip length or sample rate.
    if profile.size != bins:
        source_x = np.linspace(0, 1, profile.size)
        target_x = np.linspace(0, 1, bins)
        profile = np.interp(target_x, source_x, profile)

    peak = profile.max()
    return profile / peak if peak > 0 else profile


def spectral_tail_irregularity(profile: np.ndarray) -> float:
    """How bumpy the high-frequency half of the averaged spectrum is.

    Identical logic to frequency.py's function of the same name: a natural
    spectrum decays close to monotonically, so the mean positive first
    difference over the tail is a simple, interpretable irregularity measure.
    """
    tail = profile[len(profile) // 2 :]
    if tail.size < 4:
        return 0.0
    differences = np.diff(tail)
    rises = differences[differences > 0]
    return float(rises.mean() * 100.0) if rises.size else 0.0


def _frame_hnr_db(
    frame: np.ndarray, sample_rate: int, f0_min: float, f0_max: float
) -> float | None:
    """Harmonics-to-noise ratio for one short frame via normalised
    autocorrelation (Boersma 1993's formula: HNR = 10*log10(r / (1 - r)),
    where r is the autocorrelation peak in the plausible pitch-period range,
    normalised so a perfectly periodic signal gives r=1). Returns None for a
    frame with no usable periodicity peak (silence, noise-only) rather than a
    misleading number.
    """
    frame = frame - frame.mean()
    energy = float(np.sum(frame**2))
    if energy < 1e-9:
        return None

    # Autocorrelation via FFT (fast, exact for this frame length), normalised
    # so the zero-lag value is 1.
    n = frame.size
    fft = np.fft.rfft(frame, n=2 * n)
    autocorr = np.fft.irfft(fft * np.conj(fft))[:n]
    autocorr = autocorr / autocorr[0]

    min_lag = max(1, int(sample_rate / f0_max))
    max_lag = min(n - 1, int(sample_rate / f0_min))
    if min_lag >= max_lag:
        return None

    window = autocorr[min_lag:max_lag]
    if window.size == 0:
        return None

    r = float(window.max())
    r = min(r, 0.999999)  # guard log(0) when a frame is perfectly periodic
    if r <= 0:
        return None

    return 10.0 * np.log10(r / (1.0 - r))


def harmonics_to_noise_ratio(
    waveform: np.ndarray,
    sample_rate: int,
    frame_ms: float = 30.0,
    f0_min: float = 70.0,
    f0_max: float = 400.0,
) -> float | None:
    """Clip-level HNR in dB, averaged across voiced frames. None if no frame
    in the clip has a clear enough periodicity peak to measure at all."""
    frame_len = max(1, int(sample_rate * frame_ms / 1000.0))
    hop = frame_len // 2

    values: list[float] = []
    for start in range(0, max(1, waveform.size - frame_len), hop):
        frame = waveform[start : start + frame_len]
        if frame.size < frame_len:
            continue
        hnr = _frame_hnr_db(frame, sample_rate, f0_min, f0_max)
        if hnr is not None:
            values.append(hnr)

    return float(np.median(values)) if values else None


@dataclass
class AudioFrequencyResult:
    score: float | None
    measurements: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    spectrum_profile: np.ndarray | None = None


# Fitted against a 60-sample probe of ASVspoof2019 LA (30 bonafide, 30 spoof;
# see DECISIONS.md), not guessed: bonafide mean -1.358 dB (std 1.361), spoof
# mean +1.414 dB (std 2.847) -- spoof speech measures as *more* harmonically
# clean/periodic than bonafide, consistent with vocoder reconstruction
# producing less natural aperiodic noise than a real vocal tract does.
# Standalone AUC on that probe: 0.780 (spectral_tail_irregularity separately
# measured at 0.458, i.e. no better than chance -- reported below as a
# measurement, but excluded from scoring for that reason, the same treatment
# ELA gets in frequency.py for images).
#
# The eval harness's real run (services/inference/eval/reports/audio-2026-08-28.md)
# measured this stream at AUC 0.907 in-dataset (ASVspoof2019) but only 0.685
# cross-dataset (ASVspoof2021) -- a real generalisation gap, and fusing it with
# AASIST at its calibration-derived weight *reduced* cross-dataset AUC from
# 0.962 to 0.933. This is the same validation/cross-dataset divergence pattern
# the image pipeline hit in Phase 3 (see DECISIONS.md, 2026-08-21), now
# recurring independently in audio: a signal that measures well in-distribution
# is not the same thing as a signal that generalises. Following that same
# precedent, the weight this harness measures is shipped as-is rather than
# hand-overridden -- the gap is documented, not corrected -- but this is
# genuinely a stream whose net contribution, as currently weighted, makes the
# product's audio score *worse* on held-out data, not better. Worth knowing
# before treating this module as an unqualified improvement.
_HNR_MIDPOINT_DB = 0.028
_HNR_SCALE_DB = 2.231


def _hnr_to_score(hnr_db: float) -> float:
    z = (hnr_db - _HNR_MIDPOINT_DB) / _HNR_SCALE_DB
    return float(1.0 / (1.0 + np.exp(-z)))


def measure(waveform: np.ndarray, sample_rate: int) -> AudioFrequencyResult:
    """Score from HNR only -- spectral_tail_irregularity is reported as a
    measurement for transparency but does not move the score, since it did
    not measure as separating bonafide from spoof better than chance."""
    profile = averaged_spectrum(waveform, sample_rate)
    irregularity = spectral_tail_irregularity(profile)
    hnr = harmonics_to_noise_ratio(waveform, sample_rate)

    measurements = {"spectral_tail_irregularity": round(irregularity, 4)}
    notes = [
        "spectral_tail_irregularity measured at AUC 0.458 on a 60-sample probe "
        "(no better than chance) and is reported for transparency only -- it "
        "does not contribute to this stream's score."
    ]

    score: float | None = None
    if hnr is not None:
        measurements["harmonics_to_noise_ratio_db"] = round(hnr, 4)
        score = round(_hnr_to_score(hnr), 4)
    else:
        notes.append(
            "No frame in this clip had a clear enough periodicity peak to "
            "measure a harmonics-to-noise ratio (e.g. music, silence, or "
            "heavy background noise), so this stream has no score."
        )

    return AudioFrequencyResult(
        score=score, measurements=measurements, notes=notes, spectrum_profile=profile
    )
