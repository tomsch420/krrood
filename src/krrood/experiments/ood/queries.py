from ...entity_query_language.entity import let, an, entity, contains, set_of, or_, not_
from ...entity_query_language.symbolic import symbolic_mode
from ...experiments.ood.lubm import (
    Student,
    University,
    Department,
    Publication,
    Professor,
    FacultyMember,
    Course,
    exists,
    ResearchGroup,
    Person,
)


def query_1(specific_graduate_course):
    """
    Select all graduate students that take the given graduate course.
    """
    with symbolic_mode():
        graduate_student = let(Student)

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
        graduate_student = let(Student)
        query = an(
            set_of(
                (
                    graduate_student,
                    graduate_student.department.university,
                    graduate_student.department,
                ),
                graduate_student.takes_any_graduate_courses,
                graduate_student.undergraduate_degree_from
                == graduate_student.department.university,
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
        query = an(
            set_of(
                (professor, professor.person.last_name),
                professor.department.university == specific_university,
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
        query = an(
            set_of(
                (student, course),
                contains(specific_professor.teaches_courses, course),
                or_(
                    contains(student.takes_graduate_courses, course),
                    contains(student.takes_courses, course),
                ),
            ),
        )

    return query


def query_8(specific_university):
    """
    Get all students that are members of a specific university's departments.
    Extract the student, the department, and the email address.
    """
    with symbolic_mode():
        student = let(Student)
        query = an(
            set_of(
                (student, student.department, student.person.first_name),
                student.department.university == specific_university,
            )
        )
    return query


def query_9():
    """
    Get all students that take a course given by their advisor.
    """
    with symbolic_mode():
        student = let(Student)
        course = let(Course)
        query = an(
            set_of(
                (student, student.advisor, course),
                student.takes_any_graduate_courses,
                contains(student.advisor.teaches_graduate_courses, course),
                contains(student.takes_graduate_courses, course),
            )
        )
    return query


def query_10():
    """
    Get all students that take a graduate course.
    """
    with symbolic_mode():
        student = let(Student)
        query = an(entity(student, student.takes_any_graduate_courses))
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
        department = let(Department, domain=specific_university.departments)
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
    Get all people who got a degree from the specific university.
    """
    with symbolic_mode():
        faculty_member = let(FacultyMember)
        student = let(Student)
        q1 = an(
            entity(
                faculty_member.person,
                or_(
                    faculty_member.undergraduate_degree_from == specific_university,
                    faculty_member.masters_degree_from == specific_university,
                    faculty_member.doctoral_degree_from == specific_university,
                ),
            )
        )
        q2 = an(
            entity(
                student.person,
                student.undergraduate_degree_from == specific_university,
            )
        )
        query = an(entity(faculty_member.person, or_(q1, q2)))
    return query


def query_14():
    """
    Get all undergrad students.
    """
    with symbolic_mode():
        student = let(Student)
        query = an(entity(student), not_(student.takes_any_graduate_courses))
    return query
