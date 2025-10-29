import os

import pytest

try:
    from rustworkx_utils import GraphVisualizer
except ImportError:
    GraphVisualizer = None

from ..dataset.semantic_world_like_classes import (
    Drawer,
    Handle,
    FixedConnection,
    Body,
    Container,
    PrismaticConnection,
    RevoluteConnection,
    View,
    Door,
    Wardrobe,
)
from krrood.entity_query_language.entity import (
    entity,
    infer,
    symbolic_mode,
    let,
    an,
)
from krrood.entity_query_language.conclusion import Add
from krrood.entity_query_language.symbolic import rule_mode
from krrood.entity_query_language.predicate import HasType
from krrood.entity_query_language.rule import alternative


@pytest.mark.skipif(GraphVisualizer is None, reason="requires rustworkx_utils")
def test_render_rx_graph_as_igraph_simple(handles_and_containers_world):
    world = handles_and_containers_world
    with rule_mode():
        fixed_connection = let(FixedConnection, world.connections)
        container = fixed_connection.parent
        handle = fixed_connection.child
        rule = infer(
            entity(
                Drawer(handle=handle, container=container, world=world),
                HasType(handle, Handle),
            )
        )
    drawers = list(rule.evaluate())
    if os.path.exists("pdf_graph.pdf"):
        os.remove("pdf_graph.pdf")
    rule.visualize()
    assert os.path.exists("pdf_graph.pdf")
    os.remove("pdf_graph.pdf")


@pytest.mark.skipif(GraphVisualizer is None, reason="requires rustworkx_utils")
def test_render_rx_graph_as_igraph_complex(doors_and_drawers_world):
    world = doors_and_drawers_world
    with symbolic_mode():
        body = let(Body, domain=world.bodies)
        handle = let(Handle, domain=world.bodies)
        container = let(Container, domain=world.bodies)

        fixed_connection = an(
            entity(
                f := let(FixedConnection, domain=world.connections),
                f.parent == body,
                f.child == handle,
            )
        )
        prismatic_connection = an(
            entity(
                p := let(PrismaticConnection, domain=world.connections), p.child == body
            )
        )
        revolute_connection = an(
            entity(
                r := let(RevoluteConnection, domain=world.connections),
                r.parent == body,
                r.child == handle,
            )
        )
        rule = infer(views := View(), fixed_connection, prismatic_connection)

    with rule_mode(rule):
        Add(views, Drawer(handle=handle, container=body, world=world))
        with alternative(revolute_connection):
            Add(views, Door(handle=handle, body=body, world=world))
        with alternative(
            fixed_connection,
            body == revolute_connection.child,
            container == revolute_connection.parent,
            revolute_connection.world == world,
        ):
            Add(
                views,
                Wardrobe(handle=handle, body=body, container=container, world=world),
            )
    results = list(rule.evaluate())
    if os.path.exists("pdf_graph.pdf"):
        os.remove("pdf_graph.pdf")
    rule.visualize()
    assert os.path.exists("pdf_graph.pdf")
    os.remove("pdf_graph.pdf")
