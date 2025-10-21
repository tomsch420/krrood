import os.path
import time

import numpy as np
from SPARQLWrapper import SPARQLWrapper, JSON

import krrood.experiments.lubm_sparql_queries

# -------------------------
# SPARQL endpoint variable
# -------------------------
SPARQL_API = "http://localhost:7200/repositories/KRROOD"  # change to your endpoint


def run_query(query, query_name):
    """Run a SPARQL query and print results with timing."""
    print(f"\n=== Running {query_name} ===")

    sparql = SPARQLWrapper(SPARQL_API)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    start_time = time.time()
    results = sparql.query().convert()
    end_time = time.time()

    elapsed = end_time - start_time

    return results, elapsed


path_to_ontologies = os.path.join(
    os.path.dirname(__file__), "..", "resources", "instances"
)
#
# graph = Graph()
#
# for f in os.listdir(path_to_ontologies):
#     if f.endswith(".owl"):
#         graph.parse(os.path.join(path_to_ontologies, f), format="xml")

path_to_answers = os.path.join(path_to_ontologies, "..", "query_answers")

query_times = {}

for answer_file, query in zip(
    sorted(
        os.listdir(path_to_answers), key=lambda x: int("".join(filter(str.isdigit, x)))
    ),
    krrood.experiments.lubm_sparql_queries.sparql_queries,
):

    answer_file_full_path = os.path.join(path_to_answers, answer_file)
    with open(answer_file_full_path, "r") as f:
        lines = f.readlines()
        row_count = len([line for line in lines if line.strip()])

    current_query_times = []
    for i in range(10):
        answers_in_memory, elapsed = run_query(query, answer_file)
        current_query_times.append(elapsed)

    answers_in_memory_count = len(answers_in_memory["results"]["bindings"])
    assert (
        answers_in_memory_count == row_count - 1
    ), f"{answer_file} has {row_count} answers, SPARQLWrapper got {answers_in_memory_count} answers"

    query_times[answer_file] = current_query_times

print("Average Query times", {k: np.mean(v) for k, v in query_times.items()})
