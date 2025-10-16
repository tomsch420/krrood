from dataclasses import dataclass, field
from typing import List

import pytest
from sqlalchemy import select

from krrood.entity_query_language.predicate import Thing, PropertyDescriptor, Predicate
from krrood.entity_query_language.orm.ormatic_interface import (
    Base as EQLBase,
    SymbolGraphMappingDAO,
)


# We intentionally reuse the project's engine/session fixtures.
# The dataset Base is bound to the same engine, so we only need to
# create the EQL SymbolGraph ORM tables in our tests.


@dataclass
class Person(Thing):
    name: str
    friends: List["Person"] = field(default_factory=list)
    friend: PropertyDescriptor["Person"] = field(default_factory=PropertyDescriptor)


@dataclass
class Company(Thing):
    name: str
    employees: List[Person] = field(default_factory=list)
    hasEmployee: PropertyDescriptor[Person] = field(default_factory=PropertyDescriptor)


@pytest.mark.usefixtures("database")
def test_symbol_graph_persistence_roundtrip(session, engine):
    # Ensure the EQL ORM tables exist for this engine
    EQLBase.metadata.create_all(engine)

    # Fresh symbol graph for predictable state
    Predicate.build_symbol_graph([Person, Company])

    # Create objects and relations tracked by the SymbolGraph via PropertyDescriptors
    alice = Person(name="Alice")
    bob = Person(name="Bob")

    # Using the descriptor automatically records the relation in the SymbolGraph
    alice.friend = bob  # direct relation

    # Also add an inferred relation explicitly
    Person.friend.add_relation(bob, alice, inferred=True)

    # Sanity checks on original graph
    original_nodes = len(Predicate.symbol_graph.wrapped_instances)
    original_edges = len(list(Predicate.symbol_graph.relations()))
    assert original_nodes == 2
    assert original_edges == 2  # one direct, one inferred

    # Persist the SymbolGraph through the AlternativeMapping DAO
    mapping_dao = SymbolGraphMappingDAO.to_dao(Predicate.symbol_graph)
    session.add(mapping_dao)
    session.commit()

    # Load back from the database and reconstruct the SymbolGraph
    loaded_mapping_dao = session.scalars(select(SymbolGraphMappingDAO)).one()
    reloaded_graph = loaded_mapping_dao.from_dao()

    # Validate node and edge counts
    assert len(reloaded_graph.wrapped_instances) == original_nodes
    edges = list(reloaded_graph.relations())
    assert len(edges) == original_edges

    # Validate that at least one relation is flagged as inferred and that
    # predicates survived the round-trip as PropertyDescriptor-based relations
    assert any(e.inferred for e in edges)
    assert all(hasattr(e, "predicate") for e in edges)
    assert all(isinstance(e.predicate, PropertyDescriptor) for e in edges)


@pytest.mark.usefixtures("database")
def test_symbol_graph_persistence_with_multiple_predicates(session, engine):
    # Ensure the EQL ORM tables exist for this engine
    EQLBase.metadata.create_all(engine)

    # Fresh symbol graph for predictable state
    Predicate.build_symbol_graph([Person, Company])

    # Create objects
    acme = Company(name="ACME")
    alice = Person(name="Alice")
    bob = Person(name="Bob")

    # Establish two different kinds of relations using different descriptors
    acme.hasEmployee.add_relation(acme, [alice, bob])
    alice.friend = bob

    # Persist
    mapping_dao = SymbolGraphMappingDAO.to_dao(Predicate.symbol_graph)
    session.add(mapping_dao)
    session.commit()

    # Load and reconstruct
    loaded_mapping_dao = session.scalars(select(SymbolGraphMappingDAO)).one()
    reloaded_graph = loaded_mapping_dao.from_dao()

    # Validate: we should have 3 instances (company + 2 persons)
    assert len(reloaded_graph.wrapped_instances) == 3

    # We should have 3 edges: 2 employees + 1 friendship
    edges = list(reloaded_graph.relations())
    assert len(edges) == 3
    assert all(isinstance(e.predicate, PropertyDescriptor) for e in edges)
