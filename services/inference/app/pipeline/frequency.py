"""Stream B — frequency and signal forensics.

Generative models leave spectral fingerprints that survive resizing but not heavy
recompression. This measures four of them and combines them into one stream
score. ELA is produced as a supporting visual only and deliberately contributes
nothing to the score: it is widely misread and unreliable on its own.

An important caveat that shapes how this stream is weighted downstream: these are
unsupervised statistics with hand-derived thresholds, not a trained classifier.
They flag *unusual* signal structure, and unusual is not the same as manipulated
— a heavily edited but authentic photograph can look unusual too. The fusion
weight comes from measured validation AUC, so if these measurements turn out to
carry little signal the fusion will say so rather than us assuming.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.config import get_settings


@dataclass
class FrequencyResult:
    score: float
    measurements: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    spectrum_plot: Path | None = None


def azimuthal_power_spectrum(gray: np.ndarray, bins: int = 64) -> np.ndarray:
    """Radially averaged FFT power spectrum, normalised to its own peak.

    GAN and diffusion upsampling stacks tend to leave periodic structure that
    shows up as bumps in the high-frequency tail of this curve, where a
    photograph usually falls away smoothly.
    """
    windowed = gray.astype(np.float64)
    windowed = windowed - windowed.mean()

    # Hann window in both axes, so the FFT does not read the image border as an
    # abrupt edge and manufacture high-frequency energy that is not there.
    rows = np.hanning(windowed.shape[0])[:, None]
    cols = np.hanning(windowed.shape[1])[None, :]
    windowed = windowed * rows * cols

    spectrum = np.abs(np.fft.fftshift(np.fft.fft2(windowed))) ** 2
    spectrum = np.log1p(spectrum)

    height, width = spectrum.shape
    cy, cx = height / 2.0, width / 2.0
    y, x = np.indices(spectrum.shape)
    radius = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)

    max_radius = min(cy, cx)
    if max_radius < 2:
        return np.zeros(bins)

    edges = np.linspace(0, max_radius, bins + 1)
    profile = np.zeros(bins)
    flat_radius = radius.ravel()
    flat_spectrum = spectrum.ravel()

    for i in range(bins):
        mask = (flat_radius >= edges[i]) & (flat_radius < edges[i + 1])
        if mask.any():
            profile[i] = flat_spectrum[mask].mean()

    peak = profile.max()
    return profile / peak if peak > 0 else profile


def spectral_tail_irregularity(profile: np.ndarray) -> float:
    """How bumpy the high-frequency half of the spectrum is.

    A natural spectrum decays close to monotonically. Resampling artefacts show
    up as local reversals in that decay, so the mean positive first difference
    over the tail is a simple, interpretable measure of irregularity.
    """
    tail = profile[len(profile) // 2 :]
    if tail.size < 4:
        return 0.0

    differences = np.diff(tail)
    rises = differences[differences > 0]
    return float(rises.mean() * 100.0) if rises.size else 0.0


def dct_coefficient_stats(gray: np.ndarray) -> tuple[float, float]:
    """Kurtosis and high-frequency energy ratio of the block DCT.

    Returns (kurtosis, high-frequency energy fraction). Synthesised content often
    has a different balance of high-frequency DCT energy than camera output.
    """
    height = gray.shape[0] - gray.shape[0] % 8
    width = gray.shape[1] - gray.shape[1] % 8
    if height < 8 or width < 8:
        return 0.0, 0.0

    cropped = np.float32(gray[:height, :width]) - 128.0

    blocks = cropped.reshape(height // 8, 8, width // 8, 8).transpose(0, 2, 1, 3)
    blocks = blocks.reshape(-1, 8, 8)

    # Cap the block count so a large upload cannot make this dominate latency.
    if blocks.shape[0] > 4096:
        step = blocks.shape[0] // 4096
        blocks = blocks[::step][:4096]

    transformed = np.stack([cv2.dct(block) for block in blocks])

    ac = transformed[:, 1:, 1:].ravel()
    if ac.size == 0 or ac.std() == 0:
        return 0.0, 0.0

    centred = ac - ac.mean()
    kurtosis = float((centred**4).mean() / (centred.var() ** 2))

    total = float(np.abs(transformed).sum())
    high = float(np.abs(transformed[:, 4:, 4:]).sum())
    ratio = high / total if total > 0 else 0.0

    return kurtosis, ratio


def noise_residual_inconsistency(image_bgr: np.ndarray) -> float:
    """Variation in noise energy across the frame.

    A single sensor imprints broadly consistent noise. Content composited from
    another source often carries a different noise floor, so the spread of
    residual energy across tiles is informative. This is a coarse stand-in for
    full PRNU correlation, which needs multiple images from the same camera and
    so cannot run on a single upload.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    residual = gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)

    tiles = 4
    height, width = residual.shape
    tile_h, tile_w = height // tiles, width // tiles
    if tile_h < 8 or tile_w < 8:
        return 0.0

    energies = [
        float(residual[r * tile_h : (r + 1) * tile_h, c * tile_w : (c + 1) * tile_w].var())
        for r in range(tiles)
        for c in range(tiles)
    ]

    mean_energy = float(np.mean(energies))
    if mean_energy <= 1e-6:
        return 0.0

    # Coefficient of variation, so the measure does not simply track how noisy
    # the image is overall.
    return float(np.std(energies) / mean_energy)


