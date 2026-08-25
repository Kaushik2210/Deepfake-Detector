"""Audio decode, resampling, and the fixed-length preprocessing AASIST expects.

Formats: whatever the installed libsndfile supports through ``soundfile`` --
WAV and FLAC unconditionally, OGG/MP3 depending on the libsndfile build bundled
with the platform wheel. Unlike image/video decode this never shells out to
system ffmpeg, so it stays within this service's existing dependency footprint.
"""

from __future__ import annotations

import io
import math

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly


class AudioDecodeError(ValueError):
    """Raised when the uploaded bytes are not decodable as audio."""


def decode_audio(raw: bytes) -> tuple[np.ndarray, int]:
    """Bytes in, (mono float32 waveform in [-1, 1], sample_rate) out."""
    try:
        waveform, sample_rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    except Exception as exc:
        raise AudioDecodeError("could not decode the uploaded bytes as audio") from exc

    if waveform.size == 0:
        raise AudioDecodeError("decoded audio is empty")

    # Multi-channel input is averaged down to mono; AASIST, like the ASVspoof
    # corpus it was trained on, has no notion of a stereo/channel-count input.
    mono = waveform.mean(axis=1).astype(np.float32)
    return mono, int(sample_rate)


def resample(waveform: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Rational-factor resampling (polyphase filter), exact when the ratio is exact."""
    if orig_sr == target_sr:
        return waveform
    gcd = math.gcd(orig_sr, target_sr)
    up, down = target_sr // gcd, orig_sr // gcd
    return resample_poly(waveform, up, down).astype(np.float32)


def fit_to_length(waveform: np.ndarray, target_samples: int) -> np.ndarray:
    """Truncate if longer, tile (repeat) if shorter -- AASIST's own ``pad()``.

    Matches the upstream repo's deterministic eval-time preprocessing exactly
    (as opposed to ``pad_random``, which is training-only and takes a random
    crop instead of always the first ``target_samples``).
    """
    length = waveform.shape[0]
    if length >= target_samples:
        return waveform[:target_samples]
    repeats = target_samples // length + 1
    return np.tile(waveform, repeats)[:target_samples]


def prepare_for_model(
    waveform: np.ndarray, sample_rate: int, target_sr: int, target_samples: int
) -> torch.Tensor:
    """Full preprocessing chain: resample, then fit to AASIST's fixed input length."""
    resampled = resample(waveform, sample_rate, target_sr)
    fitted = fit_to_length(resampled, target_samples)
    return torch.from_numpy(fitted.copy())
