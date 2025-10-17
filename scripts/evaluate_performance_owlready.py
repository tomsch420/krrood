import os.path

import owlready2
import krrood.experiments.lubm_sparql_queries

path_to_ontologies = os.path.join(
    os.path.dirname(__file__), "..", "resources", "instances"
)

world = owlready2.World()

for f in os.listdir(path_to_ontologies):
    if f.endswith(".owl"):
        onto = world.get_ontology(
            f"file://{os.path.join(path_to_ontologies, f)}"
        ).load()

owlready2.sync_reasoner_pellet(
    world, infer_property_values=True, infer_data_property_values=True
)

path_to_answers = os.path.join(path_to_ontologies, "..", "query_answers")

for answer_file, query in zip(
    sorted(
        os.listdir(path_to_answers), key=lambda x: int("".join(filter(str.isdigit, x)))
    ),
    krrood.experiments.lubm_sparql_queries.sparql_queries,
):
    print(query)
    answer_file = os.path.join(path_to_answers, answer_file)
    with open(answer_file, "r") as f:
        lines = f.readlines()
        row_count = len([line for line in lines if line.strip()])

    answers_owlready = list(world.sparql(query))
    assert (
        len(answers_owlready) == row_count - 1
    ), f"{answer_file} has {row_count} answers, owlready2 got {len(answers_owlready)} answers"
