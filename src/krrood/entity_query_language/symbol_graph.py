from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from functools import cached_property
from typing_extensions import TYPE_CHECKING, Any, Iterable, Optional, List, Type


from rustworkx import PyDiGraph

from .. import logger
from ..class_diagrams import ClassDiagram, Relation
from ..class_diagrams.wrapped_field import WrappedField

if TYPE_CHECKING:
    from .predicate import Predicate


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
    instance: Any
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

    _type_graph: ClassDiagram
    _instance_graph: PyDiGraph[WrappedInstance, PredicateRelation] = field(
        default_factory=PyDiGraph
    )

    def add_node(self, wrapped_instance: WrappedInstance) -> None:
        if not isinstance(wrapped_instance, WrappedInstance):
            wrapped_instance = WrappedInstance(wrapped_instance)
        wrapped_instance.index = self._instance_graph.add_node(wrapped_instance)
        wrapped_instance._symbol_graph_ = self

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

    def relations(self) -> Iterable[PredicateRelation]:
        yield from self._instance_graph.edges()

    @property
    def wrapped_instances(self) -> List[WrappedInstance]:
        return self._instance_graph.nodes()

    def get_wrapped_instance(self, instance: Any) -> Optional[WrappedInstance]:
        for wrapped_instance in self.wrapped_instances:
            if wrapped_instance.instance is instance:
                return wrapped_instance
        return None

    def get_outgoing_neighbors_with_edge_type(
        self,
        wrapped_instance: WrappedInstance,
        predicate_type: Type[Predicate],
    ) -> Iterable[WrappedInstance]:
        for _, child_idx, edge in self._instance_graph.out_edges(
            wrapped_instance.index
        ):
            if isinstance(edge.predicate, predicate_type):
                yield self._instance_graph.get_node_data(child_idx)

    def get_outgoing_neighbors(
        self, wrapped_instance: WrappedInstance
    ) -> Iterable[WrappedInstance]:
        yield from (
            self._instance_graph.get_node_data(child_idx)
            for _, child_idx, _ in self._instance_graph.out_edges(
                wrapped_instance.index
            )
        )

    def get_neighbors(
        self, wrapped_instance: WrappedInstance
    ) -> Iterable[WrappedInstance]:
        yield from (
            self._instance_graph.get_node_data(idx)
            for idx in self._instance_graph.neighbors(wrapped_instance.index)
        )

    def clear(self):
        self._type_graph.clear()
        self._instance_graph.clear()

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
