import time

import tqdm

from krrood.entity_query_language.entity import (
    let,
    entity,
    an,
    contains,
    the,
    set_of,
    or_,
    and_,
    a,
    flatten,
)
from krrood.entity_query_language.predicate import Predicate, HasType, HasTypes
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
    ResearchGroup,
    exists,
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
        course = let(Course, domain=specific_professor.teaches_courses)
        graduate_student = a(
            gs := GraduateStudent(), contains(gs.takes_graduate_courses, course)
        )
        undergraduate_student = a(
            us := UndergraduateStudent(), contains(us.takes_courses, course)
        )
        query = an(
            set_of(
                (student, course),
                or_(graduate_student, undergraduate_student),
            )
        )
    query.visualize()
    return query


def query_8(specific_university):
    """
    Get all students that are members of a specific university's departments.
    Extract the student, the department, and the email address.
    """
    with symbolic_mode():
        student = let(Student)
        department = let(Department, domain=specific_university.departments)
        query = an(
            set_of(
                (student, department, student.person.first_name),
                student.department == department,
                department.university == specific_university,
            )
        )
    return query


def query_9():
    """
    Get all students that take a course given by their advisor.
    """
    with symbolic_mode():
        student = let(GraduateStudent)
        professor = let(Professor)
        course = let(Course)
        query = an(
            set_of(
                (student, professor, course),
                student.advisor == professor,
                contains(professor.teaches_graduate_courses, course),
                contains(student.takes_graduate_courses, course),
            )
        )
    return query


def query_10():
    """
    Get all students that take a graduate course.
    """
    with symbolic_mode():
        student = let(GraduateStudent)
        query = an(entity(student, exists(student.takes_graduate_courses)))
    return query


def query_11(university: University):
    """
    Get all research groups that are suborganizations of a specific university.
    """
    with symbolic_mode():
        research_group = let(ResearchGroup)
        query = an(
            entity(
                research_group,
                research_group.department.university == university,
            )
        )
    return query


def query_12(specific_university: University):
    """
    Get all heads and departments where the head works for the department of a specific university.
    """
    with symbolic_mode():
        head = let(Professor)
        department = let(Department)
        query = an(
            set_of(
                (head, department),
                department.head == head,
                department.university == specific_university,
            )
        )
    return query


def query_13(specific_university: University):
    """
    Get all alumni of a specific university.
    This needs the random data generator to be able to generate Alumni
    """
    raise NotImplementedError


def query_14():
    """
    Get all undergrad students.
    """
    with symbolic_mode():
        student = let(UndergraduateStudent)
        query = an(entity(student))
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
        query_8(university),
        query_9(),
        query_10(),
        query_11(university),
        query_12(university),
        query_14(),
    ]

    for query in tqdm.tqdm(queries):
        start_time = time.time()
        result = len(list(query.evaluate()))
        end_time = time.time()
        print(end_time - start_time)
        print("Number of rows", result)