def jpeg_grid_strength(gray: np.ndarray) -> float:
    """Strength of the 8x8 block grid relative to off-grid positions.

    A single JPEG encode leaves a grid aligned to its own 8x8 lattice. Content
    pasted in and re-encoded, or resized after encoding, disturbs that alignment.
    Values near zero mean no detectable grid.
    """
    signal = gray.astype(np.float32)

    row_diff = np.abs(np.diff(signal, axis=0)).mean(axis=1)
    col_diff = np.abs(np.diff(signal, axis=1)).mean(axis=0)

    def contrast(diff: np.ndarray) -> float:
        if diff.size < 16:
            return 0.0
        on_grid = diff[7::8]
        mask = np.ones(diff.size, dtype=bool)
        mask[7::8] = False
        off_grid = diff[mask]
        if on_grid.size == 0 or off_grid.size == 0 or off_grid.mean() <= 1e-6:
            return 0.0
        return float(on_grid.mean() / off_grid.mean() - 1.0)

    return max(contrast(row_diff), contrast(col_diff))


def error_level_analysis(raw_bytes: bytes, quality: int = 90) -> np.ndarray | None:
    """Recompress and amplify the difference.

    Supporting visual only. ELA is included because it helps a human see where
    compression history differs across a frame, but it is notoriously
    over-interpreted, so it deliberately contributes nothing to the score.
    """
    try:
        with Image.open(io.BytesIO(raw_bytes)) as original:
            rgb = original.convert("RGB")
            buffer = io.BytesIO()
            rgb.save(buffer, "JPEG", quality=quality)
            buffer.seek(0)
            with Image.open(buffer) as recompressed:
                difference = np.abs(
                    np.asarray(rgb, dtype=np.int16)
                    - np.asarray(recompressed.convert("RGB"), dtype=np.int16)
                )
    except Exception:
        return None

    peak = difference.max()
    if peak == 0:
        return np.zeros_like(difference, dtype=np.uint8)

    amplified = (difference.astype(np.float32) * (255.0 / peak)).clip(0, 255)
    return amplified.astype(np.uint8)[:, :, ::-1]


