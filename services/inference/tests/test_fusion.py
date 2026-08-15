"""Weighted fusion and the provenance override path."""

from __future__ import annotations

import pytest

from app.pipeline import fusion
from app.pipeline.fusion import StreamInput, fuse


@pytest.fixture(autouse=True)
def _clear_calibration_cache():
    fusion.load_calibration.cache_clear()
    yield
    fusion.load_calibration.cache_clear()


@pytest.fixture
def fitted_weights(monkeypatch):
    """Pretend the eval harness has fitted weights."""
    monkeypatch.setattr(fusion, "stream_weights", lambda: {"spatial": 0.7, "frequency": 0.3})
    monkeypatch.setattr(fusion, "temperatures", lambda: {})


def test_no_streams_is_uninformative() -> None:
    result = fuse([StreamInput("spatial", 0.9, available=False)])
    assert result.score == 0.5
    assert "uninformative" in result.notes[0].lower()


def test_weighted_average_uses_fitted_weights(fitted_weights) -> None:
    result = fuse([StreamInput("spatial", 1.0), StreamInput("frequency", 0.0)])
    assert result.score == pytest.approx(0.7, abs=1e-6)
    assert result.weights_used == {"spatial": 0.7, "frequency": 0.3}


def test_weights_renormalise_when_a_stream_is_missing(fitted_weights) -> None:
    """Dropping a stream must not silently shrink the total weight."""
    result = fuse([StreamInput("spatial", 0.8)])
    assert result.weights_used == {"spatial": 1.0}
    assert result.score == pytest.approx(0.8, abs=1e-6)


def test_falls_back_to_one_stream_when_no_weights_are_fitted(monkeypatch) -> None:
    """An unfitted product must not invent a weighting."""
    monkeypatch.setattr(fusion, "stream_weights", lambda: {})

    result = fuse([StreamInput("spatial", 0.8), StreamInput("frequency", 0.2)])

    assert result.score == 0.8
    assert len(result.weights_used) == 1
    assert "invented" in result.notes[0]


def test_zero_weighted_stream_does_not_contribute(monkeypatch) -> None:
    """A stream measured at chance is excluded, not quietly averaged in."""
    monkeypatch.setattr(fusion, "stream_weights", lambda: {"spatial": 1.0, "frequency": 0.0})
    monkeypatch.setattr(fusion, "temperatures", lambda: {})

    result = fuse([StreamInput("spatial", 0.9), StreamInput("frequency", 0.1)])

    assert result.score == pytest.approx(0.9, abs=1e-6)
    assert "frequency" not in result.weights_used


def test_disagreement_reflects_spread(fitted_weights) -> None:
    agree = fuse([StreamInput("spatial", 0.8), StreamInput("frequency", 0.8)])
    disagree = fuse([StreamInput("spatial", 0.9), StreamInput("frequency", 0.1)])

    assert agree.disagreement == pytest.approx(0.0, abs=1e-9)
    assert disagree.disagreement > 0.3


class TestProvenanceOverride:
    def test_generator_metadata_floors_the_score(self, fitted_weights) -> None:
        result = fuse(
            [StreamInput("spatial", 0.1), StreamInput("frequency", 0.1)],
            generator_marker="Stable Diffusion",
        )

        assert result.score >= 0.88
        assert result.override_applied == "generator_metadata"
        assert "Stable Diffusion" in result.notes[-1]

    def test_generator_floor_never_lowers_a_higher_score(self, fitted_weights) -> None:
        result = fuse(
            [StreamInput("spatial", 0.97), StreamInput("frequency", 0.97)],
            generator_marker="Midjourney",
        )
        assert result.score == pytest.approx(0.97, abs=1e-6)

    def test_generator_floor_stops_short_of_certainty(self, fitted_weights) -> None:
        """Removable metadata must not produce a maximal score."""
        result = fuse([StreamInput("spatial", 0.0)], generator_marker="DALL·E")
        assert result.score < 1.0

    def test_valid_c2pa_clamps_the_score(self, fitted_weights) -> None:
        result = fuse(
            [StreamInput("spatial", 0.9), StreamInput("frequency", 0.9)],
            c2pa_valid=True,
            c2pa_signer="Example News",
        )

        assert result.score <= 0.35
        assert result.override_applied == "c2pa_valid"
        assert "Example News" in result.notes[-1]

    def test_c2pa_clamp_does_not_clear_the_score(self, fitted_weights) -> None:
        """A signature attests to a chain, not to the content being unaltered."""
        result = fuse([StreamInput("spatial", 0.99)], c2pa_valid=True)
        assert result.score > 0.0

    def test_c2pa_never_raises_an_already_low_score(self, fitted_weights) -> None:
        result = fuse([StreamInput("spatial", 0.05)], c2pa_valid=True)
        assert result.score == pytest.approx(0.05, abs=1e-6)

    def test_generator_marker_takes_precedence_over_c2pa(self, fitted_weights) -> None:
        """Self-identified generation is the more specific claim."""
        result = fuse(
            [StreamInput("spatial", 0.5)],
            generator_marker="Stable Diffusion",
            c2pa_valid=True,
        )
        assert result.override_applied == "generator_metadata"
        assert result.score >= 0.88


class TestTemperature:
    def test_temperature_above_one_softens(self) -> None:
        assert fusion.apply_temperature(0.95, 3.0) < 0.95

    def test_temperature_below_one_sharpens(self) -> None:
        assert fusion.apply_temperature(0.95, 0.5) > 0.95

    def test_temperature_preserves_the_midpoint(self) -> None:
        for temperature in (0.3, 1.0, 4.0):
            assert fusion.apply_temperature(0.5, temperature) == pytest.approx(0.5, abs=1e-9)

    def test_temperature_preserves_ranking(self) -> None:
        """Calibration changes confidence, never which sample scores higher."""
        scores = [0.1, 0.3, 0.6, 0.9]
        scaled = [fusion.apply_temperature(s, 2.5) for s in scores]
        assert scaled == sorted(scaled)

    def test_missing_temperature_leaves_the_score_untouched(self, monkeypatch) -> None:
        monkeypatch.setattr(fusion, "temperatures", lambda: {})
        score, applied = fusion.calibrate_stream("spatial", 0.77)
        assert score == 0.77
        assert applied is False
