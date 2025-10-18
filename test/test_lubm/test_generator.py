import time

from krrood.entity_query_language.entity import (
    let,
    entity,
    an,
    contains,
    the,
    set_of,
    or_,
    and_,
)
from krrood.entity_query_language.predicate import Predicate, HasType
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.experiments.generator import UniversityDataGenerator
from krrood.experiments.lubm import (
    University,
    Student,
    GraduateStudent,
    GraduateCourse,
    Department,
    Publication,
    Professor,
    Person,
    FacultyMember,
    Course,
    UndergraduateStudent,
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


def query_3(specific_professor):
    """
    Get all publications that have a specific professor as author.
    """
    with symbolic_mode():
        publication = let(Publication, domain=specific_professor.publications)
        query = an(
            entity(
                publication,
            )
        )
    return query


def query_4(specific_university):
    """
    Select all professors that work for a specific university.
    Get the professor, the name, the email-address, and the telephone-number.
    """
    with symbolic_mode():
        professor = let(Professor)
        department = let(Department)
        query = an(
            set_of(
                (professor, professor.person.last_name),
                contains(department.all_professors, professor),
                department.university == specific_university,
            )
        )
    return query


def query_5(specific_university):
    """
    Get all persons that are members of a specific university.
    """
    with symbolic_mode():
        faculty_member = let(FacultyMember)
        query = an(
            entity(
                faculty_member.person,
                faculty_member.department.university == specific_university,
            )
        )
    return query


def query_6():
    """
    Get all students.
    """
    with symbolic_mode():
        student = let(Student)
        query = an(
            entity(
                student,
            )
        )
    return query


def query_7(specific_professor):
    """
    Get all students and courses where the student takes a course given by a specific professor.
    """
    with symbolic_mode():
        student = let(Student)
        course = let(Course)
        query = an(
            set_of(
                (student, course),
                contains(specific_professor.teaches_courses, course),
                or_(
                    and_(
                        HasType(student, GraduateStudent),
                        contains(student.takes_graduate_courses, course),
                    ),
                    and_(
                        HasType(student, UndergraduateStudent),
                        contains(student.takes_courses, course),
                    ),
                ),
            )
        )
    return query


def test_ood_querying(university_data):

    university: University = university_data[0]

    specific_graduate_course = university.departments[0].graduate_courses[0]
    specific_professor = university.departments[0].all_professors[0]

    queries = [
        query_1(specific_graduate_course),
        query_2(),
        query_3(specific_professor),
        query_4(university),
        query_5(university),
        query_6(),
        query_7(specific_professor),
    ]

    for query in queries[6:]:
        start_time = time.time()
        result = len(list(query.evaluate()))
        end_time = time.time()
        print(end_time - start_time)
        print("Number of rows", result)
