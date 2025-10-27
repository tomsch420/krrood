from dataclasses import dataclass, field
from typing import List

import pytest
from sqlalchemy import select

import krrood
from krrood.entity_query_language.symbol_graph import SymbolGraph
from ..dataset.example_classes import Position
from ..dataset.sqlalchemy_interface import *
from krrood.entity_query_language.predicate import BinaryPredicate
from krrood.ormatic.dao import to_dao


def test_symbol_graph_persistence(session, database):
    p1 = Position(1, 2, 3)

    symbol_graph = SymbolGraph()
    symbol_graph_dao = to_dao(symbol_graph)
    session.add(symbol_graph_dao)
    session.commit()

    # # test the content of the database
    queried_p1 = session.scalars(select(PositionDAO)).one()

    assert p1.x == queried_p1.x
    assert p1.y == queried_p1.y
    assert p1.z == queried_p1.z

    p1_reconstructed = queried_p1.from_dao()
    assert p1 == p1_reconstructed
