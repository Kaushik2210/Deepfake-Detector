"""Combining per-face scores into one image-level result.

The naive approach — report the highest face score — has a statistical problem
that gets worse exactly where this feature is aimed. Every face tested is another
chance to produce a high score by accident, so an eight-person group photo has
many more opportunities to throw one than a portrait does. Reporting the maximum
without adjustment would make group photos score systematically higher than solo
photos for reasons that have nothing to do with manipulation.

This module keeps the maximum as the headline (one manipulated face does mean
the image is manipulated) but treats a lone outlier among many faces as weaker
evidence than the same score on its own, and distinguishes that case from the
one where every face is elevated — which usually points at something about the
whole image rather than at the individual people in it.
"""

from __future__ import annotations

from dataclasses import dataclass

# A face at or above this score is "elevated" — the bottom of the "Mixed
# signals" band, i.e. the point where the report stops saying "likely benign".
ELEVATED_THRESHOLD = 0.45

# Where "every face looks alike" starts being more plausible as a whole-image
# property than as several independent manipulations.
_GLOBAL_CAUSE_MIN_FACES = 3


@dataclass(frozen=True)
class Aggregation:
    score: float
    spread: float
    pattern: str
    faces_analyzed: int
    faces_elevated: int
    penalties: list[tuple[str, float]]


def _multiplicity_factor(face_count: int) -> float:
    """Confidence multiplier for a single elevated face among several.

    Shrinks as more faces are tested, because more tests mean more chances for
    one to come back high by accident. Deliberately gentle — it should temper a
    lone reading, not erase it — and floored so a crowd scene never drives the
    signal to nothing.
    """
    return max(0.55, 1.0 / (1.0 + 0.09 * (face_count - 1)))


def aggregate(face_scores: list[float], face_spreads: list[float]) -> Aggregation:
    if not face_scores:
        raise ValueError("cannot aggregate an empty list of face scores")

    count = len(face_scores)
    top_index = max(range(count), key=lambda i: face_scores[i])
    top_score = face_scores[top_index]
    elevated = sum(1 for s in face_scores if s >= ELEVATED_THRESHOLD)

    penalties: list[tuple[str, float]] = []

    if count == 1:
        pattern = "single_face"
    elif elevated == 0:
        pattern = "none_elevated"
    elif elevated == count and count >= _GLOBAL_CAUSE_MIN_FACES:
        pattern = "all_elevated"
        penalties.append(
            (
                f"All {count} faces scored similarly high. When every face in an image "
                "looks alike to the detector, that more often reflects something about "
                "the whole image — how it was generated, compressed, or edited — than "
                "manipulation of each person separately.",
                0.85,
            )
        )
    elif elevated == 1:
        pattern = "single_outlier"
        factor = _multiplicity_factor(count)
        penalties.append(
            (
                f"One face out of {count} stands out. Testing several faces gives "
                "several chances for one to score high by coincidence, so a single "
                "outlier in a group photo is weaker evidence than the same score would "
                "be on a photo of one person.",
                round(factor, 3),
            )
        )
    else:
        pattern = "several_elevated"

    return Aggregation(
        score=top_score,
        spread=face_spreads[top_index],
        pattern=pattern,
        faces_analyzed=count,
        faces_elevated=elevated,
        penalties=penalties,
    )
