import itertools
import time
from typing import List

from krrood.entity_query_language.entity import (
    symbolic_mode,
    a,
    flatten,
    contains,
    set_of,
    the,
)
from krrood.entity_query_language.predicate import HasType
from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.entity_query_language.symbolic import ResultQuantifier
from krrood.experiments import lubm_with_predicates
from krrood.experiments.helpers import (
    evaluate_eql,
    load_instances_for_lubm_with_predicates,
)
from krrood.experiments.lubm_with_predicates import (
    GraduateStudent,
    Person,
    Publication,
    Professor,
    AssociateProfessor,
    Department,
    University,
    Student,
    Faculty,
    ResearchGroup,
    Chair,
    UndergraduateStudent,
)
from krrood.ormatic.utils import classes_of_module


def get_eql_queries() -> List[ResultQuantifier]:
    # 1 (No joining, just filtration of graduate students through taking a certain course)
    SymbolGraph().clear()
    SymbolGraph.build(classes=classes_of_module(lubm_with_predicates))
    with symbolic_mode():
        q1 = a(
            x := GraduateStudent(),
            flatten(x.takes_course).uri
            == "http://www.Department0.University0.edu/GraduateCourse0",
        )

    # 2
    with symbolic_mode():
        q2 = a(
            x := GraduateStudent(),
            HasType(
                z := flatten(x.person.member_of), Department
            ),  # filtration of x producing z
            HasType(
                y := flatten(z.sub_organization_of), University
            ),  # filtration of z (which in turn filters x again) producing y
            contains(x.person.undergraduate_degree_from, y),  # join between x and y
        )

    # 3
    with symbolic_mode():
        q3 = a(
            x := Publication(),
            flatten(x.publication_author).uri
            == "http://www.Department0.University0.edu/AssistantProfessor0",
        )

    # 4
    with symbolic_mode():
        q4 = a(
            set_of(
                (
                    x := Professor(),
                    name := x.name,
                    email := x.person.email_address,
                    telephone := x.person.telephone,
                ),
                flatten(x.works_for).uri == "http://www.Department0.University0.edu",
            )
        )

    # 5
    with symbolic_mode():
        q5 = a(
            x := Person(),
            flatten(x.member_of).uri == "http://www.Department0.University0.edu",
        )

    # 6
    with symbolic_mode():
        q6 = a(x := Student())

    # 7
    with symbolic_mode():
        associate_professor = the(
            AssociateProfessor(
                uri="http://www.Department0.University0.edu/AssociateProfessor0"
            )
        )
        q7 = a(
            set_of(
                (
                    x := Student(),
                    y := flatten(x.takes_course),
                ),
                contains(associate_professor.teacher_of, y),
            )
        )

    # 8
    with symbolic_mode():
        q8 = a(
            set_of(
                (
                    x := Student(),
                    y := flatten(x.person.member_of),
                    z := x.person.email_address,
                ),
                HasType(y, Department),
                flatten(y.sub_organization_of).uri == "http://www.University0.edu",
            )
        )

    # 9
    with symbolic_mode():
        q9 = a(
            set_of(
                (
                    x := Student(),
                    y := flatten(x.person.advisor),
                    z := flatten(x.takes_course),
                ),
                HasType(y, Faculty),
                contains(
                    y.teacher_of, z
                ),  # will benefit from symbol graph optimization
            )
        )

    # 10
    with symbolic_mode():
        q10 = a(
            x := Student(),
            flatten(x.takes_course).uri
            == "http://www.Department0.University0.edu/GraduateCourse0",
        )

    # 11
    with symbolic_mode():
        q11 = a(
            x := ResearchGroup(),
            flatten(x.sub_organization_of).uri == "http://www.University0.edu",
        )

    # 12
    with symbolic_mode():
        q12 = a(
            set_of(
                (x := Chair(), y := flatten(x.works_for)),
                HasType(y, Department),
                flatten(y.sub_organization_of).uri == "http://www.University0.edu",
            )  # writing contains like this implies that the user knows that this is a set of objects.
            # A more declarative way would be to write SubOrganizationOf(y, the(University(name="University0"))).
        )

    # 13
    with symbolic_mode():
        q13 = a(
            x := flatten(the(University(uri="http://www.University0.edu")).has_alumnus),
        )

    # 14
    with symbolic_mode():
        q14 = a(x := UndergraduateStudent())

    eql_queries = [q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12, q13, q14]
    return eql_queries


def get_python_queries():
    """
    Legacy hand-written Python for q8. Kept for comparison.
    """
    students_data = (
        data for cls_, data in registry._by_class.items() if issubclass(cls_, Student)
    )
    flat_students_data = itertools.chain.from_iterable(students_data)
    q8 = (
        (student, m, student.person.email_address)
        for student in flat_students_data
        for m in student.person.member_of
        for u in m.sub_organization_of
        if isinstance(m, Department) and (u.uri == "http://www.University0.edu")
    )
    return [q8]


if __name__ == "__main__":
    registry = load_instances_for_lubm_with_predicates()
    python_start_time = time.time()
    count = None
    for pq in get_python_queries():
        count = len(list(pq))
    python_end_time = time.time()
    print(f"Python Count: {count}")
    print(f"Python Time elapsed: {python_end_time - python_start_time} seconds")
    start_time = time.time()
    counts, results, times = evaluate_eql(get_eql_queries())
    end_time = time.time()
    for i, n in enumerate(counts, 1):
        print(f"{i}:{n} ({times[i - 1]} sec)")
        print({type(r) for r in results[i - 1]})
    print(f"Time elapsed: {end_time - start_time} seconds")
