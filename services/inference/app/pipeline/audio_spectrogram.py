"""Renders a spectrogram artifact -- the audio stream's evidence, same role
frequency.py's radial power spectrum plot plays for images (principle 2: every
score ships a visual, not just a number). Hand-rolled with cv2 rather than
matplotlib, matching how frequency.py avoids adding a plotting dependency.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import stft


def _magnitude_db(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    """(freq, time) magnitude spectrogram in dB, oriented low-freq at the bottom."""
    nperseg = min(512, max(32, waveform.size // 4 or 32))
    _, _, zxx = stft(waveform, fs=sample_rate, nperseg=nperseg)
    magnitude = np.abs(zxx)
    db = 20.0 * np.log10(magnitude + 1e-8)
    return db[::-1, :]


def render_spectrogram(waveform: np.ndarray, sample_rate: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    db = _magnitude_db(waveform, sample_rate)
    floor = np.percentile(db, 5)
    ceiling = np.percentile(db, 99.5)
    span = max(ceiling - floor, 1e-6)
    normalized = np.clip((db - floor) / span, 0.0, 1.0)

    heat = (normalized * 255).astype(np.uint8)
    colored = cv2.applyColorMap(heat, cv2.COLORMAP_MAGMA)

    target_width, target_height = 640, 240
    resized = cv2.resize(colored, (target_width, target_height), interpolation=cv2.INTER_AREA)

    pad = 24
    canvas = np.full((target_height + pad, target_width + pad, 3), 255, dtype=np.uint8)
    canvas[0:target_height, pad : pad + target_width] = resized

    font = cv2.FONT_HERSHEY_SIMPLEX
    grey = (90, 90, 90)
    cv2.putText(canvas, "0Hz", (2, target_height - 4), font, 0.35, grey, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"{sample_rate // 2}Hz", (2, 12), font, 0.35, grey, 1, cv2.LINE_AA)

    path = output_dir / f"spectrogram_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(path), canvas)
    return path
