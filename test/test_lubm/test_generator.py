import time

from krrood.entity_query_language.entity import let, entity, an, contains, the
from krrood.entity_query_language.predicate import Predicate
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.experiments.generator import UniversityDataGenerator
from krrood.experiments.lubm import University, Student, GraduateStudent, GraduateCourse


def test_generator():
    Predicate.build_symbol_graph()
    generator = UniversityDataGenerator(university_count=1, seed=123)
    universities = generator.generate()

    university: University = universities[0]

    course = university.departments[0].graduate_courses[0]

    with symbolic_mode():
        graduate_student = let(GraduateStudent)
        graduate_course = let(GraduateCourse)

        specific_graduate_course = the(
            entity(graduate_course),
            graduate_course == course,
        )

        q1 = an(
            entity(
                graduate_student,
                contains(
                    graduate_student.takes_graduate_courses, specific_graduate_course
                ),
            )
        )

    start_time = time.time()
    q1.evaluate()
    end_time = time.time()
    print(end_time - start_time)
