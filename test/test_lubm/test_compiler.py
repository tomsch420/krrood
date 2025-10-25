from __future__ import annotations

import time

from krrood.experiments.helpers import (
    load_instances_for_lubm_with_predicates,
    evaluate_eql,
)
from krrood.experiments.lubm_eql_queries import get_eql_queries
from krrood.entity_query_language.eql_to_python import compile_to_python


def test_compiled_queries_results_match_eql():
    # Load instances to populate Variable cache and symbol graph
    registry = load_instances_for_lubm_with_predicates()

    # Build EQL queries
    eql_queries = get_eql_queries()
    total_eql_time = 0
    total_compiled_time = 0

    # Compile queries to a Python generator
    for i, q in enumerate(eql_queries):
        num = i + 1
        print(f"Compiling query {num}")
        start = time.time()
        compiled = compile_to_python(q)
        if num == 7:
            src = compiled.source
            print(src)
            assert "in pre_set_" in src, "q7 should use precomputed membership set"
            assert (
                "in (associate_professor_teacher_of)" not in src
            ), "q7 should not check membership against associate_professor.teacher_of directly"
            ap_loop = (
                "for associate_professor in _iterate_instances(AssociateProfessor)"
            )
            student_loop = "for student in _iterate_instances(Student)"
            if ap_loop in src and student_loop in src:
                assert src.find(ap_loop) < src.find(
                    student_loop
                ), "AssociateProfessor iteration must be outside and before the Student loop"
            uri = "http://www.Department0.University0.edu/AssociateProfessor0"
            assert src.count(uri) == 1, "q7 must emit the AssociateProfessor URI filter only once in precompute"
        compiled_results = list(compiled.function())
        end = time.time()
        total_compiled_time += end - start
        print(f"Compiled query time: {end - start} seconds")
        # Evaluate reference EQL engine for q8 and compare counts
        counts, _, t = evaluate_eql([q])
        total_eql_time += t[0]
        print(f"Reference query time: {t[0]} seconds")
        assert len(compiled_results) == counts[0]
    print(f"Total compiled time: {total_compiled_time} seconds")
    print(f"Total reference time: {total_eql_time} seconds")
