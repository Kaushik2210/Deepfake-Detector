"""Stratified splitting of an already-scored sample pool into two disjoint halves.

Used to carve the reporting corpus into a weight-selection validation half and a
final held-out half -- see DECISIONS.md, "Fusion weights derived from a genuine
cross-dataset validation split". Ordinary index slicing would work about as well
whenever the upstream loader already shuffles (both dataset loaders do), but
stratifying by label removes that assumption: a run stays balanced even if a
future loader ever emits samples in label-grouped blocks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def stratified_half_split(
    items: list[T], label_fn: Callable[[T], int], fraction: float = 0.5
) -> tuple[list[T], list[T]]:
    """Split `items` into (first, second) shares, `fraction` in the first, per label.

    Each label's own items are cut at `fraction` independently, so both outputs
    keep the same class balance as the input -- disjoint by construction, since
    every item lands in exactly one of the two lists.
    """
    by_label: dict[int, list[T]] = {}
    for item in items:
        by_label.setdefault(label_fn(item), []).append(item)

    first: list[T] = []
    second: list[T] = []
    for group in by_label.values():
        cut = round(len(group) * fraction)
        first.extend(group[:cut])
        second.extend(group[cut:])

    return first, second