def _render_spectrum_plot(profile: np.ndarray, output_dir: Path) -> Path:
    """Draw the radial spectrum as a simple line chart."""
    width, height, pad = 480, 240, 28
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)

    plot_w = width - 2 * pad
    plot_h = height - 2 * pad

    cv2.rectangle(canvas, (pad, pad), (width - pad, height - pad), (210, 210, 210), 1)

    points = [
        (
            pad + int(i / max(1, len(profile) - 1) * plot_w),
            height - pad - int(value * plot_h),
        )
        for i, value in enumerate(profile)
    ]
    for a, b in zip(points, points[1:], strict=False):
        cv2.line(canvas, a, b, (180, 90, 30), 2, cv2.LINE_AA)

    font = cv2.FONT_HERSHEY_SIMPLEX
    grey = (90, 90, 90)
    cv2.putText(canvas, "low freq", (pad, height - 8), font, 0.4, grey, 1, cv2.LINE_AA)
    cv2.putText(
        canvas, "high freq", (width - pad - 62, height - 8), font, 0.4, grey, 1, cv2.LINE_AA
    )
    cv2.putText(canvas, "radial power", (pad, 18), font, 0.45, (60, 60, 60), 1, cv2.LINE_AA)

    path = output_dir / f"spectrum_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(path), canvas)
    return path


# Thresholds below which a measurement reads as ordinary. Derived from the
# measured distribution over authentic images in the eval corpus, not guessed —
# see eval/reports/. They are conservative on purpose: this stream should not
# drive a verdict on its own.
_TAIL_IRREGULARITY_REF = 1.2
_NOISE_INCONSISTENCY_REF = 0.9
_GRID_STRENGTH_REF = 0.35


def analyze_frequency(
    image_bgr: np.ndarray,
    raw_bytes: bytes | None = None,
    output_dir: Path | None = None,
    render_plot: bool = True,
) -> FrequencyResult:
    settings = get_settings()
    output_dir = output_dir or settings.artifact_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    profile = azimuthal_power_spectrum(gray)
    irregularity = spectral_tail_irregularity(profile)
    kurtosis, high_ratio = dct_coefficient_stats(gray)
    noise_spread = noise_residual_inconsistency(image_bgr)
    grid = jpeg_grid_strength(gray)

    measurements = {
        "spectral_tail_irregularity": round(irregularity, 4),
        "dct_ac_kurtosis": round(kurtosis, 4),
        "dct_high_freq_ratio": round(high_ratio, 4),
        "noise_residual_inconsistency": round(noise_spread, 4),
        "jpeg_grid_strength": round(grid, 4),
    }

    # Each component is squashed into [0, 1] against its reference level, then
    # averaged. Equal weighting within the stream is deliberate: we have no
    # per-component validation data to justify anything else, and inventing
    # weights would be exactly the hand-picking the architecture forbids.
    components = [
        min(1.0, irregularity / _TAIL_IRREGULARITY_REF),
        min(1.0, noise_spread / _NOISE_INCONSISTENCY_REF),
        min(1.0, grid / _GRID_STRENGTH_REF),
    ]
    score = float(np.clip(np.mean(components), 0.0, 1.0))

    notes: list[str] = []
    if irregularity > _TAIL_IRREGULARITY_REF:
        notes.append(
            f"The high-frequency tail of the spectrum is irregular ({irregularity:.2f}), "
            "which can indicate resampling from a generative upsampling stack."
        )
    if noise_spread > _NOISE_INCONSISTENCY_REF:
        notes.append(
            f"Noise energy varies unevenly across the frame ({noise_spread:.2f}), which "
            "can happen when content from a different source is composited in."
        )
    if grid > _GRID_STRENGTH_REF:
        notes.append(
            f"A JPEG block grid is unusually pronounced ({grid:.2f}), which can indicate "
            "recompression after editing."
        )
    if not notes:
        notes.append("No unusual frequency-domain structure was measured.")

    plot_path = _render_spectrum_plot(profile, output_dir) if render_plot else None

    return FrequencyResult(
        score=round(score, 4),
        measurements=measurements,
        notes=notes,
        spectrum_plot=plot_path,
    )
