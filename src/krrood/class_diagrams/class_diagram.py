from __future__ import annotations

from .utils import is_builtin_class
from abc import ABC
from dataclasses import field, InitVar, fields
from enum import Enum
from typing import List, Optional

import rustworkx as rx
from rustworkx_utils import RWXNode

import inspect
import logging
import sys
from dataclasses import dataclass
from functools import lru_cache, cached_property

from typing_extensions import Type

from krrood.class_diagrams.wrapped_field import WrappedField


@dataclass
class Relation(ABC):
    """
    Abstract base class representing a relationship between two classes in a UML class diagram.
    """

    source: WrappedClass
    """The source class in the relation."""

    target: WrappedClass
    """The target class in the relation."""


@dataclass
class Inheritance(Relation):
    """
    Represents an inheritance (generalization) relationship in UML.

    This is an "is-a" relationship where the source class inherits from the target class.
    In UML notation, this is represented by a solid line with a hollow triangle pointing to the parent class.
    """


@dataclass
class Association(Relation):
    """
    Represents a general association relationship between two classes.

    This is the most general form of relationship, indicating that instances of one class
    are connected to instances of another class. In UML notation, this is shown as a solid line.
    """

    field: WrappedField
    """The field in the source class that creates this association with the target class."""


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

    @cached_property
    def fields(self) -> List[WrappedField]:
        try:
            return [WrappedField(self, f) for f in fields(self.clazz)]
        except TypeError as e:
            logging.error(f"Error parsing class {self.clazz}: {e}")
            raise ParseError(e) from e

    def __hash__(self):
        return hash((self.index, self.clazz))


@dataclass
class ClassDiagram:

    classes: InitVar[List[Type]]

    _dependency_graph: rx.PyDiGraph = field(default_factory=rx.PyDiGraph, init=False)

    def __post_init__(self, classes: List[Type]):
        self._dependency_graph = rx.PyDiGraph()
        for clazz in classes:
            self.add_node(WrappedClass(clazz=clazz))
        self._create_all_relations()

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
        base = [cls for cls in self.wrapped_classes if cls.clazz == clazz]
        return base[0] if base else None

    def add_node(self, clazz: WrappedClass):
        clazz.index = self._dependency_graph.add_node(clazz)
        clazz._class_diagram = self

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

                target_type = (
                    wrapped_field.contained_type
                    if wrapped_field.is_container or wrapped_field.is_optional
                    else wrapped_field.resolved_type
                )

                wrapped_target_class = self.get_wrapped_class(target_type)

                if not wrapped_target_class:
                    continue

                relation = Association(
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
