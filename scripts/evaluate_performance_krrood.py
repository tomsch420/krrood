import os
import time

import numpy as np
import owlready2
import tqdm

from krrood.entity_query_language.entity import entity, let, the
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.experiments.ood.lubm import University
from krrood.experiments.ood.owl_instance_loader import DatasetConverter
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
    query_13,
    query_14,
)


def evaluate_query(query):
    start_time = time.time()
    result = list(query.evaluate())
    end_time = time.time()
    elapsed_time = end_time - start_time
    return result, elapsed_time


def evaluate_eql():
    world = owlready2.World()
    path_to_instances = os.path.join(
        os.path.dirname(__file__), "..", "resources", "instances"
    )

    for filename in os.listdir(path_to_instances):
        if filename.endswith(".owl"):
            onto = world.get_ontology(
                f"file://{os.path.join(path_to_instances, filename)}"
            ).load()

    owlready2.sync_reasoner_hermit(world, infer_property_values=True)

    converter = DatasetConverter(world)
    converter.convert()

    with symbolic_mode():
        university: University = the(
            entity(u := let(University), u.name == "www.University0.edu")
        ).evaluate()

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

    query_times = {}
    for index, query in enumerate(tqdm.tqdm(queries)):
        current_query_time = []
        for i in range(10):
            result, elapsed_time = evaluate_query(query)
            current_query_time.append(elapsed_time)
        query_times[f"query_{index}"] = current_query_time

    print(
        "Average Query times",
        *{k: np.mean(v) for k, v in query_times.items()},
        sep="\n",
    )


if __name__ == "__main__":
    evaluate_eql()
