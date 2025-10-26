from __future__ import annotations

from dataclasses import dataclass

from krrood.class_diagrams.utils import classes_of_module
from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.entity_query_language.symbolic import symbolic_mode, Variable
from krrood.entity_query_language.predicate import Predicate
from krrood.experiments.lubm_with_predicates import (
    Organization,
    Person,
    Employee,
    MemberOf,
    SubOrganizationOf,
    WorksFor,
)
import krrood.experiments.lubm_with_predicates as lubm_with_predicates


@dataclass
class Company(Organization):
    def __hash__(self) -> int:
        return id(self)


SymbolGraph().clear()
SymbolGraph.build(classes=classes_of_module(lubm_with_predicates) + [Company])


def test_query_on_descriptor_field_filters():
    org1 = Organization(name="ACME")
    org2 = Company(name="ABC")

    people = [
        Employee(Person(name="John")),
        Employee(Person(name="Jane")),
    ]

    people[0].works_for = [org1]
    people[1].works_for = [org2]

    with symbolic_mode():
        with Employee() as employee:
            WorksFor(org1)
    results = list(employee.evaluate())
    assert [p.person.name for p in results] == ["John"]


def test_query_on_descriptor_inheritance():
    org1 = Organization(name="ACME")
    org2 = Company(name="ABC")

    people = [
        Employee(Person(name="John")),
        Employee(Person(name="Jane")),
    ]
    people[0].works_for = [org1]
    people[1].works_for = [org2]

    with symbolic_mode():
        with Person() as person:
            MemberOf(org1)
    results = list(person.evaluate())
    assert [p.name for p in results] == ["John"]


def test_query_on_descriptor_transitivity():
    org1 = Organization(name="ACME")
    org2 = Company(name="ACME_sub")
    org3 = Organization(name="ACME_sub_sub")
    org2.sub_organization_of = [org1]
    org3.sub_organization_of = [org2]

    SymbolGraph().to_dot("instance_graph.pdf", format="pdf", graph_type="instance")

    with symbolic_mode():
        with Organization() as my_org:
            SubOrganizationOf(org1)

    results = list(my_org.evaluate())
    SymbolGraph().to_dot(
        "instance_graph_inferred.pdf", format="pdf", graph_type="instance"
    )
    assert {p.name for p in results} == {"ACME_sub", "ACME_sub_sub"}
