from krrood.entity_query_language import Predicate


def test_visualize_symbol_graph():
    Predicate.build_symbol_graph()
    assert len(Predicate.symbol_graph._type_graph.wrapped_classes) == 16
    Predicate.symbol_graph._type_graph.visualize()
