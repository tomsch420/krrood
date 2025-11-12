from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest
from typing_extensions import Set, Type

from krrood.entity_query_language.mixins import HasInverseProperty, TransitiveProperty
from krrood.entity_query_language.predicate import Symbol
from krrood.entity_query_language.property_descriptor import PropertyDescriptor
from krrood.entity_query_language.symbol_graph import SymbolGraph


@dataclass
class Company(Symbol):
    name: str
    members: Set[Person] = field(default_factory=set)
    sub_organization_of: Company = None

    def __hash__(self):
        return hash(self.name)


@dataclass
class Person(Symbol):
    name: str
    works_for: Company = None

    def __hash__(self):
        return hash(self.name)


@dataclass
class Member(PropertyDescriptor):
    pass


@dataclass
class MemberOf(PropertyDescriptor, HasInverseProperty):
    @classmethod
    def get_inverse(cls) -> Type[Member]:
        return Member


@dataclass
class WorksFor(MemberOf):
    pass


@dataclass
class SubOrganizationOf(PropertyDescriptor, TransitiveProperty): ...


Person.works_for = WorksFor(Person, "works_for")
Company.members = Member(Company, "members")
Company.sub_organization_of = SubOrganizationOf(Company, "sub_organization_of")

SymbolGraph().clear()
SymbolGraph()


def test_set_non_container_property():
    company = Company(name="BassCo")
    person1 = Person(name="Bass1")

    person1.works_for = company
    assert person1.works_for == company
    assert person1 in company.members

    person2 = Person(name="Bass2")
    another_company = Company(name="AnotherBassCo")
    person2.works_for = another_company
    assert person2.works_for == another_company
    assert person2 in another_company.members
    assert person2 not in company.members
