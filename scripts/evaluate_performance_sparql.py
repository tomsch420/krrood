import os

from krrood.experiments.helpers import evaluate_sparql, make_rdf_graph
from krrood import sparql_queries


if __name__ == "__main__":
    graph = make_rdf_graph(os.path.join("..", "resources", "lubm_instances.owl"))
    evaluate_sparql(graph, sparql_queries)
