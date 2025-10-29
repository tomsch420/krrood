from __future__ import annotations

import itertools
import os
import weakref
from collections import defaultdict
from dataclasses import dataclass, field, InitVar

from rustworkx import PyDiGraph
from typing_extensions import (
    TYPE_CHECKING,
    Any,
    Iterable,
    Optional,
    List,
    Type,
    Dict,
    DefaultDict,
)

from .. import logger
from ..class_diagrams import ClassDiagram
from ..singleton import SingletonMeta
from ..utils import recursive_subclasses

if TYPE_CHECKING:
    from .predicate import BinaryPredicate, Symbol


@dataclass
class PredicateClassRelation:
    """
    Edge data representing a predicate-based relation between two wrapped instances.

    The relation carries the predicate instance that asserted the edge and a flag indicating
    whether it was inferred transitively or added directly.
    """

    source: WrappedInstance
    """
    The source of the predicate
    """

    target: WrappedInstance
    """
    The target of the predicate
    """

    predicate: BinaryPredicate
    """
    The asserted Predicate"""

    inferred: bool = False
    """
    Rather it was inferred or not.
    """

    def __str__(self):
        """Return the predicate type name for labeling the edge."""
        return self.predicate.__class__.__name__

    @property
    def color(self) -> str:
        return "red" if self.inferred else "black"


@dataclass
class WrappedInstance:
    """
    A node wrapper around a concrete Symbol instance used in the instance graph.
    """

    instance: InitVar[Symbol]
    """
    The instance to wrap. Only passed as initialization variable.
    """

    instance_reference: weakref.ReferenceType[Symbol] = field(init=False, default=None)
    """
    A weak reference to the symbol instance this wraps.
    """

    index: Optional[int] = field(init=False, default=None)
    """
    Index in the instance graph of the symbol graph that manages this object.
    """

    _symbol_graph_: Optional[SymbolGraph] = field(
        init=False, hash=False, default=None, repr=False
    )
    """
    The symbol graph that manages this object.
    """

    inferred: bool = False
    """
    Rather is instance was inferred or constructed.
    """

    instance_type: Type[Symbol] = field(init=False, default=None)
    """
    The type of the instance.
    This is needed to clean it up from the cache after the instance reference died.
    """

    def __post_init__(self, instance: Symbol):
        self.instance_reference = weakref.ref(instance)
        self.instance_type = type(instance)

    @property
    def instance(self) -> Optional[Symbol]:
        """
        :return: The symbol that is referenced to. Can return None if this symbol is garbage collected already.
        """
        return self.instance_reference()

    @property
    def name(self):
        """Return a unique display name composed of class name and node index."""
        return self.instance.__class__.__name__ + str(self.index)

    @property
    def color(self) -> str:
        return "red" if self.inferred else "black"

    def __eq__(self, other):
        return self.instance == other.instance

    def __hash__(self):
        if self.instance:
            return hash(self.instance)
        else:
            return id(self.instance)


