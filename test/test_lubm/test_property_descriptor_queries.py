from __future__ import annotations

from dataclasses import dataclass

from krrood.entity_query_language import symbolic_mode, in_, a
from krrood.entity_query_language import From

from krrood.experiments.lubm_with_predicates import (
    Organization,
    Person,
    Employee,
    MemberOf,
    SubOrganizationOf,
)


@dataclass
class Company(Organization):
    def __hash__(self) -> int:
        return id(self)


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
        query = a(
            person := Employee(From(people)),
            in_(Organization("ACME"), person.works_for),
        )
    results = list(query.evaluate())
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
        query = a(
            person := Person(From(people)), MemberOf(person, Organization("ACME"))
        )
    results = list(query.evaluate())
    assert [p.name for p in results] == ["John"]


def test_query_on_descriptor_transitivity():
    org1 = Organization("ACME")
    org2 = Company("ACME_sub")
    org3 = Organization("ACME_sub_sub")
    org2.sub_organization_of = [org1]
    org3.sub_organization_of = [org2]

    with symbolic_mode():
        query = a(org := Organization(), SubOrganizationOf(org, org1))
    results = list(query.evaluate())
    assert {p.name for p in results} == {"ACME_sub", "ACME_sub_sub"}
