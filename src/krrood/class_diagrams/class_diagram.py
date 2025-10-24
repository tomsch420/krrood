from __future__ import annotations

import dataclasses
import logging
from abc import ABC
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from dataclasses import field, InitVar, fields
from functools import cached_property, lru_cache
from types import NoneType
from typing import List, Optional, Dict, Iterable, Union, Any, Tuple, Set

import rustworkx as rx
from rustworkx_utils import RWXNode
from typing_extensions import Type, TYPE_CHECKING

from .attribute_introspector import (
    AttributeIntrospector,
    DataclassOnlyIntrospector,
)
from .utils import Role, get_generic_type_param
from .wrapped_field import WrappedField

if TYPE_CHECKING:
    from ..entity_query_language.predicate import PropertyDescriptor


@dataclass
class Relation(ABC):
    """
    Abstract base class representing a relationship between two classes in a UML class diagram.
    """

    source: WrappedClass
    """The source class in the relation."""

    target: WrappedClass
    """The target class in the relation."""

    def __str__(self):
        return f"{self.__class__.__name__}"

    @property
    def color(self) -> str:
        return "black"


@dataclass
class Inheritance(Relation):
    """
    Represents an inheritance (generalization) relationship in UML.

    This is an "is-a" relationship where the source class inherits from the target class.
    In UML notation, this is represented by a solid line with a hollow triangle pointing to the parent class.
    """

    def __str__(self):
        return f"isSuperClassOf"


@dataclass(unsafe_hash=True)
class Association(Relation):
    """
    Represents a general association relationship between two classes.

    This is the most general form of relationship, indicating that instances of one class
    are connected to instances of another class. In UML notation, this is shown as a solid line.
    """

    field: WrappedField
    """The field in the source class that creates this association with the target class."""

    one_to_many: bool = dataclasses.field(init=False)
    """Whether the association is one-to-many (True) or many-to-one (False)."""

    def __post_init__(self):
        self.one_to_many = (
            self.field.is_one_to_many_relationship and not self.field.is_type_type
        )

    def __str__(self):
        return f"has-{self.field.public_name}"


@dataclass(eq=False)
class HasRoleTaker(Association):
    """
    This is an association between a role and a role taker where the role class contains a role taker field.
    """

    def __str__(self):
        return f"role-taker({self.field.public_name})"


class ParseError(TypeError):
    """
    Error that will be raised when the parser encounters something that can/should not be parsed.

    For instance, Union types
    """

    pass


@dataclass
class WrappedClass:
    index: Optional[int] = field(init=False, default=None)
    clazz: Type
    _class_diagram: Optional[ClassDiagram] = field(
        init=False, hash=False, default=None, repr=False
    )
    _wrapped_field_name_map_: Dict[str, WrappedField] = field(
        init=False, hash=False, default_factory=dict, repr=False
    )

    @cached_property
    def fields(self) -> List[WrappedField]:
        """Return wrapped fields discovered by the diagram’s attribute introspector.

        Public names from the introspector are used to index `_wrapped_field_name_map_`.
        """
        try:
            wrapped_fields: list[WrappedField] = []
            introspector = self._class_diagram.introspector
            discovered = introspector.discover(self.clazz)
            for item in discovered:
                wf = WrappedField(
                    self,
                    item.field,
                    public_name=item.public_name,
                    property_descriptor=item.property_descriptor,
                )
                # Map under the public attribute name (e.g., "advisor")
                self._wrapped_field_name_map_[item.public_name] = wf
                wrapped_fields.append(wf)
            return wrapped_fields
        except TypeError as e:
            logging.error(f"Error parsing class {self.clazz}: {e}")
            raise ParseError(e) from e

    @property
    def name(self):
        return self.clazz.__name__ + str(self.index)

    def __hash__(self):
        return hash((self.index, self.clazz))


@dataclass
class RoleTakerPropertyFields:
    role_taker: WrappedField
    fields: Tuple[WrappedField, ...]


