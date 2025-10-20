import time

import pytest
import tqdm

from krrood.entity_query_language.predicate import Predicate
from krrood.experiments.ood.generator import UniversityDataGenerator
from krrood.experiments.ood.lubm import (
    University,
)
from krrood.experiments.ood.queries import (
    query_1,
    query_2,
    query_3,
    query_4,
    query_5,
    query_6,
    query_7,
    query_8,
    query_9,
    query_10,
    query_11,
    query_12,
    query_14,
    query_13,
)


@pytest.fixture(scope="session")
def university_data():
    Predicate.build_symbol_graph()
    generator = UniversityDataGenerator(university_count=1, seed=69)
    return generator.generate()


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
        query_13(university),
        query_14(),
    ]

    for index, query in enumerate(tqdm.tqdm(queries)):
        start_time = time.time()
        result = len(list(query.evaluate()))
        end_time = time.time()
        print(index + 1, "Number of rows", result, "Time elaped", end_time - start_time)
        print("=" * 80)
