from __future__ import annotations

from dataclasses import dataclass

from krrood.entity_query_language import symbolic_mode, Predicate
from krrood.experiments.lubm_with_predicates import (
    Organization,
    Person,
    Employee,
    MemberOf,
    SubOrganizationOf,
    WorksFor,
)


@dataclass
class Company(Organization):
    def __hash__(self) -> int:
        return id(self)


Predicate.build_symbol_graph()


def test_query_on_descriptor_field_filters():
    org1 = Organization("ACME")
    org2 = Company("ABC")

    people = [
        Employee("John"),
        Employee("Jane"),
    ]
    people[0].works_for = [org1]
    people[1].works_for = [org2]

    with symbolic_mode():
        with Employee() as employee:
            WorksFor(Organization("ACME"))
    results = list(employee.evaluate())
    assert [p.name for p in results] == ["John"]


def test_query_on_descriptor_inheritance():
    org1 = Organization("ACME")
    org2 = Company("ABC")

    people = [
        Employee("John"),
        Employee("Jane"),
    ]
    people[0].works_for = [org1]
    people[1].works_for = [org2]

    with symbolic_mode():
        with Person() as person:
            MemberOf(Organization("ACME"))
    results = list(person.evaluate())
    assert [p.name for p in results] == ["John"]


def test_query_on_descriptor_transitivity():
    org1 = Organization("ACME")
    org2 = Company("ACME_sub")
    org3 = Organization("ACME_sub_sub")
    org2.sub_organization_of = [org1]
    org3.sub_organization_of = [org2]

    Predicate.symbol_graph.to_dot(
        "instance_graph.pdf", format="pdf", graph_type="instance"
    )

    with symbolic_mode():
        with Organization() as my_org:
            SubOrganizationOf(org1)

    results = list(my_org.evaluate())
    Predicate.symbol_graph.to_dot(
        "instance_graph_inferred.pdf", format="pdf", graph_type="instance"
    )
    assert {p.name for p in results} == {"ACME_sub", "ACME_sub_sub"}
