import os
from rdflib import Graph
from owlrl import DeductiveClosure, OWLRL_Semantics

from krrood.experiments.helpers import evaluate_sparql
from krrood.experiments.lubm_sparql_queries import sparql_queries

if __name__ == "__main__":
    onto_file = os.path.abspath(os.path.join("..", "resources", "lubm_instances.owl"))

    print(f"Loading ontology from: {onto_file}")

    # Create RDFLib graph and load data
    graph = Graph()
    graph.parse(onto_file)

    # Apply OWL-RL reasoning to materialize inferred triples
    print("Applying OWL-RL reasoning...")
    DeductiveClosure(OWLRL_Semantics).expand(graph)

    # Now execute SPARQL queries on the expanded graph
    counts = []
    for q in sparql_queries:
        res = graph.query(q)
        counts.append(len(list(res)))

    print(counts)
