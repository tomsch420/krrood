from __future__ import annotations

from krrood.entity_query_language.cache_data import IndexedCache


class TestIndexedCacheFastPaths:
    def test_exact_contains(self):
        cache = IndexedCache([1, 2])
        # Insert a fully bound entry
        cache.insert({1: "a", 2: "b"}, output="ab", index=True)

        # exact_contains should be True only when all keys are present and match exactly
        assert cache.exact_contains({1: "a", 2: "b"}) is True
        assert cache.exact_contains({1: "a"}) is False
        assert cache.exact_contains({2: "b"}) is False
        assert cache.exact_contains({1: "a", 2: "x"}) is False

    def test_check_with_bitmask_and_exact(self):
        cache = IndexedCache([1, 2])
        # No overlap in keys -> check should return False quickly
        assert cache.check({3: "z"}) is False

        # Populate cache with a couple of entries
        cache.insert({1: "a", 2: "b"}, output="ab", index=True)
        cache.insert({1: "a"}, output="a*", index=True)

        # Exact match should short-circuit to True
        assert cache.check({1: "a", 2: "b"}) is True

        # Partial assignment that is covered by SeenSet should also be True
        # (there exists something under 1="a")
        assert cache.check({1: "a"}) is True

        # Conflicting partial assignment should be False
        assert cache.check({1: "x"}) is False
