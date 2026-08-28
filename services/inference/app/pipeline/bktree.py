"""A BK-tree (Burkhard-Keller tree) for nearest-neighbour search under a
discrete metric -- Hamming distance on perceptual hashes here. Hand-built
for this project (Burkhard & Keller, 1973's structure, not any particular
library's implementation) to replace hash_cache.py's bounded linear scan,
exactly the "future work" the module's own docstring already named.

The idea: every node is a point; each of its children sits in a bucket keyed
by its exact distance from the parent. A query at distance d from a node can
only match points whose distance from that node's parent falls within
[d - max_distance, d + max_distance], by the triangle inequality -- so a
query only has to descend into a few buckets, not compare against every
point in the tree. For a cache of thousands of hashes queried at a small
max_distance, this is a large, structural improvement over scanning every
row, not just a constant-factor one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

DistanceFn = Callable[[str, str], int]


@dataclass
class _Node(Generic[T]):
    key: str
    payload: T
    children: dict[int, _Node[T]] = field(default_factory=dict)


class BKTree(Generic[T]):
    """Not thread-safe for concurrent inserts; callers serialise their own
    writes (hash_cache.py does this with a lock). Concurrent reads are safe.
    """

    def __init__(self, distance_fn: DistanceFn):
        self._distance_fn = distance_fn
        self._root: _Node[T] | None = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def insert(self, key: str, payload: T) -> None:
        self._size += 1
        if self._root is None:
            self._root = _Node(key=key, payload=payload)
            return

        node = self._root
        while True:
            distance = self._distance_fn(key, node.key)
            if distance == 0:
                # An exact duplicate hash: keep the newest by overwriting the
                # payload at this node rather than growing a same-key branch
                # that could never be reached (its own distance-0 bucket).
                node.payload = payload
                self._size -= 1
                return

            existing_child = node.children.get(distance)
            if existing_child is None:
                node.children[distance] = _Node(key=key, payload=payload)
                return
            node = existing_child

    def query(self, key: str, max_distance: int) -> list[tuple[int, T]]:
        """Every (distance, payload) pair within max_distance of `key`,
        unsorted -- callers pick the closest themselves (hash_cache.py wants
        the single nearest; a test wants the whole set)."""
        if self._root is None:
            return []

        results: list[tuple[int, T]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            distance = self._distance_fn(key, node.key)
            if distance <= max_distance:
                results.append((distance, node.payload))

            # Triangle inequality: any match reachable through a child in
            # bucket `child_distance` must itself be within max_distance of
            # `key`, i.e. |distance - child_distance| <= max_distance.
            lo, hi = distance - max_distance, distance + max_distance
            for child_distance, child in node.children.items():
                if lo <= child_distance <= hi:
                    stack.append(child)

        return results

    def query_nearest(self, key: str, max_distance: int) -> T | None:
        matches = self.query(key, max_distance)
        if not matches:
            return None
        return min(matches, key=lambda pair: pair[0])[1]
