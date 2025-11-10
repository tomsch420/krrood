from __future__ import annotations

from copy import copy
from functools import lru_cache

from typing_extensions import Type

from .hashed_data import HashedIterable
from .utils import All

"""
Cache utilities.

This module provides caching datastructures and utilities.
It also exposes a runtime switch to enable/disable caching.
"""
import contextvars
from collections import UserDict
from dataclasses import dataclass, field, InitVar
from typing import Dict, List, Any, Iterable, Hashable, Optional, Tuple


# Runtime switch to enable/disable caching paths
_caching_enabled = contextvars.ContextVar("caching_enabled", default=True)


def enable_caching() -> None:
    """
    Enable the caching fast-paths for query evaluation.

    :return: None
    :rtype: None
    """
    _caching_enabled.set(True)


def disable_caching() -> None:
    """
    Disable the caching fast-paths for query evaluation.

    :return: None
    :rtype: None
    """
    _caching_enabled.set(False)


def is_caching_enabled() -> bool:
    """
    Check whether caching is currently enabled.

    :return: True if caching is enabled; False otherwise.
    :rtype: bool
    """
    return _caching_enabled.get()


@dataclass
class SeenSet:
    """
    Coverage index for previously seen partial assignments.

    This replaces the linear scan with a trie-based index using a fixed key order.
    An assignment A is considered covered if there exists a stored constraint C
    such that C.items() is a subset of A.items().
    """

    keys: tuple = field(default_factory=tuple, repr=False)
    all_seen: bool = field(default=False, init=False)
    constraints: list = field(default_factory=list, init=False, repr=False)
    exact: set = field(default_factory=set, init=False, repr=False)

    def add(self, assignment: Dict) -> None:
        """
        Add a constraint (partial assignment) to the coverage index.
        """
        if self.all_seen:
            return
        if not assignment:
            # Empty constraint means everything is covered
            self.all_seen = True
            return
        # Maintain exact-match set only when all keys are present
        if self.keys and all(k in assignment for k in self.keys):
            self.exact.add(tuple(assignment[k] for k in self.keys))
        self.constraints.append(dict(assignment))

    def check(self, assignment: Dict) -> bool:
        """
        Return True if any stored constraint is a subset of the given assignment.
        Mirrors previous semantics: encountering an empty assignment flips all_seen
        but returns False the first time to allow population.
        """
        if self.all_seen:
            return True
        if not assignment:
            # First observation of empty assignment should not be considered covered
            # but should mark the index so later checks short-circuit.
            self.all_seen = True
            return False

        # Fast exact-key path when all keys are present
        if self.exact_contains(assignment):
            return True

        # Fallback to coverage check using constraints
        for constraint in self.constraints:
            if all(
                (k in assignment) and (assignment[k] == v)
                for k, v in constraint.items()
            ):
                return True
        return False

    def exact_contains(self, assignment: Dict) -> bool:
        """
        Return True if the assignment contains all cache keys and the exact key tuple
        exists in the cache. This is an O(1) membership test and does not consult
        the coverage trie.
        """
        if self.keys and all(k in assignment for k in self.keys):
            t = tuple(assignment[k] for k in self.keys)
            if t in self.exact:
                return True
        return False

    def clear(self):
        self.all_seen = False
        self.constraints.clear()
        self.exact.clear()


class CacheDict(UserDict): ...


