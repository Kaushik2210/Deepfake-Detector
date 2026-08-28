"""BK-tree nearest-neighbour search. Pure and offline -- no DB needed."""

from __future__ import annotations

import random

import pytest

from app.pipeline.bktree import BKTree
from app.pipeline.phash import hamming_distance


def _flip_bits(hex_hash: str, n_bits: int, rng: random.Random) -> str:
    value = int(hex_hash, 16)
    bit_width = len(hex_hash) * 4
    positions = rng.sample(range(bit_width), n_bits)
    for pos in positions:
        value ^= 1 << pos
    return format(value, f"0{len(hex_hash)}x")


@pytest.fixture
def tree() -> BKTree[str]:
    return BKTree(hamming_distance)


class TestInsertAndQuery:
    def test_empty_tree_returns_nothing(self, tree: BKTree[str]) -> None:
        assert tree.query("0" * 16, max_distance=5) == []
        assert tree.query_nearest("0" * 16, max_distance=5) is None

    def test_finds_an_exact_match(self, tree: BKTree[str]) -> None:
        tree.insert("0" * 16, "exact")
        assert tree.query_nearest("0" * 16, max_distance=0) == "exact"

    def test_finds_a_near_match_within_budget(self, tree: BKTree[str]) -> None:
        rng = random.Random(0)
        base = "0" * 16
        near = _flip_bits(base, 2, rng)
        tree.insert(near, "near")
        assert tree.query_nearest(base, max_distance=5) == "near"

    def test_rejects_a_match_outside_the_distance_budget(self, tree: BKTree[str]) -> None:
        rng = random.Random(0)
        base = "0" * 16
        far = _flip_bits(base, 20, rng)
        tree.insert(far, "far")
        assert tree.query_nearest(base, max_distance=5) is None

    def test_picks_the_closest_of_several_candidates(self, tree: BKTree[str]) -> None:
        rng = random.Random(1)
        base = "0" * 16
        tree.insert(_flip_bits(base, 4, rng), "far")
        tree.insert(_flip_bits(base, 1, rng), "near")
        tree.insert(_flip_bits(base, 8, rng), "farther")
        assert tree.query_nearest(base, max_distance=10) == "near"

    def test_a_duplicate_key_overwrites_rather_than_growing_unreachably(
        self, tree: BKTree[str]
    ) -> None:
        tree.insert("0" * 16, "first")
        tree.insert("0" * 16, "second")
        assert len(tree) == 1
        assert tree.query_nearest("0" * 16, max_distance=0) == "second"

    def test_len_tracks_distinct_insertions(self, tree: BKTree[str]) -> None:
        rng = random.Random(2)
        base = "0" * 16
        for _ in range(10):
            tree.insert(_flip_bits(base, rng.randint(1, 30), rng), "x")
        assert len(tree) == 10


class TestAgainstLinearScan:
    """The tree must find exactly what a linear scan would, just faster."""

    def test_matches_linear_scan_on_a_random_population(self, tree: BKTree[str]) -> None:
        rng = random.Random(42)
        population: list[tuple[str, str]] = []
        for i in range(200):
            key = format(rng.getrandbits(64), "016x")
            payload = f"item-{i}"
            population.append((key, payload))
            tree.insert(key, payload)

        for _ in range(20):
            query = format(rng.getrandbits(64), "016x")
            max_distance = rng.choice([2, 5, 10, 15])

            linear_best: str | None = None
            linear_best_distance = max_distance + 1
            for key, payload in population:
                distance = hamming_distance(query, key)
                if distance < linear_best_distance:
                    linear_best_distance = distance
                    linear_best = payload

            tree_best = tree.query_nearest(query, max_distance)
            expected = linear_best if linear_best_distance <= max_distance else None
            assert tree_best == expected
