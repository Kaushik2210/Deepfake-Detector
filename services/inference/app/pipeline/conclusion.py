"""Plain-language summary of a report.

This is the part most readers will actually read, which makes it the easiest
place to accidentally imply a verdict. Rules it follows:

- Never asserts an image is fake or genuine, however strong the signals.
- Says what was measured and how many faces, not what happened to them.
- States the limitation that applies to *this* result, not a generic warning.
- Tells the reader what to do next, since "0.68" on its own is not actionable.

The wording is assembled from templates rather than generated, so it can be
tested and cannot drift into overclaiming.
"""

from __future__ import annotations

from app.bands import score_to_band
from app.pipeline.aggregate import Aggregation


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _headline(aggregation: Aggregation, score: float) -> str:
    band = score_to_band(score)
    count = aggregation.faces_analyzed
    elevated = aggregation.faces_elevated

    if count == 0:
        return "No face was found, so no analysis could run"

    if count == 1:
        return f"{band.label.lower().capitalize()} of manipulation on the single face found"

    if elevated == 0:
        return f"No manipulation signals on any of the {count} faces"

    if elevated == count:
        return f"All {count} faces show similar signals"

    return (
        f"{elevated} of {count} {_plural(elevated, 'face')} "
        f"{_plural(elevated, 'shows', 'show')} signals worth reviewing"
    )


def _detail(aggregation: Aggregation, score: float) -> str:
    band = score_to_band(score)
    count = aggregation.faces_analyzed
    elevated = aggregation.faces_elevated
    pattern = aggregation.pattern

    if count == 0:
        return (
            "The detector works by analysing faces, and it could not find one in this "
            "image. That means there was nothing for it to examine — not that the image "
            "was checked and found clean."
        )

    if pattern == "single_face":
        return (
            f"One face was found and analysed. The detector rates it "
            f"“{band.label.lower()}”: {band.copy.lower()}. The highlighted "
            "areas in the heatmap are the regions that most influenced that rating."
        )

    if pattern == "none_elevated":
        return (
            f"All {count} faces were analysed individually and none of them showed "
            "signals the detector considers notable. Bear in mind this only means "
            "nothing was detected — detectors miss manipulations they were not trained "
            "to recognise, particularly from newer tools."
        )

    if pattern == "single_outlier":
        return (
            f"Of the {count} faces analysed, one scored noticeably higher than the rest. "
            "A single face standing out is the pattern face-swapping tends to leave, so "
            "it is worth a look. It is also, though, the pattern you get by chance when "
            "several faces are each tested: more faces means more opportunities for one "
            "to score high for no meaningful reason. The confidence in this result has "
            "been reduced to reflect that."
        )

    if pattern == "all_elevated":
        return (
            f"Every one of the {count} faces scored similarly high. That is usually less "
            "interesting than it sounds. When a detector reacts the same way to every "
            "face in an image, the cause is more often something affecting the whole "
            "picture — it may be entirely AI-generated, heavily filtered, or compressed "
            "in an unusual way — than each person being edited separately."
        )

    return (
        f"Of the {count} faces analysed, {elevated} scored high enough to be worth "
        "reviewing and the rest did not. Mixed results like this are genuinely "
        "ambiguous: they can indicate that specific people were edited into an "
        "otherwise ordinary photo, or simply that some faces are smaller, blurrier or "
        "more awkwardly lit than others. The per-face details below show which is which."
    )


def _next_steps(aggregation: Aggregation, score: float) -> str:
    count = aggregation.faces_analyzed
    elevated = aggregation.faces_elevated

    if count == 0:
        return (
            "If you expected a face in this image, try a version where the face is "
            "larger and more clearly visible. Otherwise this tool cannot tell you "
            "anything about this file."
        )

    if elevated == 0:
        return (
            "Nothing here needs your attention on the strength of this analysis alone. "
            "If you have another reason to doubt the image, check where it came from — "
            "provenance is far more reliable than any statistical detector."
        )

    highlighted = (
        "the highlighted face" if elevated == 1 else f"the {elevated} highlighted faces"
    )
    return (
        f"Look at {highlighted} yourself, using the heatmap to see which regions drove "
        "the score. Then check the image's origin: who published it, when, and whether "
        "an earlier version exists. A confirmed source settles the question in a way "
        "this score cannot."
    )


def build_conclusion(aggregation: Aggregation, score: float) -> dict:
    return {
        "headline": _headline(aggregation, score),
        "detail": _detail(aggregation, score),
        "next_steps": _next_steps(aggregation, score),
        "pattern": aggregation.pattern,
        "faces_analyzed": aggregation.faces_analyzed,
        "faces_elevated": aggregation.faces_elevated,
    }


def build_no_face_conclusion() -> dict:
    empty = Aggregation(
        score=0.5,
        spread=0.0,
        pattern="none_elevated",
        faces_analyzed=0,
        faces_elevated=0,
        penalties=[],
    )
    return {
        "headline": _headline(empty, 0.5),
        "detail": _detail(empty, 0.5),
        "next_steps": _next_steps(empty, 0.5),
        "pattern": "none_elevated",
        "faces_analyzed": 0,
        "faces_elevated": 0,
    }