@dataclass
class SymbolGraph(metaclass=SingletonMeta):
    """
    A singleton combination of a class and instance diagram.
    This class tracks the life cycles `Symbol` instance created in the python process.
    Furthermore, relations between instances are also tracked.

    Relations are represented as edges where each edge has a relation object attached to it. The relation object
    contains also the Predicate object that represents the relation.

    The construction of this object will do nothing if a singleton instance of this already exists.
    Make sure to call `clear()` before constructing this object if you want a new one.
    """

    _class_diagram: ClassDiagram = field(default=None)
    """
    The class diagram of all registered classes.
    """

    _instance_graph: PyDiGraph[WrappedInstance, PredicateClassRelation] = field(
        default_factory=PyDiGraph, init=False
    )
    """
    A directed graph that stores all instances of `Symbol` and how they relate to each other.
    """

    _instance_index: Dict[int, WrappedInstance] = field(
        default_factory=dict, init=False, repr=False
    )
    """
    Dictionary that maps the ids of objects to wrapped instances.
    Used for faster access when only the WrappedInstance.instance is available.
    """

    _class_to_wrapped_instances: DefaultDict[Type, List[WrappedInstance]] = field(
        init=False, default_factory=lambda: defaultdict(lambda: [])
    )
    """
    A dictionary that sorts the wrapped instances by the type inside them.
    This enables quick behavior similar to selecting everything from an entire table in SQL.
    """

    _relation_index: Dict[type, set[tuple[int, int]]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self):
        if self._class_diagram is None:
            # fetch all symbols and construct the graph
            from .predicate import Symbol

            self._class_diagram = ClassDiagram(list(recursive_subclasses(Symbol)))

    def get_role_takers_of_instance(self, instance: Any) -> Optional[Symbol]:
        """
        :param instance: The instance to get the role takers for.
        :return: Role takers of the given instance. A role taker is a field that represents
         a one-to-one relationship and is not optional.
        """
        wrapped_instance = self.get_wrapped_instance(instance)
        if not wrapped_instance:
            raise ValueError(f"Instance {instance} not found in graph.")
        role_taker_assoc = self.class_diagram.get_role_taker_associations_of_cls(
            type(wrapped_instance.instance)
        )
        if not role_taker_assoc:
            return None
        return getattr(wrapped_instance.instance, role_taker_assoc.field.public_name)

    @property
    def class_diagram(self) -> ClassDiagram:
        return self._class_diagram

    def add_node(self, wrapped_instance: WrappedInstance):
        """
        Add a wrapped instance to the cache.

        :param wrapped_instance: The instance to add.
        """
        wrapped_instance.index = self._instance_graph.add_node(wrapped_instance)
        wrapped_instance._symbol_graph_ = self
        self._instance_index[id(wrapped_instance.instance)] = wrapped_instance
        self._class_to_wrapped_instances[type(wrapped_instance.instance)].append(
            wrapped_instance
        )

    def remove_node(self, wrapped_instance: WrappedInstance):
        """
        Remove a wrapped instance from the cache.

        :param wrapped_instance: The instance to remove.
        """
        self._instance_index.pop(id(wrapped_instance.instance), None)
        self._class_to_wrapped_instances[wrapped_instance.instance_type].remove(
            wrapped_instance,
        )
        self._instance_graph.remove_node(wrapped_instance.index)

    def remove_dead_instances(self):
        for node in self._instance_graph.nodes():
            if node.instance is None:
                self.remove_node(node)

    def get_instances_of_type(self, type_: Type[Symbol]) -> Iterable[WrappedInstance]:
        """
        Get all wrapped instances of the given type and all its subclasses.
        :param type_: The symbol type to look for
        :return: All wrapped instances that refer to an instance of the given type.
        """
        yield from (
            instance.instance
            for cls in [type_] + recursive_subclasses(type_)
            for instance in self._class_to_wrapped_instances[cls]
        )

    def get_wrapped_instance(self, instance: Any) -> Optional[WrappedInstance]:
        if isinstance(instance, WrappedInstance):
            return instance
        return self._instance_index.get(id(instance), None)

    def clear(self) -> None:
        SingletonMeta.clear_instance(type(self))

    # Adapters to align with ORM alternative mapping expectations
    def add_instance(self, wrapped_instance: WrappedInstance) -> None:
        """Add a wrapped instance to the graph.

        This is an adapter that delegates to add_node to keep API compatibility with
        SymbolGraphMapping.create_from_dao.
        """
        self.add_node(wrapped_instance)

    def add_relation(self, relation: PredicateClassRelation) -> None:
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

    def add_edge(self, relation: PredicateClassRelation) -> None:
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

    def relations(self) -> Iterable[PredicateClassRelation]:
        yield from self._instance_graph.edges()

    @property
    def wrapped_instances(self) -> List[WrappedInstance]:
        return self._instance_graph.nodes()

    def get_outgoing_neighbors_with_predicate_subclass(
        self,
        wrapped_instance: WrappedInstance,
        predicate_subclass: Type[BinaryPredicate],
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
        self, wrapped_instance: WrappedInstance, predicate_type: Type[BinaryPredicate]
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
        self, wrapped_instance: WrappedInstance, predicate_type: Type[BinaryPredicate]
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
                    self._class_diagram.to_subdiagram_without_inherited_associations(
                        True
                    )._dependency_graph
                )
            else:
                graph = self._class_diagram._dependency_graph
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
