"""Band mapping, including parity with the TypeScript implementation.

The boundary cases here deliberately mirror ``packages/core/src/__tests__/bands.test.ts``.
If the two ever disagree, the same score would be labelled differently in the API
and in the UI, which is the exact failure this table exists to prevent.
"""

from __future__ import annotations

import json

import pytest

from app.bands import (
    _locate_bands_json,
    band_definitions,
    report_footer_disclaimer,
    score_to_band,
)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.1, "low"),
        (0.3, "weak"),
        (0.5, "mixed"),
        (0.8, "strong"),
        (0.95, "very_strong"),
    ],
)
def test_midpoints_map_to_expected_band(score: float, expected: str) -> None:
    assert score_to_band(score).id == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.2, "weak"),
        (0.45, "mixed"),
        (0.7, "strong"),
        (0.88, "very_strong"),
    ],
)
def test_lower_bounds_are_inclusive(score: float, expected: str) -> None:
    """A score exactly on a boundary belongs to the higher band, matching the TS side."""
    assert score_to_band(score).id == expected


def test_extremes() -> None:
    assert score_to_band(0.0).id == "low"
    assert score_to_band(1.0).id == "very_strong"


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan")])
def test_rejects_out_of_range(score: float) -> None:
    with pytest.raises(ValueError):
        score_to_band(score)


def test_bands_cover_unit_interval_without_gaps() -> None:
    bands = sorted(band_definitions(), key=lambda b: b.min)
    assert bands[0].min == 0.0
    assert bands[-1].max == 1.0
    for previous, current in zip(bands, bands[1:], strict=False):
        assert current.min == previous.max


def test_python_matches_canonical_json_exactly() -> None:
    """Python must not drift from the file the TypeScript side reads."""
    data = json.loads(_locate_bands_json().read_text(encoding="utf-8"))

    assert [b["id"] for b in data["bands"]] == [b.id for b in band_definitions()]
    for raw, band in zip(data["bands"], band_definitions(), strict=True):
        assert (raw["min"], raw["max"]) == (band.min, band.max)
        assert (raw["label"], raw["copy"]) == (band.label, band.copy)

    assert data["report_footer_disclaimer"] == report_footer_disclaimer()


def test_no_band_label_implies_a_binary_verdict() -> None:
    """Principle 1: no band may read as a FAKE/REAL determination."""
    forbidden = {"fake", "real", "authentic", "genuine", "verdict"}
    for band in band_definitions():
        words = set(band.label.lower().replace("-", " ").split())
        assert not (words & forbidden), f"band {band.id} label reads as a verdict"
