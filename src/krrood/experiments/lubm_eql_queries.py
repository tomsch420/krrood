import os
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
from krrood.entity_query_language.symbolic import ResultQuantifier

from krrood.experiments import lubm_with_predicates
from krrood.experiments.helpers import evaluate_eql
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


def get_eql_queries() -> List[ResultQuantifier]:
    # 1 (No joining, just filtration of graduate students through taking a certain course)
    with symbolic_mode():
        q1 = a(
            x := GraduateStudent(),
            flatten(x.takes_course).name == "GraduateCourse0",
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
            contains(
                x.publication_author,
                the(AssistantProfessor(name="AssistantProfessor0")).person,
            ),
        )

    # 4
    with symbolic_mode():
        q4 = a(x := Professor(), flatten(x.works_for).name == "Department0")

    # 5
    with symbolic_mode():
        q5 = a(x := Person(), flatten(x.member_of).name == "Department0")

    # 6
    with symbolic_mode():
        q6 = a(x := Student())

    # 7
    with symbolic_mode():
        q7 = a(
            set_of(
                (
                    x := Student(),
                    y := the(AssociateProfessor(name="AssociateProfessor0")).teacher_of,
                ),
                contains(y, flatten(x.takes_course)),
                # can be optimized by walking from student.takes_course to teacher_of to AssociateProfessor
                # in the SymbolGraph
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
                contains(y.sub_organization_of, the(University(name="University0"))),
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
                contains(y.teacher_of, z),
            )
        )

    # 10
    with symbolic_mode():
        q10 = a(
            x := Student(),
            contains(x.takes_course, the(GraduateCourse(name="GraduateCourse0"))),
        )

    # 11
    with symbolic_mode():
        q11 = a(
            x := ResearchGroup(),
            contains(x.sub_organization_of, the(University(name="University0"))),
        )

    # 12
    with symbolic_mode():
        q12 = a(
            set_of(
                (x := Chair(), y := flatten(x.works_for)),
                HasType(y, Department),
                contains(y.sub_organization_of, the(University(name="University0"))),
            )  # writing contains like this implies that the user knows that this is a set of objects.
            # A more declarative way would be to write SubOrganizationOf(y, the(University(name="University0"))).
        )

    # 13
    with symbolic_mode():
        q13 = a(
            x := the(University(name="University0")).has_alumnus,
        )

    # 14
    with symbolic_mode():
        q14 = a(x := UndergraduateStudent())

    eql_queries = [q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12, q13, q14]
    return eql_queries


if __name__ == "__main__":
    instances_path = os.path.join("..", "..", "..", "resources", "lubm_instances.owl")
    load_instances(
        instances_path,
        model_module=lubm_with_predicates,
    )
    start_time = time.time()
    counts, results = evaluate_eql(get_eql_queries())
    end_time = time.time()
    for i, n in enumerate(counts, 1):
        print(f"{i}:{n}")
        print({type(r) for r in results[i - 1]})
    print(f"Time elapsed: {end_time - start_time} seconds")
