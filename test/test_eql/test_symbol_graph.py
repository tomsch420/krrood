import os
import time

import pytest

from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.entity_query_language.symbolic import symbolic_mode
from ..dataset import semantic_world_like_classes
from ..dataset.example_classes import Position
from krrood.class_diagrams.utils import classes_of_module
from krrood.entity_query_language.entity import an, entity, let

try:
    import pydot
    import pygraphviz
except ImportError:
    pydot = None
    pygraphviz = None


@pytest.mark.skipif(
    not (pydot and pygraphviz), reason="pydot and graphviz not installed"
)
def test_visualize_symbol_graph():
    SymbolGraph().clear()
    symbol_graph = SymbolGraph()
    symbol_graph.to_dot("symbol_graph.svg", format="svg", graph_type="type")
    assert len(symbol_graph._type_graph.wrapped_classes) == 14
    if os.path.exists("symbol_graph.svg"):
        os.remove("symbol_graph.svg")


@pytest.mark.skip
def test_memory_leak():
    """
    Test if the SymbolGraph does not artificially keep objects alive that would be garbage collected.
    """

    def create_data():
        point = Position(1, 2, 3)

    create_data()
    time.sleep(1)
    with symbolic_mode():
        q = an(entity(let(Position)))
    assert list(q.evaluate()) == []
