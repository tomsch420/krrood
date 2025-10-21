from __future__ import annotations

import os
from copy import copy
from dataclasses import dataclass, field, fields
from functools import cached_property

from rustworkx import PyDiGraph
from typing_extensions import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Optional,
    List,
    Type,
    Dict,
    ClassVar,
    Set,
)

from .attribute_introspector import DescriptorAwareIntrospector
from .utils import recursive_subclasses
from .. import logger
from ..class_diagrams import ClassDiagram, Relation
from ..class_diagrams.wrapped_field import WrappedField

if TYPE_CHECKING:
    from .predicate import Predicate, Symbol


@dataclass
class PredicateRelation(Relation):
    source: WrappedInstance
    target: WrappedInstance
    predicate: Predicate
    inferred: bool = False

    def __str__(self):
        return self.predicate.__class__.__name__

    @property
    def color(self) -> str:
        return "red" if self.inferred else "black"


@dataclass
class WrappedInstance:
    instance: Symbol
    index: Optional[int] = field(init=False, default=None)
    _symbol_graph_: Optional[SymbolGraph] = field(
        init=False, hash=False, default=None, repr=False
    )
    inferred: bool = False

    @cached_property
    def fields(self) -> List[WrappedField]:
        return [WrappedField(self.instance, f) for f in fields(self.instance)]

    @property
    def name(self):
        return self.instance.__class__.__name__ + str(self.index)

    @property
    def color(self) -> str:
        return "red" if self.inferred else "black"

    def __eq__(self, other):
        return self.instance == other.instance

    def __hash__(self):
        try:
            return hash(self.instance)
        except TypeError:
            return id(self.instance)


