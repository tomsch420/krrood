from __future__ import annotations

from copy import copy

from line_profiler import profile
from typing_extensions import Type

from .hashed_data import HashedIterable
from .utils import All

"""
Cache utilities.

This module provides caching datastructures and utilities. In addision it 
provides simple counters and timers used to profile the internal
caching layer. It also exposes a runtime switch to enable/disable caching.
"""
import contextvars
from collections import defaultdict, UserDict
from dataclasses import dataclass, field
from typing import Dict, List, Any, Iterable, Hashable, Optional


@dataclass
class CacheCount:
    """
    Counter for named cache-related events.

    :ivar values: Mapping from counter name to its integer value.
    :vartype values: Dict[str, int]
    """

    values: Dict[str, int] = field(default_factory=lambda: defaultdict(lambda: 0))

    def update(self, name: str) -> None:
        """
        Increment a named counter.

        :param name: Counter name to increment.
        :type name: str
        :return: None
        :rtype: None
        """
        self.values[name] += 1


@dataclass
class CacheTime:
    """
    Aggregator for named timing values (in seconds).

    :ivar values: Mapping from timer name to accumulated seconds.
    :vartype values: Dict[str, float]
    """

    values: Dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 0.0))

    def add(self, name: str, seconds: float) -> None:
        """
        Add elapsed time to a named timer.

        :param name: Timer name.
        :type name: str
        :param seconds: Elapsed time to add in seconds.
        :type seconds: float
        :return: None
        :rtype: None
        """
        self.values[name] += seconds


cache_enter_count = CacheCount()
cache_search_count = CacheCount()
cache_match_count = CacheCount()
cache_lookup_time = CacheTime()
cache_update_time = CacheTime()

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


def cache_profile_report() -> Dict[str, Dict[str, float]]:
    """
    Produce a snapshot of current cache statistics.

    :return: Dictionary with counters and timers grouped by kind.
    :rtype: Dict[str, Dict[str, float]]
    """
    return {
        "enter_count": dict(cache_enter_count.values),
        "search_count": dict(cache_search_count.values),
        "match_count": dict(cache_match_count.values),
        "lookup_time_seconds": dict(cache_lookup_time.values),
        "update_time_seconds": dict(cache_update_time.values),
    }


@dataclass
class TrieNode:
    """
    A node in the coverage trie. Each edge is keyed by a (key, value) pair.
    Terminal nodes indicate a complete stored constraint.
    """

    children: dict = field(default_factory=dict)
    terminal: bool = False


@dataclass
class SeenSet:
    """
    Coverage index for previously seen partial assignments.

    This replaces the linear scan with a trie-based index using a fixed key order.
    An assignment A is considered covered if there exists a stored constraint C
    such that C.items() is a subset of A.items().
    """

    sorted_keys: tuple = field(default_factory=tuple)
    root: TrieNode = field(default_factory=TrieNode, init=False)
    all_seen: bool = field(default=False, init=False)
    _fallback_constraints: list = field(default_factory=list, init=False, repr=False)

    def set_keys(self, keys: Iterable[Hashable]) -> None:
        """
        Set or update the fixed key order for the index.
        Resets the trie since the projection order has changed.
        """
        self.sorted_keys = tuple(sorted(keys))
        self.clear()

    def add(self, assignment: Dict) -> None:
        """
        Add a constraint (partial assignment) to the coverage index.
        """
        if self.all_seen:
            return
        if not assignment:
            # Empty constraint means everything is covered
            self.all_seen = True
            # Only mark terminal when we actually use the trie
            if self.sorted_keys:
                self.root.terminal = True
            return
        # If we have no key order, fall back to linear storage and subset checks
        if not self.sorted_keys:
            self._fallback_constraints.append(dict(assignment))
            return
        node = self.root
        # Insert only pairs present in the constraint, following fixed key order
        for k in self.sorted_keys:
            if k not in assignment:
                continue
            v = assignment[k]
            node = node.children.setdefault((k, v), TrieNode())
        node.terminal = True

    @profile
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
            # but should mark the index so subsequent checks short-circuit.
            self.all_seen = True
            if self.sorted_keys:
                self.root.terminal = True
            return False

        # Fallback linear scan when no key order is defined
        if not self.sorted_keys:
            for constraint in self._fallback_constraints:
                if all((k in assignment) and (assignment[k] == v) for k, v in constraint.items()):
                    return True
            return False

        node = self.root
        if node.terminal:
            return True
        # Walk down following available keys in assignment; any terminal on the path
        # implies a stored constraint is a subset of this assignment.
        for k in self.sorted_keys:
            v = assignment.get(k, None)
            if v is None:
                continue
            child = node.children.get((k, v))
            if child is None:
                continue
            node = child
            if node.terminal:
                return True
        return False

    def clear(self):
        self.root = TrieNode()
        self.all_seen = False
        self._fallback_constraints.clear()


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
    :ivar enter_count: Diagnostic counter for retrieval entries.
    :ivar search_count: Diagnostic counter for wildcard searches.
    """

    _keys: List[Hashable] = field(default_factory=list)
    seen_set: SeenSet = field(default_factory=SeenSet, init=False)
    cache: CacheDict = field(default_factory=CacheDict, init=False)
    flat_cache: HashedIterable = field(default_factory=HashedIterable, init=False)
    enter_count: int = field(default=0, init=False)
    search_count: int = field(default=0, init=False)

    def __post_init__(self):
        self.keys = self._keys

    @property
    def keys(self) -> List[Hashable]:
        return self._keys

    @keys.setter
    def keys(self, keys: List[Hashable]):
        self._keys = list(sorted(keys))
        self.cache.clear()
        self.seen_set.set_keys(self._keys)

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

    @profile
    def check(self, assignment: Dict) -> bool:
        """
        Check if seen entries cover an assignment (dict).

        :param assignment: The assignment to check.
        """
        # If no keys from this cache are present in the assignment, do not short-circuit via coverage.
        # This preserves correctness by forcing evaluation of the right-hand side when unconstrained.
        for k in self._keys:
            if k in assignment:
                break
        else:
            return False
        # Do not allocate a filtered dict; the coverage index projects by its own key order.
        if not self.seen_set.check(assignment):
            return False
        # Double-check there is at least one retrievable match under this assignment.
        # This prevents false positives from coverage that would otherwise skip evaluation.
        for _ in self.retrieve(assignment):
            return True
        return False

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
            self.enter_count += 1
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
                else:
                    self.search_count += 1
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
            self.search_count += 1
            yield from self.retrieve(assignment, cache_val, key_idx + 1, result)
        else:
            yield result, cache_val


def yield_class_values_from_cache(
    cache: Dict[Type, IndexedCache],
    clazz: Type,
    assignment: Optional[Dict] = None,
    from_index: bool = True,
    cache_keys: Optional[List] = None,
) -> Iterable:
    if from_index and assignment and ((clazz not in cache) or (not cache[clazz].keys)):
        cache[clazz].keys = list(assignment.keys())
    if not cache_keys:
        cache_keys = get_cache_keys_for_class_(cache, clazz)
    for t in cache_keys:
        yield from cache[t].retrieve(assignment, from_index=from_index)


def get_cache_keys_for_class_(
    cache: Dict[Type, IndexedCache], clazz: Type
) -> List[Type]:
    """
    Get the cache keys for the given class which are its subclasses and itself.
    """
    cache_keys = []
    if isinstance(clazz, type):
        cache_keys = [
            t for t in cache.keys() if isinstance(t, type) and issubclass(t, clazz)
        ]
    elif clazz in cache:
        cache_keys = [clazz]
    return cache_keys
