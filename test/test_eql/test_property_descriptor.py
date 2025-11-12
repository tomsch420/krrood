from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from typing_extensions import Set, Type

from krrood.class_diagrams.utils import Role
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
    member_of: List[Company] = field(default_factory=list)

    def __hash__(self):
        return hash(self.name)


@dataclass
class CEO(Role[Person], Symbol):
    person: Person
    head_of: Company = None

    def __hash__(self):
        return hash(self.person)


@dataclass
class Member(PropertyDescriptor, HasInverseProperty):

    @classmethod
    def get_inverse(cls) -> Type[MemberOf]:
        return MemberOf


@dataclass
class MemberOf(PropertyDescriptor, HasInverseProperty):
    @classmethod
    def get_inverse(cls) -> Type[Member]:
        return Member


@dataclass
class WorksFor(MemberOf):
    pass


@dataclass
class HeadOf(WorksFor):
    pass


@dataclass
class SubOrganizationOf(PropertyDescriptor, TransitiveProperty): ...


Person.works_for = WorksFor(Person, "works_for")
Person.member_of = MemberOf(Person, "member_of")
CEO.head_of = HeadOf(CEO, "head_of")
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


def test_set_container_property():
    company = Company(name="BassCo")
    company2 = Company(name="AnotherBassCo")
    person1 = Person(name="Bass1")
    person2 = Person(name="Bass2")

    # test direct setting of a set
    company.members = {person1, person2}
    assert person1 in company.members
    assert person2 in company.members
    assert company in person1.member_of
    assert company in person2.member_of
    assert person1.works_for != company
    assert person2.works_for != company

    person1.member_of.append(company2)
    assert company2 in person1.member_of
    assert person1 in company2.members
    assert person1.works_for != company2


def test_setting_a_role_affects_role_taker():
    company = Company(name="BassCo")
    person1 = Person(name="Bass1")
    ceo1 = CEO(person1)

    ceo1.head_of = company
    assert ceo1.head_of == company
    assert ceo1.person.works_for == company
    assert ceo1 in company.members
    assert company in ceo1.person.member_of