@dataclass
class ClassDiagram:

    classes: InitVar[List[Type]]

    introspector: AttributeIntrospector = field(
        default_factory=DataclassOnlyIntrospector, init=True, repr=False
    )

    _dependency_graph: rx.PyDiGraph[WrappedClass, Relation] = field(
        default_factory=rx.PyDiGraph, init=False
    )
    _cls_wrapped_cls_map: Dict[Type, WrappedClass] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self, classes: List[Type]):
        self._dependency_graph = rx.PyDiGraph()
        for clazz in classes:
            self.add_node(WrappedClass(clazz=clazz))
        self._create_all_relations()

    @lru_cache(maxsize=None)
    def get_role_taker_superclass_properties(
        self,
        wrapped_cls: Union[Type, WrappedClass],
        property_descriptor_cls: Type[PropertyDescriptor],
    ) -> Optional[RoleTakerPropertyFields]:
        wrapped_cls = self.get_wrapped_class(wrapped_cls)
        for assoc in self.get_out_edges(wrapped_cls):
            if not isinstance(assoc, HasRoleTaker):
                continue
            role_taker = assoc.target
            role_taker_fields = self.get_fields_of_superclass_property_descriptors(
                role_taker, property_descriptor_cls
            )
            return RoleTakerPropertyFields(assoc.field, role_taker_fields)
        return None

    @lru_cache(maxsize=None)
    def get_fields_of_superclass_property_descriptors(
        self,
        wrapped_cls: Union[Type, WrappedClass],
        property_descriptor_cls: Type[PropertyDescriptor],
    ) -> Tuple[WrappedField, ...]:
        wrapped_cls = self.get_wrapped_class(wrapped_cls)
        association_fields = []
        for assoc in self.get_out_edges(wrapped_cls):
            if not isinstance(assoc, Association):
                continue
            if not assoc.field.property_descriptor:
                continue
            other_prop_type = type(assoc.field.property_descriptor)
            if (
                issubclass(property_descriptor_cls, other_prop_type)
                and property_descriptor_cls is not other_prop_type
            ):
                association_fields.append(assoc.field)
        return tuple(association_fields)

    @lru_cache(maxsize=None)
    def get_the_field_of_property_descriptor_type(
        self,
        wrapped_cls: Union[Type, WrappedClass],
        property_descriptor_cls: Type[PropertyDescriptor],
    ) -> Optional[WrappedField]:
        wrapped_cls = self.get_wrapped_class(wrapped_cls)
        for assoc in self.get_out_edges(wrapped_cls):
            if not isinstance(assoc, Association):
                continue
            if not assoc.field.property_descriptor:
                continue
            other_prop_type = type(assoc.field.property_descriptor)
            if property_descriptor_cls is other_prop_type:
                return assoc.field

    @lru_cache(maxsize=None)
    def get_common_role_taker_associations(
        self, cls1: Union[Type, WrappedClass], cls2: Union[Type, WrappedClass]
    ) -> Tuple[Optional[HasRoleTaker], Optional[HasRoleTaker]]:
        cls1 = self.get_wrapped_class(cls1)
        cls2 = self.get_wrapped_class(cls2)
        assoc1 = self.get_role_taker_associations_of_cls(cls1)
        if not assoc1:
            return None, None
        target_1 = assoc1.target
        for _, _, assoc2 in self._dependency_graph.in_edges(target_1.index):
            if not isinstance(assoc2, HasRoleTaker):
                continue
            if assoc2.source.clazz != cls2.clazz:
                continue
            if assoc2.field.is_role_taker:
                return assoc1, assoc2
        return None, None

    @lru_cache(maxsize=None)
    def get_role_taker_associations_of_cls(
        self, cls: Union[Type, WrappedClass]
    ) -> Optional[HasRoleTaker]:
        """
        :return: Association objects representing the role takers of the given class, a role taker is
        a field that is a one-to-one relationship and is not optional.
        """
        for assoc in self.get_out_edges(cls):
            if isinstance(assoc, HasRoleTaker) and assoc.field.is_role_taker:
                return assoc
        return None

    @lru_cache(maxsize=None)
    def get_neighbors_with_relation_type(
        self,
        cls: Union[Type, WrappedClass],
        relation_type: Type[Relation],
    ) -> Tuple[WrappedClass, ...]:
        wrapped_cls = self.get_wrapped_class(cls)
        edge_filter_func = lambda edge: isinstance(edge, relation_type)
        filtered_neighbors = [
            self._dependency_graph.get_node_data(n)
            for n, e in self._dependency_graph.adj(wrapped_cls.index).items()
            if edge_filter_func(e)
        ]
        return tuple(filtered_neighbors)

    @lru_cache(maxsize=None)
    def get_outgoing_neighbors_with_relation_type(
        self,
        cls: Union[Type, WrappedClass],
        relation_type: Type[Relation],
    ) -> Tuple[WrappedClass, ...]:
        wrapped_cls = self.get_wrapped_class(cls)
        edge_filter_func = lambda edge: isinstance(edge, relation_type)
        find_successors_by_edge = self._dependency_graph.find_successors_by_edge
        return tuple(find_successors_by_edge(wrapped_cls.index, edge_filter_func))

    @lru_cache(maxsize=None)
    def get_incoming_neighbors_with_relation_type(
        self,
        cls: Union[Type, WrappedClass],
        relation_type: Type[Relation],
    ) -> Tuple[WrappedClass, ...]:
        wrapped_cls = self.get_wrapped_class(cls)
        edge_filter_func = lambda edge: isinstance(edge, relation_type)
        find_predecessors_by_edge = self._dependency_graph.find_predecessors_by_edge
        return tuple(find_predecessors_by_edge(wrapped_cls.index, edge_filter_func))

    @lru_cache(maxsize=None)
    def get_out_edges(self, cls: Union[Type, WrappedClass]) -> Tuple[Relation, ...]:
        wrapped_cls = self.get_wrapped_class(cls)
        out_edges = [
            edge for _, _, edge in self._dependency_graph.out_edges(wrapped_cls.index)
        ]
        return tuple(out_edges)

    def to_subdiagram_without_inherited_associations(
        self,
        include_field_name: bool = False,
    ) -> ClassDiagram:
        """
        Return a new class diagram where association edges that are present on any
        ancestor of the source class are removed from descendants.

        Inheritance edges are preserved.
        """
        # Rebuild a fresh diagram from the same classes to avoid mutating this instance
        result = copy(self)

        # Convenience locals
        g = result._dependency_graph

        # 1) Build parent map from inheritance edges: child_idx -> set(parent_idx)
        parent_map: dict[int, set[int]] = {}
        for u, v in g.edge_list():
            rel = g.get_edge_data(u, v)
            if isinstance(rel, Inheritance):
                parent_map.setdefault(v, set()).add(u)

        # 2) DFS to compute all ancestors for each node index
        def all_ancestors(node_idx: int) -> set[int]:
            parents = parent_map.get(node_idx, set())
            if not parents:
                return set()
            stack = list(parents)
            seen: set[int] = set(parents)
            while stack:
                cur = stack.pop()
                for p in parent_map.get(cur, set()):
                    if p not in seen:
                        seen.add(p)
                        stack.append(p)
            return seen

        # 3) Precompute association keys per source node
        #    Key = (relation class, target class[, field name])
        def assoc_key(rel: Association) -> tuple:
            if include_field_name:
                return (rel.__class__, rel.target.clazz, rel.field.field.name)
            return (rel.__class__, rel.target.clazz)

        assoc_keys_by_source: dict[int, set[tuple]] = {}
        for u, v in g.edge_list():
            rel = g.get_edge_data(u, v)
            if isinstance(rel, Association):
                assoc_keys_by_source.setdefault(u, set()).add(assoc_key(rel))

        # 4) Mark redundant descendant association edges for removal
        edges_to_remove: list[tuple[int, int]] = []
        for u, v in g.edge_list():
            rel = g.get_edge_data(u, v)
            if not isinstance(rel, Association):
                continue

            key = assoc_key(rel)
            # Collect all keys defined by any ancestor of u
            inherited_keys: set[tuple] = set()
            for anc in all_ancestors(u):
                inherited_keys |= assoc_keys_by_source.get(anc, set())

            if key in inherited_keys:
                edges_to_remove.append((u, v))

        # 5) Remove redundant edges
        for u, v in edges_to_remove:
            # Safe even if duplicates appear in list; graph ignores missing
            try:
                g.remove_edge(u, v)
            except Exception:
                # Be conservative: if already removed due to earlier operation, skip
                pass

        return result

    @property
    def wrapped_classes(self):
        return self._dependency_graph.nodes()

    @property
    def associations(self) -> List[Association]:
        return [
            edge
            for edge in self._dependency_graph.edges()
            if isinstance(edge, Association)
        ]

    @property
    def inheritance_relations(self) -> List[Inheritance]:
        return [
            edge
            for edge in self._dependency_graph.edges()
            if isinstance(edge, Inheritance)
        ]

    def get_wrapped_class(self, clazz: Type) -> Optional[WrappedClass]:
        if isinstance(clazz, WrappedClass):
            return clazz
        return self._cls_wrapped_cls_map.get(clazz, None)

    def add_node(self, clazz: WrappedClass):
        clazz.index = self._dependency_graph.add_node(clazz)
        clazz._class_diagram = self
        self._cls_wrapped_cls_map[clazz.clazz] = clazz

    def add_relation(self, relation: Relation):
        self._dependency_graph.add_edge(
            relation.source.index, relation.target.index, relation
        )

    def _create_inheritance_relations(self):
        for clazz in self.wrapped_classes:
            for superclass in clazz.clazz.__bases__:
                source = self.get_wrapped_class(superclass)
                if source:
                    relation = Inheritance(
                        source=source,
                        target=clazz,
                    )
                    self.add_relation(relation)

    def _create_all_relations(self):
        self._create_inheritance_relations()
        self._create_association_relations()

    def _create_association_relations(self):
        for clazz in self.wrapped_classes:
            for wrapped_field in clazz.fields:
                target_type = wrapped_field.type_endpoint

                wrapped_target_class = self.get_wrapped_class(target_type)

                if not wrapped_target_class:
                    continue

                association_type = Association
                if wrapped_field.is_role_taker and issubclass(clazz.clazz, Role):
                    role_taker_type = get_generic_type_param(clazz.clazz, Role)[0]
                    if role_taker_type is target_type:
                        association_type = HasRoleTaker

                relation = association_type(
                    field=wrapped_field,
                    source=clazz,
                    target=wrapped_target_class,
                )
                self.add_relation(relation)

    def _build_rxnode_tree(self) -> RWXNode:
        """
        Convert the class diagram graph to RWXNode tree structure for visualization.

        Creates a tree where inheritance relationships are represented as parent-child connections.
        If there are multiple root classes, they are grouped under a virtual root node.

        :return: Root RWXNode representing the class diagram
        """
        # Create RWXNode for each class
        node_map = {}
        for wrapped_class in self.wrapped_classes:
            class_name = wrapped_class.clazz.__name__
            node = RWXNode(name=class_name, data=wrapped_class)
            node_map[wrapped_class.index] = node

        # Build parent-child relationships from edges
        for edge in self._dependency_graph.edge_list():
            source_idx, target_idx = edge
            relation = self._dependency_graph.get_edge_data(source_idx, target_idx)

            # For inheritance: source is parent class, target is child class
            # In RWXNode: parent class should have child class as its child
            if isinstance(relation, Inheritance):
                parent_node = node_map[source_idx]
                child_node = node_map[target_idx]
                child_node.add_parent(parent_node)
            # elif isinstance(relation, Association):
            #     # For associations, add as parent relationship with label
            #     source_node = node_map[source_idx]
            #     target_node = node_map[target_idx]
            #     # Association goes from source to target
            #     target_node.add_parent(source_node)

        # Find root nodes (nodes without parents)
        root_nodes = [node for node in node_map.values() if not node.parents]

        # If there's only one root, return it
        if len(root_nodes) == 1:
            return root_nodes[0]

        # If there are multiple roots, create a virtual root
        virtual_root = RWXNode(name="Class Diagram")
        for root_node in root_nodes:
            root_node.add_parent(virtual_root)

        return virtual_root

    def visualize(
        self,
        filename: str = "class_diagram.pdf",
        title: str = "Class Diagram",
        figsize: tuple = (35, 30),
        node_size: int = 7000,
        font_size: int = 25,
        layout: str = "layered",
        edge_style: str = "straight",
        **kwargs,
    ):
        """
        Visualize the class diagram using rustworkx_utils.

        Creates a visual representation of the class diagram showing classes and their relationships.
        The diagram is saved as a PDF file.

        :param filename: Output filename for the visualization
        :param title: Title for the diagram
        :param figsize: Figure size as (width, height) tuple
        :param node_size: Size of the nodes in the visualization
        :param font_size: Font size for labels
        :param kwargs: Additional keyword arguments passed to RWXNode.visualize()
        """
        root_node = self._build_rxnode_tree()
        root_node.visualize(
            filename=filename,
            title=title,
            figsize=figsize,
            node_size=node_size,
            font_size=font_size,
            layout=layout,
            edge_style=edge_style,
            **kwargs,
        )

    def clear(self):
        self._dependency_graph.clear()

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        return self is other
