"""Stream B (frequency) and Stream D (provenance)."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from app.pipeline.frequency import (
    analyze_frequency,
    azimuthal_power_spectrum,
    error_level_analysis,
    jpeg_grid_strength,
    noise_residual_inconsistency,
)
from app.pipeline.provenance import analyze_provenance


class TestFrequency:
    def test_score_is_a_probability(self, real_face_bgr: np.ndarray) -> None:
        result = analyze_frequency(real_face_bgr, render_plot=False)
        assert 0.0 <= result.score <= 1.0

    def test_reports_every_measurement_it_used(self, real_face_bgr: np.ndarray) -> None:
        result = analyze_frequency(real_face_bgr, render_plot=False)
        for key in (
            "spectral_tail_irregularity",
            "dct_ac_kurtosis",
            "noise_residual_inconsistency",
            "jpeg_grid_strength",
        ):
            assert key in result.measurements

    def test_always_explains_itself(self, real_face_bgr: np.ndarray) -> None:
        """Principle 2: a contributing score needs a stated reason."""
        result = analyze_frequency(real_face_bgr, render_plot=False)
        assert result.notes
        assert all(len(note) > 20 for note in result.notes)

    def test_renders_a_spectrum_plot(self, real_face_bgr: np.ndarray, tmp_path) -> None:
        result = analyze_frequency(real_face_bgr, output_dir=tmp_path, render_plot=True)
        assert result.spectrum_plot is not None
        assert result.spectrum_plot.is_file()

    def test_spectrum_profile_is_normalised_and_decreasing(
        self, real_face_bgr: np.ndarray
    ) -> None:
        gray = cv2.cvtColor(real_face_bgr, cv2.COLOR_BGR2GRAY)
        profile = azimuthal_power_spectrum(gray)

        assert profile.max() == pytest.approx(1.0, abs=1e-9)
        # A photograph's spectrum falls away from low to high frequency.
        assert profile[:8].mean() > profile[-8:].mean()

    def test_recompression_raises_the_block_grid_measure(
        self, real_face_bgr: np.ndarray
    ) -> None:
        """The measurement most directly tied to JPEG history."""
        gray = cv2.cvtColor(real_face_bgr, cv2.COLOR_BGR2GRAY)
        _, low = cv2.imencode(".jpg", real_face_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 15])
        degraded = cv2.cvtColor(cv2.imdecode(low, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)

        assert jpeg_grid_strength(degraded) > jpeg_grid_strength(gray)

    def test_noise_inconsistency_is_scale_free(self, real_face_bgr: np.ndarray) -> None:
        """Brightening must not by itself look like inconsistent noise."""
        brighter = np.clip(real_face_bgr.astype(np.int16) + 25, 0, 255).astype(np.uint8)

        base = noise_residual_inconsistency(real_face_bgr)
        assert noise_residual_inconsistency(brighter) == pytest.approx(base, abs=0.35)

    def test_handles_a_tiny_image_without_crashing(self) -> None:
        tiny = np.full((6, 6, 3), 120, dtype=np.uint8)
        result = analyze_frequency(tiny, render_plot=False)
        assert 0.0 <= result.score <= 1.0

    def test_ela_returns_an_image_for_jpeg(self, real_face_jpeg: bytes) -> None:
        ela = error_level_analysis(real_face_jpeg)
        assert ela is not None
        assert ela.ndim == 3

    def test_ela_does_not_contribute_to_the_score(self, real_face_bgr: np.ndarray) -> None:
        """ELA is a visual aid only; it is too unreliable to move a number."""
        with_bytes = analyze_frequency(real_face_bgr, b"not a real jpeg", render_plot=False)
        without = analyze_frequency(real_face_bgr, None, render_plot=False)
        assert with_bytes.score == without.score


class TestProvenance:
    def test_absent_credentials_are_not_treated_as_suspicious(
        self, real_face_jpeg: bytes
    ) -> None:
        result = analyze_provenance(real_face_jpeg, "image/jpeg")

        assert result.c2pa.present is False
        assert result.fired is False
        assert any("not itself suspicious" in note for note in result.notes)

    def test_detects_a_generator_that_names_itself(self, real_face_jpeg: bytes) -> None:
        image = Image.open(io.BytesIO(real_face_jpeg)).convert("RGB")
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Software", "Stable Diffusion v1.5")
        buffer = io.BytesIO()
        image.save(buffer, "PNG", pnginfo=meta)

        result = analyze_provenance(buffer.getvalue(), "image/png")

        assert result.generator_marker == "Stable Diffusion"
        assert result.fired is True

    def test_generator_note_states_that_absence_proves_nothing(
        self, real_face_jpeg: bytes
    ) -> None:
        image = Image.open(io.BytesIO(real_face_jpeg)).convert("RGB")
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Comment", "created with Midjourney")
        buffer = io.BytesIO()
        image.save(buffer, "PNG", pnginfo=meta)

        result = analyze_provenance(buffer.getvalue(), "image/png")
        assert any("absence" in note and "proves nothing" in note for note in result.notes)

    def test_editing_software_is_distinguished_from_manipulation(
        self, real_face_jpeg: bytes
    ) -> None:
        image = Image.open(io.BytesIO(real_face_jpeg)).convert("RGB")
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Software", "Adobe Photoshop 25.0")
        buffer = io.BytesIO()
        image.save(buffer, "PNG", pnginfo=meta)

        result = analyze_provenance(buffer.getvalue(), "image/png")

        assert result.editor_marker == "photoshop"
        assert result.generator_marker is None
        assert any("not manipulation" in note for note in result.notes)

    def test_never_claims_an_untrusted_signer_is_trusted(
        self, real_face_jpeg: bytes
    ) -> None:
        """We maintain no signer allow-list, so trust must report as unknown."""
        result = analyze_provenance(real_face_jpeg, "image/jpeg")
        assert result.c2pa.trusted_signer is None

    def test_survives_bytes_that_are_not_an_image(self) -> None:
        result = analyze_provenance(b"definitely not an image", "image/jpeg")
        assert result.c2pa.present is False
        assert result.notes
