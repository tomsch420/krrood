from __future__ import annotations

from typing_extensions import Dict, Iterable, List

import pytest

from krrood.entity_query_language.hashed_data import HashedValue
from krrood.entity_query_language.utils import generate_combinations
from krrood.entity_query_language.utils import IDGenerator


# We import the function after potential implementation
try:
    from krrood.entity_query_language.utils import generate_bindings
except Exception:  # pragma: no cover - fallback during initial TDD red phase
    generate_bindings = None  # type: ignore


class _StubVar:
    """
    A very small stub that mimics the minimal interface used by
    utils.generate_bindings and Variable._generate_combinations_for_child_vars_values_.

    It yields dictionaries of the form {self._id_: HashedValue(value)} from its domain.
    Optionally, it can enforce a dependency on another variable id by only yielding
    values equal to sources[dep_id].value + offset.
    """

    _id_gen = IDGenerator()

    def __init__(
        self,
        name: str,
        domain: Iterable[int],
        dep_on: int | None = None,
        offset: int = 0,
    ):
        self._name__ = name
        self._id_ = self._id_gen(self)
        self._domain_values: List[int] = list(domain)
        self._dep_on = dep_on
        self._offset = offset
        self._is_indexed_ = False
        self._kwargs_expression_ = None

    def _name_(self) -> str:
        return self._name__

    def _evaluate__(self, sources: Dict[int, HashedValue] | None = None):
        sources = sources or {}
        if self._dep_on is not None and self._dep_on in sources:
            target = sources[self._dep_on].value + self._offset
            if target in self._domain_values:
                yield {self._id_: HashedValue(target)}
            return
        for v in self._domain_values:
            yield {self._id_: HashedValue(v)}


@pytest.mark.skipif(
    generate_bindings is None, reason="generate_bindings not implemented yet"
)
class TestGenerateBindings:
    def test_equivalence_without_dependencies(self):
        # Given three independent child variables
        a = _StubVar("a", [1, 2])
        b = _StubVar("b", [10, 20])
        c = _StubVar("c", [100])
        child_vars = {"a": a, "b": b, "c": c}

        # Old behavior using Cartesian product of generators
        gens = {k: v._evaluate__({}) for k, v in child_vars.items()}
        product_out = list(generate_combinations(gens))

        # New behavior using DFS backtracking (should be identical here)
        from krrood.entity_query_language.utils import generate_bindings

        dfs_out = list(generate_bindings(list(child_vars.items()), {}))

        def normalize(items):
            # Convert dict of name -> {id: hv} to frozenset of (name, hv.value)
            return {
                frozenset(
                    (name, next(iter(d.values())).value) for name, d in kw.items()
                )
                for kw in items
            }

        assert normalize(product_out) == normalize(dfs_out)

    def test_prunes_with_dependencies(self):
        # a and b in [1,2,3], c depends on a: c == a + 1
        a = _StubVar("a", [1, 2, 3])
        b = _StubVar("b", [1, 2, 3])
        c = _StubVar("c", [1, 2, 3, 4], dep_on=a._id_, offset=1)

        child_vars = {"a": a, "b": b, "c": c}
        gens = {k: v._evaluate__({}) for k, v in child_vars.items()}
        product_out = list(generate_combinations(gens))

        from krrood.entity_query_language.utils import generate_bindings

        dfs_out = list(generate_bindings(list(child_vars.items()), {}))

        # The DFS should be able to prune combinations that do not satisfy c == a + 1
        # So it should produce fewer or equal combinations compared to the full Cartesian product
        assert len(dfs_out) <= len(product_out)
        # And still produce only valid bindings for c when a is present
        for kw in dfs_out:
            # Find a and c values
            a_val = next(iter(kw["a"].values())).value
            c_val = next(iter(kw["c"].values())).value
            assert c_val == a_val + 1
