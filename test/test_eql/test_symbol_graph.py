import os

import pytest

from krrood.entity_query_language.symbol_graph import SymbolGraph
from ..dataset import semantic_world_like_classes
from krrood.class_diagrams.utils import classes_of_module

try:
    import pydot
    import pygraphviz
except ImportError:
    pydot = None
    pygraphviz = None


@pytest.mark.skipif(not (pydot and pygraphviz), reason="pydot not installed")
def test_visualize_symbol_graph():
    SymbolGraph().clear()
    symbol_graph = SymbolGraph.build(classes_of_module(semantic_world_like_classes))
    symbol_graph.to_dot("symbol_graph.svg", format="svg", graph_type="type")
    assert len(symbol_graph._class_diagram.wrapped_classes) == 14
    if os.path.exists("symbol_graph.svg"):
        os.remove("symbol_graph.svg")
