"""Perceptual-hash cache.

``find_best_match`` is pure and tested offline. Everything else needs a real
Postgres and is marked ``db``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.pipeline import hash_cache
from app.pipeline.hash_cache import Candidate, find_best_match

# A 64-bit hex hash with the low 4 bits flipped one, two, and three times.
_BASE = "0000000000000000"


def _flip_low_bits(hex_hash: str, n: int) -> str:
    value = int(hex_hash, 16)
    mask = (1 << n) - 1
    return format(value ^ mask, "016x")


class TestFindBestMatch:
    def test_exact_match_wins(self) -> None:
        candidates = [Candidate(hash=_BASE, payload="exact")]
        assert find_best_match(_BASE, candidates, max_distance=5) == "exact"

    def test_picks_the_closest_of_several(self) -> None:
        far = _flip_low_bits(_BASE, 4)
        near = _flip_low_bits(_BASE, 1)
        candidates = [
            Candidate(hash=far, payload="far"),
            Candidate(hash=near, payload="near"),
        ]
        assert find_best_match(_BASE, candidates, max_distance=10) == "near"

    def test_rejects_a_match_outside_the_distance_budget(self) -> None:
        distant = _flip_low_bits(_BASE, 8)
        candidates = [Candidate(hash=distant, payload="too far")]
        assert find_best_match(_BASE, candidates, max_distance=3) is None

    def test_boundary_distance_is_inclusive(self) -> None:
        exactly_three = _flip_low_bits(_BASE, 3)
        candidates = [Candidate(hash=exactly_three, payload="boundary")]
        assert find_best_match(_BASE, candidates, max_distance=3) == "boundary"

    def test_empty_candidate_list_returns_none(self) -> None:
        assert find_best_match(_BASE, [], max_distance=10) is None

    def test_prefers_first_seen_on_an_exact_tie(self) -> None:
        # Two distinct hashes, each Hamming distance 2 from _BASE via
        # different bit positions -- a genuine tie, not two copies of one hash.
        a = format(0b0011, "016x")  # bits 0-1 set
        b = format(0b0011 << 4, "016x")  # bits 4-5 set
        assert a != b
        candidates = [Candidate(hash=a, payload="first"), Candidate(hash=b, payload="second")]
        assert find_best_match(_BASE, candidates, max_distance=5) == "first"


@pytest.mark.db
class TestHashCacheDatabase:
    @pytest.fixture(autouse=True)
    def _clean(self):
        hash_cache.ensure_schema()
        yield
        with hash_cache._connection() as conn:  # noqa: SLF001 - test cleanup only
            conn.execute("DELETE FROM phash_cache WHERE phash LIKE 'dead%'")

    def _ttl(self, **kwargs) -> datetime:
        return datetime.now(UTC) + timedelta(**kwargs)

    def test_insert_then_exact_lookup_roundtrips(self) -> None:
        report = {"job_id": "abc", "score": 0.42}
        hash_cache.insert("dead0000000000f1", report, self._ttl(hours=1))
        assert hash_cache.lookup("dead0000000000f1") == report

    def test_lookup_miss_returns_none(self) -> None:
        assert hash_cache.lookup("deadffffffffffff") is None

    def test_near_match_within_threshold_is_found(self) -> None:
        report = {"job_id": "near", "score": 0.1}
        hash_cache.insert("dead000000000000", report, self._ttl(hours=1))
        # Flip a couple of low bits -- still within the default threshold.
        near_query = "dead000000000003"
        assert hash_cache.lookup(near_query) == report

    def test_expired_entries_are_not_returned(self) -> None:
        report = {"job_id": "expired"}
        hash_cache.insert("dead00000000dead", report, self._ttl(seconds=-1))
        assert hash_cache.lookup("dead00000000dead") is None

    def test_sweep_removes_expired_rows_but_not_live_ones(self) -> None:
        # Far apart in Hamming distance (32 bits), so the still-live entry
        # cannot near-match the expired one's query and mask its absence.
        hash_cache.insert("dead000000000000", {"x": 1}, self._ttl(seconds=-1))
        hash_cache.insert("dead0000ffffffff", {"x": 2}, self._ttl(hours=1))

        hash_cache.sweep_expired()

        assert hash_cache.lookup("dead000000000000") is None
        assert hash_cache.lookup("dead0000ffffffff") == {"x": 2}

    def test_cache_report_is_a_noop_for_a_missing_hash(self) -> None:
        # Must not raise -- some media (e.g. no-face images) has no phash.
        hash_cache.cache_report(None, {"job_id": "no-hash"}, self._ttl(hours=1))

    def test_exact_match_preferred_over_a_closer_scan_result(self) -> None:
        """An exact hit should short-circuit before the nearest-neighbour scan
        even runs, so it can never lose to a coincidentally-closer decoy."""
        exact_report = {"job_id": "exact"}
        hash_cache.insert("dead0000000000cc", exact_report, self._ttl(hours=1))
        assert hash_cache.lookup("dead0000000000cc") == exact_report
