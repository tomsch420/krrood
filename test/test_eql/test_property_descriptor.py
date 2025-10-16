from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from krrood.entity_query_language.predicate import PropertyDescriptor, Thing
from test_class_diagram.test_wrapped_field import get_field_by_name


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
    assert isinstance(person2.worksForOrg, WorksFor)

    works_for_org_field = get_field_by_name(Person, "worksForOrg")
    # Domain types and range types
    assert Person in works_for_org_field.default_factory().domain_types
    assert Organization in works_for_org_field.default_factory().range_types
    # WorksFor on Person and Employee share class variables
    works_for_company_field = get_field_by_name(Person, "worksForCompany")
    assert (
        works_for_company_field.default_factory().domain_types == WorksFor.domain_types
    )


def test_nullable_and_name_attributes():
    # The range types contain no None by default
    works_for_org_field = get_field_by_name(Person, "worksForOrg")
    wf = works_for_org_field.default_factory()
    assert wf.nullable is False
    assert wf.name == "worksFor"
