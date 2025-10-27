import os

from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.entity_query_language.symbolic import Variable
from krrood.experiments import lubm_with_predicates
from krrood.class_diagrams.utils import classes_of_module
from krrood.entity_query_language.predicate import Predicate


def test_visualize_symbol_graph():
    SymbolGraph().clear()
    symbol_graph = SymbolGraph.build(classes_of_module(lubm_with_predicates))
    # Predicate.symbol_graph._type_graph.visualize(
    #     figsize=(80, 50),
    #     layout="layered",
    #     edge_style="straight",
    #     spacing_x=40,
    #     spacing_y=10,
    # )
    symbol_graph.to_dot("symbol_graph.svg", format="svg", graph_type="type")
    assert len(symbol_graph._type_graph.wrapped_classes) == 67
    # os.remove("symbol_graph.svg")
