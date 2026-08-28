"""Rate limiting and abuse-pattern logging. Needs a reachable Redis."""

from __future__ import annotations

import uuid

import pytest
import redis as redis_lib

from app.config import get_settings
from app.pipeline import rate_limit
from app.pipeline.rate_limit import RateLimitExceeded, enforce, note_phash_activity

pytestmark = pytest.mark.redis


def _reachable() -> bool:
    try:
        rate_limit._client().ping()
        return True
    except redis_lib.RedisError:
        return False


if not _reachable():
    pytest.skip("no reachable Redis at settings.redis_url", allow_module_level=True)


@pytest.fixture(autouse=True)
def _clear_cache():
    rate_limit._client.cache_clear()
    yield
    rate_limit._client.cache_clear()


class TestEnforce:
    def test_allows_requests_under_the_limit(self) -> None:
        scope, identifier = "test", uuid.uuid4().hex
        for _ in range(3):
            enforce(scope, identifier, limit=5, window_seconds=60)  # must not raise

    def test_raises_once_the_limit_is_exceeded(self) -> None:
        scope, identifier = "test", uuid.uuid4().hex
        for _ in range(3):
            enforce(scope, identifier, limit=3, window_seconds=60)

        with pytest.raises(RateLimitExceeded) as exc_info:
            enforce(scope, identifier, limit=3, window_seconds=60)

        assert exc_info.value.limit == 3
        assert exc_info.value.window_seconds == 60

    def test_scopes_are_independent(self) -> None:
        identifier = uuid.uuid4().hex
        for _ in range(3):
            enforce("scope_a", identifier, limit=3, window_seconds=60)

        enforce("scope_b", identifier, limit=3, window_seconds=60)  # must not raise

    def test_identifiers_are_independent(self) -> None:
        scope = "test"
        for _ in range(3):
            enforce(scope, "caller_a", limit=3, window_seconds=60)

        enforce(scope, "caller_b", limit=3, window_seconds=60)  # must not raise

    def test_fails_open_when_redis_is_unreachable(self, monkeypatch) -> None:
        # A handful of iterations is enough to prove no RateLimitExceeded is
        # raised despite limit=1 -- looping many times here just burns wall
        # clock on repeated slow-timeout connection attempts to a dead port.
        settings = get_settings()
        monkeypatch.setattr(settings, "redis_url", "redis://localhost:1")
        rate_limit._client.cache_clear()
        try:
            for _ in range(3):
                enforce("test", uuid.uuid4().hex, limit=1, window_seconds=60)
        finally:
            rate_limit._client.cache_clear()


class TestNotePhashActivity:
    def test_does_not_raise_below_threshold(self) -> None:
        phash = uuid.uuid4().hex
        for _ in range(3):
            note_phash_activity(phash, threshold=10, window_seconds=3600)

    def test_logs_once_when_threshold_is_crossed(self, caplog) -> None:
        import logging

        phash = uuid.uuid4().hex
        with caplog.at_level(logging.WARNING, logger="app.pipeline.rate_limit"):
            for _ in range(5):
                note_phash_activity(phash, threshold=5, window_seconds=3600)

        matching = [r for r in caplog.records if phash in r.message]
        assert len(matching) == 1

    def test_never_logs_raw_content_only_the_hash(self, caplog) -> None:
        import logging

        phash = "deadbeefcafef00d"
        with caplog.at_level(logging.WARNING, logger="app.pipeline.rate_limit"):
            for _ in range(3):
                note_phash_activity(phash, threshold=3, window_seconds=3600)

        for record in caplog.records:
            assert phash in record.message
            # Nothing beyond the hash, a count, and the fixed explanatory text.
            assert "bytes" not in record.message.lower()
