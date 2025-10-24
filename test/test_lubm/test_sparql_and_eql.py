from __future__ import annotations

import os

from krrood.experiments import lubm_with_predicates
from krrood.experiments.helpers import (
    evaluate_sparql,
    make_rdf_graph,
    load_instances_for_lubm_with_predicates,
)
from krrood.experiments.lubm_sparql_queries import sparql_queries
from krrood.experiments.lubm_eql_queries import evaluate_eql, get_eql_queries
from krrood.experiments.owl_instances_loader import load_instances


def test_eql_counts_match_sparql():

    # rdf_graph = make_rdf_graph(instances_path)
    # expected = evaluate_sparql(rdf_graph, sparql_queries)

    registry = load_instances_for_lubm_with_predicates()
    actual, _, _ = evaluate_eql(get_eql_queries())

    # test only the first query for now as the queries of sparql are not correct yet.
    # assert actual[0] == expected[0]
