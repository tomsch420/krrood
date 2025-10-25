from __future__ import annotations

import re

import pytest

from krrood.experiments.helpers import load_instances_for_lubm_with_predicates
from krrood.experiments.lubm_with_predicates import (
    GraduateStudent,
    Department,
    University,
    Student,
)
from krrood.entity_query_language.entity import symbolic_mode, a, flatten, set_of, contains
from krrood.entity_query_language.predicate import HasType
from krrood.entity_query_language.eql_to_python import compile_to_python


@pytest.fixture(scope="module", autouse=True)
def _load_registry():
    # Ensure cache and classes are initialized once for this module
    load_instances_for_lubm_with_predicates()


def _normalize_source(src: str) -> str:
    # Collapse multiple spaces to one and strip
    return re.sub(r"\s+", " ", src).strip()


def test_has_type_compiles_to_isinstance():
    with symbolic_mode():
        q = a(x := GraduateStudent(), HasType(flatten(x.person.member_of), Department))
    compiled = compile_to_python(q)
    src = _normalize_source(compiled.source)
    assert "isinstance(" in src and "Department" in src


def test_flatten_emits_for_loop():
    with symbolic_mode():
        q = a(x := Student(), y := flatten(x.takes_course))
    compiled = compile_to_python(q)
    src = compiled.source
    # We expect to see a loop introduced for flatten
    assert "for" in src and "_iter" in src and "in _iter" in _normalize_source(src)


def test_set_of_emits_seen_deduplication():
    with symbolic_mode():
        q = a(
            set_of(
                (
                    x := Student(),
                    y := flatten(x.takes_course),
                ),
            )
        )
    compiled = compile_to_python(q)
    src = compiled.source
    assert "_seen = set()" in src
    assert "_seen.add(" in src and "if" in src and "in _seen" in src


def test_contains_precompute_emits_set_when_possible():
    # Similar pattern to LUBM query 7 but smaller: a fixed professor teaches courses, join with students' courses
    from krrood.experiments.lubm_with_predicates import AssociateProfessor
    with symbolic_mode():
        target = a(AssociateProfessor(uri="http://www.Department0.University0.edu/AssociateProfessor0"))
        q = a(set_of((x := Student(), y := flatten(x.takes_course)), contains(target.teacher_of, y)))
    compiled = compile_to_python(q)
    src = compiled.source
    # Expect a precomputed membership set
    assert "pre_set_" in src or "pre_set" in src


def test_variable_iteration_emits_iterate_instances():
    # Ensure base Symbol variable iteration uses the cache iterator helper
    with symbolic_mode():
        q = a(x := Student())
    compiled = compile_to_python(q)
    src = compiled.source
    assert "in _iterate_instances(Student)" in src


def test_attribute_binding_assignment():
    # Ensure attribute access is lowered to a simple assignment
    with symbolic_mode():
        q = a(x := Student(), n := x.name)
    compiled = compile_to_python(q)
    lines = [ln.strip() for ln in compiled.source.splitlines()]
    assert any(" = " in ln and ".name" in ln for ln in lines)


def test_comparator_equality_emission():
    # Ensure equality comparator emits a standard Python if condition
    with symbolic_mode():
        q = a(x := Student(), (x.name == "SomeName"))
    compiled = compile_to_python(q)
    src = _normalize_source(compiled.source)
    assert "if (" in src and "==" in src and ".name" in src
