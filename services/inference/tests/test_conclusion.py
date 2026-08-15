"""The plain-language conclusion.

The conclusion is the part a non-technical reader actually reads, which makes it
the easiest place to accidentally state a verdict. These tests guard that.
"""

from __future__ import annotations

import pytest

from app.pipeline.aggregate import aggregate
from app.pipeline.conclusion import build_conclusion, build_no_face_conclusion

# Verdict constructions, not bare words. "A confirmed source" is fine — it is
# advice about checking provenance; "confirmed fake" is not.
_FORBIDDEN = (
    "is fake",
    "is real",
    "is genuine",
    "is authentic",
    "is a deepfake",
    "was manipulated",
    "has been manipulated",
    "confirmed fake",
    "confirmed manipulation",
    "definitely",
    "proves",
    "proof that",
    "we can confirm",
)


def _conclude(scores: list[float], score: float | None = None) -> dict:
    aggregation = aggregate(scores, [0.01] * len(scores))
    return build_conclusion(aggregation, score if score is not None else aggregation.score)


def _all_text(conclusion: dict) -> str:
    return " ".join(
        [conclusion["headline"], conclusion["detail"], conclusion["next_steps"]]
    ).lower()


@pytest.mark.parametrize(
    "scores",
    [
        [0.05],
        [0.95],
        [0.1, 0.2, 0.3],
        [0.1, 0.1, 0.1, 0.95],
        [0.8, 0.82, 0.79, 0.85],
        [0.9, 0.88, 0.1, 0.12],
    ],
)
def test_never_states_a_verdict(scores: list[float]) -> None:
    text = _all_text(_conclude(scores))
    for phrase in _FORBIDDEN:
        assert phrase not in text, f"conclusion asserted {phrase!r}: {text}"


@pytest.mark.parametrize(
    "scores",
    [[0.05], [0.95], [0.1, 0.2], [0.1, 0.1, 0.95], [0.8, 0.82, 0.79]],
)
def test_every_field_is_populated(scores: list[float]) -> None:
    conclusion = _conclude(scores)
    for field in ("headline", "detail", "next_steps"):
        assert len(conclusion[field]) > 25, f"{field} is too thin to be useful"


def test_counts_are_reported_accurately() -> None:
    conclusion = _conclude([0.9, 0.88, 0.1, 0.12])
    assert conclusion["faces_analyzed"] == 4
    assert conclusion["faces_elevated"] == 2
    assert "2 of 4" in conclusion["headline"]


def test_lone_outlier_explains_the_multiplicity_caveat() -> None:
    """A reader must be told why one face standing out is weaker than it looks."""
    conclusion = _conclude([0.1, 0.1, 0.1, 0.1, 0.95])

    assert conclusion["pattern"] == "single_outlier"
    detail = conclusion["detail"].lower()
    assert "chance" in detail
    assert "more faces" in detail or "several faces" in detail


def test_all_elevated_points_at_a_whole_image_cause() -> None:
    conclusion = _conclude([0.8, 0.82, 0.79, 0.85])

    assert conclusion["pattern"] == "all_elevated"
    detail = conclusion["detail"].lower()
    assert "whole picture" in detail or "whole image" in detail
    assert "ai-generated" in detail or "compressed" in detail


def test_clean_result_does_not_claim_the_image_is_safe() -> None:
    """Principle 3: 'nothing detected' is not 'nothing there'."""
    conclusion = _conclude([0.05, 0.08, 0.1])
    detail = conclusion["detail"].lower()

    assert "miss" in detail or "only means nothing was detected" in detail


def test_no_face_says_it_could_not_look() -> None:
    conclusion = build_no_face_conclusion()

    assert conclusion["faces_analyzed"] == 0
    detail = conclusion["detail"].lower()
    assert "could not find" in detail
    assert "not that the image was checked and found clean" in detail


def test_next_steps_point_at_provenance() -> None:
    """Provenance beats any statistical detector, and the advice should say so."""
    for scores in ([0.95], [0.1, 0.1, 0.95], [0.05, 0.08]):
        assert "origin" in _conclude(scores)["next_steps"].lower() or (
            "came from" in _conclude(scores)["next_steps"].lower()
        )


def test_singular_and_plural_read_correctly() -> None:
    single = _conclude([0.1, 0.1, 0.1, 0.95])["headline"]
    assert "1 of 4 face shows" in single

    multiple = _conclude([0.9, 0.88, 0.1, 0.12])["headline"]
    assert "2 of 4 faces show" in multiple
