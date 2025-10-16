from dataclasses import dataclass
from typing_extensions import List

from ..predicate import Predicate
from ..symbol_graph import SymbolGraph, WrappedInstance, PredicateRelation
from ...ormatic.dao import AlternativeMapping, T


@dataclass
class SymbolGraphMapping(AlternativeMapping[SymbolGraph]):

    instances: List[WrappedInstance]

    predicate_relations: List[PredicateRelation]

    @classmethod
    def create_instance(cls, obj: SymbolGraph):
        return cls(
            instances=obj.wrapped_instances,
            predicate_relations=list(obj.relations()),
        )

    def create_from_dao(self) -> T:
        result = Predicate.build_symbol_graph()
        for instance in self.instances:
            result.add_instance(instance)
        for relation in self.predicate_relations:
            result.add_relation(relation)
        return result
