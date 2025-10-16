from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from krrood.entity_query_language import symbolic_mode, in_, a
from krrood.entity_query_language.predicate import PropertyDescriptor, Thing
from krrood.entity_query_language import From


@dataclass
class MemberOf(PropertyDescriptor): ...


@dataclass
class WorksFor(MemberOf): ...


@dataclass(unsafe_hash=True)
class Organization(Thing):
    name: str


@dataclass(unsafe_hash=True)
class Company(Organization): ...


@dataclass(eq=False)
class Person(Thing):
    name: str


@dataclass(eq=False)
class Employee(Person):
    works_for: List[Organization] = field(default_factory=WorksFor)


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
            person := Employee(From(people)), MemberOf(person, Organization("ACME"))
        )
    results = list(query.evaluate())
    assert [p.name for p in results] == ["John"]
