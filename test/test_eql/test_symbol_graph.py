import os

from krrood.entity_query_language.symbol_graph import SymbolGraph
from ..dataset import semantic_world_like_classes
from krrood.class_diagrams.utils import classes_of_module


def test_visualize_symbol_graph():
    SymbolGraph().clear()
    symbol_graph = SymbolGraph.build(classes_of_module(semantic_world_like_classes))
    symbol_graph.to_dot("symbol_graph.svg", format="svg", graph_type="type")
    assert len(symbol_graph._type_graph.wrapped_classes) == 14
    os.remove("symbol_graph.svg")