@dataclass
class IndexedCache:
    """
    A hierarchical cache keyed by a fixed sequence of indices.

    It supports insertion of outputs under partial assignments and retrieval with
    wildcard handling using the ALL sentinel.

    :ivar keys: Ordered list of integer keys to index the cache.
    :ivar seen_set: Helper to track assignments already checked.
    :ivar cache: Nested mapping structure storing cached results.
    :ivar flat_cache: Flattened mapping structure storing cached results.
    """

    _keys: InitVar[Tuple[Hashable]] = ()
    seen_set: SeenSet = field(default_factory=SeenSet, init=False)
    cache: CacheDict = field(default_factory=CacheDict, init=False)
    flat_cache: HashedIterable = field(default_factory=HashedIterable, init=False)

    def __post_init__(self, _keys: Tuple[Hashable] = ()):
        self.keys = _keys

    @property
    def keys(self) -> Tuple[Hashable]:
        return self.seen_set.keys

    @keys.setter
    def keys(self, keys: Iterable[Hashable]):
        self.seen_set.keys = tuple(sorted(keys))
        # Reset structures
        self.cache.clear()
        self.seen_set.clear()

    def insert(self, assignment: Dict, output: Any, index: bool = True) -> None:
        """
        Insert an output under the given partial assignment.

        Missing keys are filled with the ALL sentinel.

        :param assignment: Mapping from key index to concrete value.
        :type assignment: Dict
        :param output: Cached value to store at the leaf.
        :type output: Any
        :param index: If True, insert into cache tree; otherwise, store directly in a flat cache.
        :type index: bool
        :return: None
        :rtype: None
        """
        # Make a shallow copy only for seen_set tracking to avoid mutating caller's dict
        if not index or not assignment:
            self.flat_cache.add(output)
            return

        seen_assignment = dict(assignment)
        self.seen_set.add(seen_assignment)

        cache = self.cache
        keys = self.keys
        last_idx = len(keys) - 1

        # Use local lookups and setdefault to reduce overhead
        for idx, k in enumerate(keys):
            v = assignment.get(k, All)
            if idx < last_idx:
                next_cache = cache.get(v)
                if next_cache is None:
                    next_cache = CacheDict()
                    cache[v] = next_cache
                cache = next_cache
            else:
                cache[v] = output

    def check(self, assignment: Dict) -> bool:
        """
        Check if seen entries cover an assignment (dict).

        :param assignment: The assignment to check.
        """
        return self.seen_set.check(assignment)

    def __getitem__(self, key: Any):
        return self.flat_cache[key]

    def retrieve(
        self,
        assignment: Optional[Dict] = None,
        cache=None,
        key_idx=0,
        result: Dict = None,
        from_index: bool = True,
    ) -> Iterable:
        """
        Retrieve leaf results matching a (possibly partial) assignment.

        This yields tuples of (resolved_assignment, value) when a leaf is found.

        :param assignment: Partial mapping from key index to values.
        :param cache: Internal recursion parameter; the current cache node.
        :param key_idx: Internal recursion parameter; current key index position.
        :param result: Internal accumulator for building a full assignment.
        :param from_index: If True, retrieve from cache tree; otherwise, retrieve directly from flat cache.
        :return: Generator of (assignment, value) pairs.
        :rtype: Iterable
        """
        if not from_index:
            for v in self.flat_cache:
                yield {}, v
            return

        # Initialize result only once; avoid repeated copying where possible
        if result is None:
            result = copy(assignment)
        if cache is None:
            cache = self.cache
        # Fast return on empty cache node
        if isinstance(cache, CacheDict) and not cache:
            return
        keys = self.keys
        n_keys = len(keys)
        key = keys[key_idx]

        # Follow the concrete chain as far as it exists without exceptions
        while key in assignment:
            next_cache = cache.get(assignment[key])
            if next_cache is None:
                # Try wildcard branch at this level
                wildcard = cache.get(All)
                if wildcard is not None:
                    yield from self._yield_result(assignment, wildcard, key_idx, result)
                return
            cache = next_cache
            if key_idx + 1 < n_keys:
                key_idx += 1
                key = keys[key_idx]
            else:
                break

        if key not in assignment:
            # Prefer wildcard branch if available
            wildcard = cache.get(All)
            if wildcard is not None:
                yield from self._yield_result(assignment, wildcard, key_idx, result)
            else:
                # Explore all branches at this level, copying only the minimal delta
                for cache_key, cache_val in cache.items():
                    local_result = copy(result)
                    local_result[key] = cache_key
                    yield from self._yield_result(
                        assignment, cache_val, key_idx, local_result
                    )
        else:
            # Reached the leaf (value or next dict) specifically specified by assignment
            yield result, cache

    def clear(self):
        self.cache.clear()
        self.seen_set.clear()
        self.flat_cache.clear()

    def _yield_result(
        self, assignment: Dict, cache_val: Any, key_idx: int, result: Dict[int, Any]
    ):
        """
        Internal helper to descend into cache and yield concrete results.

        :param assignment: Original partial assignment.
        :param cache_val: Current cache node or value.
        :param key_idx: Current key index.
        :param result: Accumulated assignment.
        :return: Yields (assignment, value) when reaching leaves.
        """
        if isinstance(cache_val, CacheDict):
            yield from self.retrieve(assignment, cache_val, key_idx + 1, result)
        else:
            yield result, cache_val
