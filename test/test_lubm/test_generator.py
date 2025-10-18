import time

from krrood.entity_query_language.entity import let, entity, an, contains, the, set_of
from krrood.entity_query_language.predicate import Predicate
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.experiments.generator import UniversityDataGenerator
from krrood.experiments.lubm import (
    University,
    Student,
    GraduateStudent,
    GraduateCourse,
    Department,
)

import pytest
from krrood.entity_query_language.predicate import Predicate
from krrood.experiments.generator import UniversityDataGenerator


@pytest.fixture(scope="session")
def university_data():
    Predicate.build_symbol_graph()
    generator = UniversityDataGenerator(university_count=1, seed=69)
    return generator.generate()


def query_1(specific_graduate_course):
    """
    Select all graduate students that take the given graduate course.
    """
    with symbolic_mode():
        graduate_student = let(GraduateStudent)

        query = an(
            entity(
                graduate_student,
                contains(
                    graduate_student.takes_graduate_courses, specific_graduate_course
                ),
            )
        )
    return query


def query_2():
    """
    Select all graduate students that work in a department of the university where they got their undergraduate
    degree from.
    """
    with symbolic_mode():
        graduate_student = let(GraduateStudent)
        university = let(University)
        department = let(Department)

        query = an(
            set_of(
                (graduate_student, university, department),
                contains(university.departments, department),
                contains(department.graduate_students, graduate_student),
                graduate_student.undergraduate_degree_from == university,
            )
        )
    return query


def test_ood_querying(university_data):

    university: University = university_data[0]

    specific_graduate_course = university.departments[0].graduate_courses[0]

    queries = [
        query_1(specific_graduate_course),
        query_2(),
    ]

    for query in queries[1:]:
        start_time = time.time()
        result = query.evaluate()
        end_time = time.time()
        print(end_time - start_time)
