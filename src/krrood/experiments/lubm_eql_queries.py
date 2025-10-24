import os
import pickle
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
    GraduateCourse,
    Person,
    Publication,
    Professor,
    AssistantProfessor,
    AssociateProfessor,
    Department,
    University,
    Student,
    Course,
    Faculty,
    ResearchGroup,
    Chair,
    UndergraduateStudent,
    MemberOf,
    SubOrganizationOf,
    UndergraduateDegreeFrom,
    PublicationAuthor,
    TeacherOf,
    WorksFor,
    Advisor,
    HasAlumnus,
    TakesCourse,
)
from krrood.experiments.owl_instances_loader import load_instances
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
        assistant_professor = the(
            AssistantProfessor(
                uri="http://www.Department0.University0.edu/AssistantProfessor0"
            )
        )
        q3 = a(
            x := Publication(),
            contains(x.publication_author, assistant_professor.person),
        )

    # 4
    with symbolic_mode():
        q4 = a(
            x := Professor(),
            flatten(x.works_for).uri == "http://www.Department0.University0.edu",
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
        assistant_professor = the(
            AssistantProfessor(
                uri="http://www.Department0.University0.edu/AssistantProfessor0"
            )
        )
        q7 = a(
            set_of(
                (
                    x := Student(),
                    y := assistant_professor.teacher_of,
                ),
                contains(y, flatten(x.takes_course)),
                # can be optimized by walking from student.takes_course to teacher_of to AssociateProfessor
                # in the SymbolGraph
            )
        )

    # 8
    with symbolic_mode():
        university = the(University(uri="http://www.University0.edu"))
        q8 = a(
            set_of(
                (
                    x := Student(),
                    y := flatten(x.person.member_of),
                    z := x.person.email_address,
                ),
                HasType(y, Department),
                contains(
                    y.sub_organization_of,
                    university,
                ),
            )
        )
    # u = list(
    #     filter(
    #         lambda x: x.uri == "http://www.University0.edu",
    #         registry._by_class[University],
    #     )
    # )[0]
    # students = (
    #     registry._by_class[UndergraduateStudent] + registry._by_class[GraduateStudent]
    # )
    # equivalent_pyton_query = [
    #     (student, m, student.person.email_address)
    #     for student in students
    #     for m in student.person.member_of
    #     if isinstance(m, Department) and (u in m.sub_organization_of)
    # ]

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
                contains(y.teacher_of, z),
            )
        )

    # 10
    with symbolic_mode():
        q10 = a(
            x := Student(),
            contains(
                x.takes_course,
                the(
                    GraduateCourse(
                        uri="http://www.Department0.University0.edu/GraduateCourse0"
                    )
                ),
            ),
        )

    # 11
    with symbolic_mode():
        q11 = a(
            x := ResearchGroup(),
            contains(
                x.sub_organization_of, the(University(uri="http://www.University0.edu"))
            ),
        )

    # 12
    with symbolic_mode():
        q12 = a(
            set_of(
                (x := Chair(), y := flatten(x.works_for)),
                HasType(y, Department),
                contains(
                    y.sub_organization_of,
                    the(University(uri="http://www.University0.edu")),
                ),
            )  # writing contains like this implies that the user knows that this is a set of objects.
            # A more declarative way would be to write SubOrganizationOf(y, the(University(name="University0"))).
        )

    # 13
    with symbolic_mode():
        q13 = a(
            x := the(University(uri="http://www.University0.edu")).has_alumnus,
        )

    # 14
    with symbolic_mode():
        q14 = a(x := UndergraduateStudent())

    eql_queries = [q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12, q13, q14]
    return eql_queries


if __name__ == "__main__":
    registry = load_instances_for_lubm_with_predicates()
    start_time = time.time()
    counts, results = evaluate_eql(get_eql_queries())
    end_time = time.time()
    for i, n in enumerate(counts, 1):
        print(f"{i}:{n}")
        print({type(r) for r in results[i - 1]})
    print(f"Time elapsed: {end_time - start_time} seconds")
