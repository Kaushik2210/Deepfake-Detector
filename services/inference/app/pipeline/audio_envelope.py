"""Out-of-distribution envelope checks for audio, mirroring envelope.py's role for images.

AASIST was trained on ASVspoof2019 LA: clean, single-speaker, studio-adjacent
recordings a few seconds long. Real-world audio -- phone calls, voice notes,
background noise, long clips tiled down to a 4-second window -- sits outside
that distribution in ways worth surfacing rather than silently absorbing into
an unqualified score.
"""

from __future__ import annotations

import numpy as np

from app.config import get_settings
from app.pipeline.envelope import EnvelopeAssessment

# A sample counts as "clipped" once it sits within this fraction of full scale
# (audio is float32 in [-1, 1]); a handful of true full-scale samples happens
# naturally, so the envelope check is on *ratio* of the clip, not on any one sample.
_CLIP_THRESHOLD = 0.999
# RMS energy below this, per short frame, counts as silence for the silence-ratio
# measurement -- quiet enough that no speech content could be resolved from it.
_SILENCE_RMS_THRESHOLD = 0.01
_FRAME_SAMPLES = 1024


def clipping_ratio(waveform: np.ndarray) -> float:
    if waveform.size == 0:
        return 0.0
    return float(np.mean(np.abs(waveform) >= _CLIP_THRESHOLD))


def silence_ratio(waveform: np.ndarray) -> float:
    """Fraction of short frames whose RMS energy reads as silence."""
    if waveform.size < _FRAME_SAMPLES:
        rms = float(np.sqrt(np.mean(waveform.astype(np.float64) ** 2)))
        return 1.0 if rms < _SILENCE_RMS_THRESHOLD else 0.0

    usable = waveform.size - (waveform.size % _FRAME_SAMPLES)
    frames = waveform[:usable].reshape(-1, _FRAME_SAMPLES)
    frame_rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    return float(np.mean(frame_rms < _SILENCE_RMS_THRESHOLD))


def assess(waveform: np.ndarray, sample_rate: int, duration_seconds: float) -> EnvelopeAssessment:
    settings = get_settings()
    assessment = EnvelopeAssessment(in_distribution=True)

    assessment.factors["duration"] = f"{duration_seconds:.2f}s"
    assessment.factors["sample_rate"] = f"{sample_rate}Hz"

    target_seconds = settings.audio_target_samples / settings.audio_target_sample_rate
    if duration_seconds < target_seconds:
        # Short clips are tiled (repeated) to fill AASIST's fixed 4.04s window
        # rather than rejected -- see audio_io.fit_to_length -- but a clip
        # tiled several times over is not the same evidence as a clip that
        # naturally filled the window, so this is disclosed as a penalty
        # scaled by how much repetition was needed.
        repeats = target_seconds / max(duration_seconds, 0.01)
        severity = max(0.4, min(1.0, 1.0 / repeats))
        assessment.penalties.append(
            (
                f"Clip is only {duration_seconds:.2f}s; the classifier's fixed "
                f"{target_seconds:.1f}s input window was filled by repeating it "
                f"~{repeats:.1f}x rather than hearing that much unique audio.",
                round(severity, 3),
            )
        )

    clip_ratio = clipping_ratio(waveform)
    assessment.factors["clipping"] = f"{clip_ratio * 100:.2f}% of samples"
    if clip_ratio > settings.audio_clipping_ratio_threshold:
        assessment.penalties.append(
            (
                f"Audio is clipped ({clip_ratio * 100:.2f}% of samples at full scale), "
                "which distorts the waveform features this detector relies on.",
                0.7,
            )
        )

    hush = silence_ratio(waveform)
    assessment.factors["silence_ratio"] = f"{hush * 100:.1f}%"
    if hush > settings.audio_silence_ratio_threshold:
        assessment.penalties.append(
            (
                f"{hush * 100:.0f}% of this clip is near-silent, leaving little voiced "
                "signal for the classifier to have actually evaluated.",
                0.5,
            )
        )

    # Same treatment as the image pipeline's calibration-status penalty: no eval
    # harness has fitted temperature scaling for this stream yet, so raw
    # softmax output is disclosed as uncalibrated rather than presented as if it
    # were a validated probability.
    assessment.penalties.append(
        (
            "Scores are uncalibrated: no eval harness has fitted temperature scaling "
            "for the audio stream yet. Treat the magnitude as indicative only.",
            0.85,
        )
    )

    assessment.in_distribution = len(assessment.penalties) <= 1
    return assessment
