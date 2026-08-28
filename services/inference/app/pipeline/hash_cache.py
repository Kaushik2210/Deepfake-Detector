"""Perceptual-hash cache backing ``POST /v1/analyze/hash``.

The extension computes a perceptual hash client-side (see
``packages/core/src/phash.ts``) before ever uploading media, so a repeat
lookup of something already analysed costs a small JSON call instead of a
re-upload -- privacy principle 4's "every upload is an explicit per-item
action" is easiest to honour when most clicks don't need an upload at all.

A client-computed hash will not bit-match a server-computed one for the same
source file: the browser's canvas resize and OpenCV's ``INTER_AREA`` are
different algorithms, and that is on top of whatever drift recompression or
rescaling already cause between two copies of visually the same image. Lookup
is therefore nearest-neighbour by Hamming distance, not exact match.

Nearest-neighbour search runs against an in-memory BK-tree (bktree.py) built
from Postgres on first use in this process, rather than the bounded linear
scan this module used before -- the "future work" its docstring used to name.
``find_best_match``/``Candidate`` remain as a pure reference implementation,
used by tests to cross-check the tree gives the same answer, not as the
production lookup path anymore. See DECISIONS.md.

The tree is per-process, not shared across a multi-worker deployment: a hash
inserted by one worker is invisible to another's tree until that worker's own
next insert. Acceptable for a best-effort convenience cache -- a miss just
means a real upload happens instead, never a wrong answer. Exact-match lookups
always hit Postgres directly regardless, so they are never stale.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings
from app.pipeline.bktree import BKTree
from app.pipeline.phash import hamming_distance

T = TypeVar("T")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS phash_cache (
    id BIGSERIAL PRIMARY KEY,
    phash TEXT NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ttl_expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS phash_cache_phash_idx ON phash_cache (phash);
CREATE INDEX IF NOT EXISTS phash_cache_ttl_idx ON phash_cache (ttl_expires_at);
"""


@dataclass(frozen=True)
class Candidate(Generic[T]):
    hash: str
    payload: T


def find_best_match(
    query_hash: str, candidates: list[Candidate[T]], max_distance: int
) -> T | None:
    """Nearest candidate within ``max_distance`` bits, or None.

    Pure and DB-free on purpose: this is the part of the cache actually worth
    testing carefully, and it should not need a running Postgres to do it.
    """
    best: T | None = None
    best_distance = max_distance + 1

    for candidate in candidates:
        distance = hamming_distance(query_hash, candidate.hash)
        if distance < best_distance:
            best_distance = distance
            best = candidate.payload

    return best if best_distance <= max_distance else None


class HashCacheUnavailable(RuntimeError):
    """Raised when the cache database can't be reached.

    A cache miss and a cache being unreachable are different situations. The
    caller decides how to treat this -- for /v1/analyze/hash it degrades to a
    404, the same outcome as a genuine miss, but is worth its own type rather
    than being silently swallowed.
    """


# In-memory index, built from Postgres on first use in this process. Payload
# carries ttl_expires_at alongside the report so an expired entry can be
# filtered out at query time -- BK-trees have no efficient delete, so instead
# of removing swept rows from the tree, stale hits are simply skipped, and the
# tree is rebuilt wholesale (_TREE = None) if it ever needs a hard refresh.
_TreeEntry = tuple[dict, datetime]
_TREE: BKTree[_TreeEntry] | None = None
_TREE_LOCK = threading.Lock()


def reset_tree() -> None:
    """Drop the in-memory index so the next lookup rebuilds it from Postgres.

    Not called anywhere in the request path -- tests use this to keep the
    tree in sync with data they delete directly from Postgres (bypassing
    insert()/sweep_expired(), which are the only two things that otherwise
    keep the tree consistent). A real deployment has no equivalent need: rows
    only ever leave via sweep_expired(), whose lookup()-time TTL filter
    already keeps swept-but-still-in-tree entries from being served.
    """
    global _TREE
    with _TREE_LOCK:
        _TREE = None


def _ensure_tree() -> BKTree[_TreeEntry]:
    global _TREE
    with _TREE_LOCK:
        if _TREE is not None:
            return _TREE

        tree: BKTree[_TreeEntry] = BKTree(hamming_distance)
        with _connection() as conn:
            conn.row_factory = dict_row
            rows = conn.execute(
                "SELECT phash, report, ttl_expires_at FROM phash_cache "
                "WHERE ttl_expires_at > now()"
            ).fetchall()
        for row in rows:
            tree.insert(row["phash"], (row["report"], row["ttl_expires_at"]))

        _TREE = tree
        return _TREE


@contextmanager
def _connection():
    settings = get_settings()
    try:
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        raise HashCacheUnavailable(str(exc)) from exc


def ensure_schema() -> None:
    with _connection() as conn:
        conn.execute(_SCHEMA)


def insert(phash: str, report: dict[str, Any], ttl_expires_at: datetime) -> None:
    ensure_schema()
    with _connection() as conn:
        conn.execute(
            "INSERT INTO phash_cache (phash, report, ttl_expires_at) VALUES (%s, %s, %s)",
            (phash, json.dumps(report), ttl_expires_at),
        )

    # Keep this process's tree in sync without a full rebuild. Only if it has
    # already been built -- if nothing has queried yet, the next query builds
    # it fresh from Postgres and picks this row up then anyway.
    if _TREE is not None:
        with _TREE_LOCK:
            _TREE.insert(phash, (report, ttl_expires_at))


def sweep_expired() -> int:
    """Delete cache rows past their TTL. Called lazily on lookup rather than
    on a schedule -- this service has no scheduler, and a lookup is exactly
    when stale entries would otherwise wrongly get served."""
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM phash_cache WHERE ttl_expires_at <= now()")
        return cursor.rowcount


def lookup(phash: str) -> dict[str, Any] | None:
    """Exact match first (always hits Postgres directly, so never stale),
    then nearest-neighbour search against the in-memory BK-tree."""
    settings = get_settings()
    ensure_schema()
    sweep_expired()

    with _connection() as conn:
        conn.row_factory = dict_row
        exact = conn.execute(
            "SELECT report FROM phash_cache WHERE phash = %s "
            "AND ttl_expires_at > now() ORDER BY created_at DESC LIMIT 1",
            (phash,),
        ).fetchone()
        if exact is not None:
            return exact["report"]

    tree = _ensure_tree()
    now = now_utc()
    matches = tree.query(phash, settings.phash_match_max_distance)
    live = [(distance, report) for distance, (report, ttl) in matches if ttl > now]
    if not live:
        return None
    return min(live, key=lambda pair: pair[0])[1]


def cache_report(phash: str | None, report: dict[str, Any], ttl_expires_at: datetime) -> None:
    """Best-effort cache write. Never blocks a report from being returned to
    the caller: an unreachable cache database should degrade to "no caching
    today", not to a failed analysis the user already waited for."""
    if not phash:
        return
    try:
        insert(phash, report, ttl_expires_at)
    except HashCacheUnavailable:
        pass


def now_utc() -> datetime:
    return datetime.now(UTC)
