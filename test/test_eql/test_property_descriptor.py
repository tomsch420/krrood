from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from krrood.entity_query_language.predicate import PropertyDescriptor, Thing


# Concrete descriptor used in tests
@dataclass
class WorksFor(PropertyDescriptor): ...


@dataclass
class Organization(Thing):
    name: str


@dataclass
class Company(Organization): ...


@dataclass
class Person(Thing):
    name: str
    worksForOrg: List[Organization] = field(default_factory=WorksFor)
    worksForCompany: List[Company] = field(default_factory=WorksFor)


@dataclass
class Employee(Person):
    worksForOrg: List[Organization] = field(default_factory=WorksFor)


def test_descriptor_stores_per_instance_values_and_metadata():
    person = Person("John")
    organization = Organization("ACME")
    company = Company("ABC Corp")

    # Per instance storage
    person.worksForOrg = [organization]
    person2 = Person("Jane")
    person2.worksForCompany = [company]

    assert person.worksForOrg == [organization]

    # setattr should work
    setattr(person2, "worksForCompany", [Company("SetAttr")])
    assert person2.worksForCompany == [Company("SetAttr")]

    # Class access returns the descriptor
    assert isinstance(person2.__class__.worksForOrg, WorksFor)

    # Domain types and range types
    assert Person in Person.worksForOrg.domain_types
    assert Organization in Person.worksForOrg.range_types
    # WorksFor on Person and Employee share class variables
    assert Person.worksForCompany.domain_types == WorksFor.domain_types


def test_nullable_and_name_attributes():
    # The range types contain no None by default
    wf = Person.worksForOrg
    assert wf.nullable is False
    assert wf.name == "worksFor"