@dataclass
class SymbolGraph:
    """
    A more encompassing class diagram that includes relations between classes other than inheritance and associations.
    Relations are represented as edges where each edge has a relation object attached to it. The relation object
    contains also the Predicate object that represents the relation.
    """

    _type_graph: Optional[ClassDiagram] = field(default=None)
    _instance_graph: PyDiGraph[WrappedInstance, PredicateRelation] = field(
        default_factory=PyDiGraph
    )
    _instance_index: Dict = field(default_factory=dict, init=False, repr=False)
    _relation_index: Dict[type, set[tuple[int, int]]] = field(
        default_factory=dict, init=False, repr=False
    )
    _current_graph: ClassVar[Optional[SymbolGraph]] = None
    _initialized: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs):
        if cls._current_graph is None:
            cls._current_graph = super().__new__(cls)
        return cls._current_graph

    def __init__(self, type_graph: Optional[ClassDiagram] = None):
        if not self._initialized:
            self._type_graph = type_graph or ClassDiagram([])
            self._instance_graph = PyDiGraph()
            self._instance_index = {}
            self._relation_index = {}
            self.__class__._initialized = True

    def get_role_takers_of_instance(self, instance: Any) -> Iterable[Any]:
        """
        :param instance: The instance to get the role takers for.
        :return: Role takers of the given instance. A role taker is a field that represents
         a one-to-one relationship and is not optional.
        """
        wrapped_instance = self.get_wrapped_instance(instance)
        if not wrapped_instance:
            raise ValueError(f"Instance {instance} not found in graph.")
        for role_taker_assoc in self.type_graph.get_role_taker_associations_of_cls(
            type(wrapped_instance.instance)
        ):
            yield getattr(wrapped_instance.instance, role_taker_assoc.field.public_name)

    @property
    def type_graph(self) -> ClassDiagram:
        return self._current_graph._type_graph

    def add_node(self, wrapped_instance: WrappedInstance) -> None:
        if not isinstance(wrapped_instance, WrappedInstance):
            wrapped_instance = WrappedInstance(wrapped_instance)
        wrapped_instance.index = self._instance_graph.add_node(wrapped_instance)
        wrapped_instance._symbol_graph_ = self
        self._instance_index[id(wrapped_instance.instance)] = wrapped_instance

    def get_wrapped_instance(self, instance: Any) -> Optional[WrappedInstance]:
        if isinstance(instance, WrappedInstance):
            return instance
        return self._instance_index.get(id(instance), None)

    def get_cls_associations(self, cls: Type) -> List[WrappedField]:
        if self._type_graph is None:
            return []
        wrapped_cls = self._type_graph.get_wrapped_class(cls)
        if wrapped_cls is None:
            return []
        return self._type_graph.g

    def clear(self):
        self._type_graph.clear()
        self._instance_graph.clear()
        self._instance_index.clear()
        self.__class__._current_graph = None
        self.__class__._initialized = False

    # Adapters to align with ORM alternative mapping expectations
    def add_instance(self, wrapped_instance: WrappedInstance) -> None:
        """Add a wrapped instance to the graph.

        This is an adapter that delegates to add_node to keep API compatibility with
        SymbolGraphMapping.create_from_dao.
        """
        self.add_node(wrapped_instance)

    def add_relation(self, relation: PredicateRelation) -> None:
        """Add a relation edge to the instance graph.

        This is an adapter that delegates to add_edge to keep API compatibility with
        SymbolGraphMapping.create_from_dao.
        """
        self.add_edge(relation)

    def has_edge(
        self, source: WrappedInstance, target: WrappedInstance, predicate_type: Type
    ) -> bool:
        return (source.index, target.index) in self._relation_index.get(
            predicate_type, set()
        )

    def add_edge(self, relation: PredicateRelation) -> None:
        source_out_edges = self._instance_graph.out_edges(relation.source.index)
        for _, child_idx, e in source_out_edges:
            if (
                type(e.predicate) == type(relation.predicate)
                and child_idx == relation.target.index
            ):
                return
        self._instance_graph.add_edge(
            relation.source.index, relation.target.index, relation
        )
        if type(relation.predicate) not in self._relation_index:
            self._relation_index[type(relation.predicate)] = set()
        self._relation_index[type(relation.predicate)].add(
            (relation.source.index, relation.target.index)
        )

    def relations(self) -> Iterable[PredicateRelation]:
        yield from self._instance_graph.edges()

    @property
    def wrapped_instances(self) -> List[WrappedInstance]:
        return self._instance_graph.nodes()

    def get_outgoing_neighbors_with_predicate_subclass(
        self, wrapped_instance: WrappedInstance, predicate_subclass: Type[Predicate]
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        yield from (
            self._instance_graph.get_node_data(child_idx)
            for _, child_idx, edge in self._instance_graph.in_edges(
                wrapped_instance.index
            )
            if issubclass(predicate_subclass, type(edge.predicate))
        )

    def get_incoming_neighbors_with_predicate_type(
        self, wrapped_instance: WrappedInstance, predicate_type: Type[Predicate]
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        yield from (
            self._instance_graph.get_node_data(parent_idx)
            for parent_idx, _, edge in self._instance_graph.in_edges(
                wrapped_instance.index
            )
            if isinstance(edge.predicate, predicate_type)
        )

    def get_incoming_neighbors(
        self, wrapped_instance: WrappedInstance
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        yield from (
            self._instance_graph.get_node_data(parent_idx)
            for parent_idx, _, _ in self._instance_graph.in_edges(
                wrapped_instance.index
            )
        )

    def get_outgoing_neighbors_with_predicate_type(
        self, wrapped_instance: WrappedInstance, predicate_type: Type[Predicate]
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        for _, child_idx, edge in self._instance_graph.out_edges(
            wrapped_instance.index
        ):
            if isinstance(edge.predicate, predicate_type):
                yield self._instance_graph.get_node_data(child_idx)

    def get_outgoing_neighbors(
        self, wrapped_instance: WrappedInstance
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        yield from (
            self._instance_graph.get_node_data(child_idx)
            for _, child_idx, _ in self._instance_graph.out_edges(
                wrapped_instance.index
            )
        )

    def get_neighbors(
        self, wrapped_instance: WrappedInstance
    ) -> Iterable[WrappedInstance]:
        wrapped_instance = self.get_wrapped_instance(wrapped_instance)
        yield from (
            self._instance_graph.get_node_data(idx)
            for idx in self._instance_graph.neighbors(wrapped_instance.index)
        )

    @classmethod
    def build(cls, classes: List[Type] = None) -> SymbolGraph:
        if not classes:
            for cls_ in copy(symbols_registry):
                symbols_registry.update(recursive_subclasses(cls_))
            classes = symbols_registry
        return SymbolGraph(ClassDiagram(list(classes), DescriptorAwareIntrospector()))

    def to_dot(
        self,
        filepath: str,
        format="svg",
        graph_type="instance",
        without_inherited_associations: bool = True,
    ) -> None:
        import pydot

        if graph_type == "type":
            if without_inherited_associations:
                graph = (
                    self._type_graph.to_subdiagram_without_inherited_associations()._dependency_graph
                )
            else:
                graph = self._type_graph._dependency_graph
        else:
            graph = self._instance_graph
        if not filepath.endswith(f".{format}"):
            filepath += f".{format}"
        dot_str = graph.to_dot(
            lambda node: dict(
                color="black",
                fillcolor="lightblue",
                style="filled",
                label=node.name,
            ),
            lambda edge: dict(color=edge.color, style="solid", label=str(edge)),
            dict(rankdir="LR"),
        )
        dot = pydot.graph_from_dot_data(dot_str)[0]
        try:
            dot.write(filepath, format=format)
        except FileNotFoundError:
            tmp_filepath = filepath.replace(f".{format}", ".dot")
            dot.write(tmp_filepath, format="raw")
            try:
                os.system(f"/usr/bin/dot -T{format} {tmp_filepath} -o {filepath}")
                os.remove(tmp_filepath)
            except Exception as e:
                logger.error(e)


symbols_registry: Set[Type] = set()
