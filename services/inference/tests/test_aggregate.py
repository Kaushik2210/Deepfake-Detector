"""Multi-face aggregation, especially the multiple-comparisons handling."""

from __future__ import annotations

import pytest

from app.pipeline.aggregate import ELEVATED_THRESHOLD, aggregate


def _agg(scores: list[float]):
    return aggregate(scores, [0.01] * len(scores))


def test_single_face_has_no_pattern() -> None:
    result = _agg([0.9])
    assert result.pattern == "single_face"
    assert result.penalties == []


def test_score_is_the_maximum() -> None:
    assert _agg([0.1, 0.8, 0.3]).score == 0.8


def test_spread_follows_the_top_face() -> None:
    result = aggregate([0.2, 0.9], [0.05, 0.42])
    assert result.spread == 0.42


def test_nothing_elevated() -> None:
    result = _agg([0.1, 0.2, 0.3])
    assert result.pattern == "none_elevated"
    assert result.faces_elevated == 0
    assert result.penalties == []


def test_lone_outlier_is_penalised() -> None:
    """The core multiple-comparisons case this module exists for."""
    result = _agg([0.05, 0.08, 0.10, 0.12, 0.95])

    assert result.pattern == "single_outlier"
    assert result.faces_elevated == 1
    assert len(result.penalties) == 1

    reason, factor = result.penalties[0]
    assert factor < 1.0
    assert "coincidence" in reason


def test_outlier_penalty_grows_with_face_count() -> None:
    """More faces tested means more chances for a spurious high score."""
    _, few = _agg([0.1, 0.9]).penalties[0]
    _, many = _agg([0.1] * 9 + [0.9]).penalties[0]

    assert many < few


def test_outlier_penalty_is_floored() -> None:
    """A crowd scene must not drive a real signal to nothing."""
    _, factor = _agg([0.1] * 40 + [0.9]).penalties[0]
    assert factor >= 0.55


def test_solo_high_score_is_not_penalised_for_multiplicity() -> None:
    """A portrait has only one test, so there is no multiplicity to correct."""
    assert _agg([0.95]).penalties == []


def test_all_elevated_suggests_a_whole_image_cause() -> None:
    result = _agg([0.8, 0.82, 0.79, 0.85])

    assert result.pattern == "all_elevated"
    reason, _ = result.penalties[0]
    assert "whole image" in reason


def test_two_elevated_faces_is_neither_pattern() -> None:
    result = _agg([0.9, 0.88, 0.1, 0.12])
    assert result.pattern == "several_elevated"
    assert result.faces_elevated == 2
    assert result.penalties == []


def test_all_elevated_needs_at_least_three_faces() -> None:
    """Two faces both scoring high is too small a sample to call a global cause."""
    assert _agg([0.9, 0.88]).pattern == "several_elevated"


def test_elevated_threshold_is_the_band_boundary() -> None:
    """Elevation starts where the bands stop saying 'likely benign'."""
    assert ELEVATED_THRESHOLD == 0.45
    assert _agg([0.44, 0.1, 0.1]).faces_elevated == 0
    assert _agg([0.45, 0.1, 0.1]).faces_elevated == 1


def test_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        aggregate([], [])
