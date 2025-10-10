from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Set, Optional
from typing import TextIO

import rustworkx as rx
from sqlalchemy import TypeDecorator
from typing_extensions import List, Type, Dict

from .dao import AlternativeMapping
from .field_info import FieldInfo
from .sqlalchemy_generator import SQLAlchemyGenerator
from .wrapped_table import WrappedTable
from ..class_diagrams.class_diagram import (
    ClassDiagram,
    Relation,
    WrappedClass,
)

logger = logging.getLogger(__name__)


class InheritanceStrategy(Enum):
    JOINED = "joined"
    SINGLE = "single"


class AlternativelyMaps(Relation):
    """
    Edge type that says that the source alternativly maps the target, e. g.
    `AlternativeMaps(source=PointMapping, target=Point)` means that PointMapping is the mapping for Point.
    """


@dataclass
class ORMatic:
    """
    ORMatic is a tool for generating SQLAlchemy ORM models from a set of dataclasses.
    """

    class_dependency_graph: ClassDiagram
    """
    The class diagram to add the orm for.
    """

    alternative_mappings: List[Type[AlternativeMapping]] = field(default_factory=list)
    """
    List of alternative mappings that should be used to map classes.
    """

    type_mappings: Dict[Type, TypeDecorator] = field(default_factory=dict)
    """
    A dict that maps classes to custom types that should be used to save the classes.
    They keys of the type mappings must be disjoint with the classes given..
    """

    inheritance_strategy: InheritanceStrategy = InheritanceStrategy.JOINED
    """
    The inheritance strategy to use.
    """

    foreign_key_postfix = "_id"
    """
    The postfix that will be added to foreign key columns (not the relationships).
    """

    imports: Set[str] = field(default_factory=set, init=False)
    """
    A set of modules that need to be imported.
    """

    extra_imports: Dict[str, Set[str]] = field(default_factory=dict, init=False)
    """
    A dict that maps modules to classes that should be imported via from module import class.
    The key is the module, the value is the set of classes that are needed
    """

    type_annotation_map: Dict[str, str] = field(default_factory=dict, init=False)
    """
    The string version of type mappings that is used in jinja.
    """

    inheritance_graph: rx.PyDiGraph[int] = field(default=None, init=False)
    """
    A graph that represents the inheritance structure of the classes. Extracted from the class dependency graph.
    """

    wrapped_tables: Dict[WrappedClass, WrappedTable] = field(
        default_factory=dict, init=False
    )
    """
    The wrapped tables instances for the SQLAlchemy conversion.
    """

    def __post_init__(self):
        self._create_inheritance_graph()
        self._add_alternative_mappings_to_class_diagram()
        self._create_wrapped_tables()

    def _create_wrapped_tables(self):
        self.class_dict = {}
        for wrapped_clazz in self.wrapped_classes_in_topological_order:

            # check if the class has an alternative mapping
            if alternative_mapping := self.get_alternative_mapping(wrapped_clazz):
                # add the alternative mapping
                self.wrapped_tables[wrapped_clazz] = WrappedTable(
                    wrapped_clazz=alternative_mapping, ormatic=self
                )
            else:
                # add the class normally
                self.wrapped_tables[wrapped_clazz] = WrappedTable(
                    wrapped_clazz=wrapped_clazz, ormatic=self
                )

    def _create_inheritance_graph(self):
        self.inheritance_graph = rx.PyDiGraph()
        self.inheritance_graph.add_nodes_from(
            [w.index for w in self.class_dependency_graph.wrapped_classes]
        )
        for edge in self.class_dependency_graph.inheritance_relations:
            self.inheritance_graph.add_edge(edge.source.index, edge.target.index, None)

    def _add_alternative_mappings_to_class_diagram(self):
        """
        Add alternative mappings to the class diagram.
        """
        for alternative_mapping in self.alternative_mappings:
            wrapped_alternative_mapping = WrappedClass(clazz=alternative_mapping)
            self.class_dependency_graph.add_node(wrapped_alternative_mapping)
            self.class_dependency_graph.add_relation(
                AlternativelyMaps(
                    source=wrapped_alternative_mapping,
                    target=self.class_dependency_graph.get_wrapped_class(
                        alternative_mapping.original_class()
                    ),
                )
            )

    @property
    def alternatively_maps_relations(self) -> List[AlternativelyMaps]:
        return [
            edge
            for edge in self.class_dependency_graph._dependency_graph.edges()
            if isinstance(edge, AlternativelyMaps)
        ]

    def get_alternative_mapping(
        self, wrapped_class: WrappedClass
    ) -> Optional[WrappedClass]:
        """
        Finds and returns an alternative mapping for the given wrapped class,
        if one exists, based on the relations specified in
        `alternatively_maps_relations`.

        :param wrapped_class: The wrapped class for which an alternative
            mapping is to be searched.
        :return: An alternate mapping of the type WrappedClass if found,
            otherwise None.
        """
        for rel in self.alternatively_maps_relations:
            if rel.target == wrapped_class:
                return rel.source
        return None

    def create_type_annotations_map(self):
        self.type_annotation_map = {"Type": "TypeType"}
        for clazz, custom_type in self.type_mappings.items():
            self.type_annotation_map[f"{clazz.__module__}.{clazz.__name__}"] = (
                f"{custom_type.__module__}.{custom_type.__name__}"
            )

    @property
    def wrapped_classes_in_topological_order(self) -> List[WrappedClass]:
        """
        :return: List of all tables in topological order.
        """
        result = []
        sorter = rx.TopologicalSorter(self.inheritance_graph)
        while sorter.is_active():
            nodes = sorter.get_ready()
            result.extend(
                [self.class_dependency_graph._dependency_graph[n] for n in nodes]
            )
            sorter.done(nodes)
        return result

    def make_all_tables(self):
        for table in self.wrapped_tables.values():
            table.parse_fields()

    def foreign_key_name(self, field_info: FieldInfo):
        """
        :return: A foreign key name for the given field.
        """
        return f"{field_info.clazz.__name__.lower()}_{field_info.name}{self.foreign_key_postfix}"

    def to_sqlalchemy_file(self, file: TextIO):
        """
        Generate a Python file with SQLAlchemy declarative mappings from the ORMatic models.

        :param file: The file to write to
        """
        sqlalchemy_generator = SQLAlchemyGenerator(self)
        sqlalchemy_generator.to_sqlalchemy_file(file)
