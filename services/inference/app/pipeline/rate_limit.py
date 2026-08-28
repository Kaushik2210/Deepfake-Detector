"""Fixed-window rate limiting and abuse-pattern logging, backed by Redis.

Best-effort, the same way hash_cache.py treats its own store: an unreachable
Redis degrades to "no rate limiting today" rather than failing every request
outright. Availability of the detector matters more than perfect enforcement
of a limit, and a rate limiter that takes the whole service down when it can't
reach its own backing store would be a worse failure mode than the abuse it
exists to prevent.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a caller has exceeded its limit for a scope. main.py maps
    this to HTTP 429, the same way DecodeError maps to 400 -- this module
    stays FastAPI-agnostic, matching the rest of app/pipeline."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(f"rate limit exceeded: {limit} requests per {window_seconds}s")


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    settings = get_settings()
    # Short timeouts: a slow/unreachable Redis must fail fast into the
    # except-and-continue path below, not make every request wait on it.
    return redis.Redis.from_url(
        settings.redis_url, socket_connect_timeout=1, socket_timeout=1
    )


def _increment(key: str, window_seconds: int) -> int | None:
    """Atomically increment a fixed-window counter, returning the new count.

    None means Redis was unreachable -- callers must treat that as "allow the
    request", not as a count of zero. Fixed windows can double-count activity
    that straddles a window boundary, unlike a sliding-window log; that
    imprecision is an acceptable trade for a single INCR+EXPIRE round trip
    rather than tracking a timestamp per request. This is abuse prevention,
    not a billing meter.
    """
    try:
        client = _client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)  # only arms the TTL once
        count, _ = pipe.execute()
        return int(count)
    except redis.RedisError:
        return None


def enforce(scope: str, identifier: str, limit: int, window_seconds: int) -> None:
    """Raise RateLimitExceeded if `identifier` has gone over `limit` requests
    for `scope` within the current window."""
    count = _increment(f"ratelimit:{scope}:{identifier}", window_seconds)

    if count is None:
        logger.warning(
            "rate limiter unreachable, request allowed unrestricted (scope=%s)", scope
        )
        return

    if count > limit:
        raise RateLimitExceeded(limit, window_seconds)


def note_phash_activity(phash: str, threshold: int, window_seconds: int) -> None:
    """Log (never block) when the same piece of content is analysed or looked
    up unusually often in a short window -- the harassment pattern CLAUDE.md's
    ethics guardrails name explicitly: this tool can be misused to repeatedly
    "prove" the same person's real content is fake to different audiences. A
    per-caller rate limit cannot see this pattern, since it is spread across
    many different callers checking the same content, not one caller making
    many requests. Never logs raw media, only the perceptual hash and a count.
    """
    count = _increment(f"phash_activity:{phash}", window_seconds)
    if count is None:
        return

    # Logged only once per window, when the threshold is first crossed, not on
    # every subsequent lookup -- this should read as a signal, not spam.
    if count == threshold:
        logger.warning(
            "phash %s analysed/looked up %d times within %ds -- possible repeated "
            "harassment pattern (CLAUDE.md's abuse guardrails)",
            phash,
            count,
            window_seconds,
        )
