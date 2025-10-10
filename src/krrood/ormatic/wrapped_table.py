from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from functools import cached_property, lru_cache

from typing_extensions import List, Dict, TYPE_CHECKING, Optional, Tuple

from .dao import AlternativeMapping
from ..class_diagrams.class_diagram import (
    WrappedClass,
)
from ..class_diagrams.wrapped_field import WrappedField

if TYPE_CHECKING:
    from .ormatic import ORMatic, InheritanceStrategy

logger = logging.getLogger(__name__)


@dataclass
class ColumnConstructor:
    """
    Represents a column constructor that can be used to create a column in SQLAlchemy.
    """

    name: str
    """
    The name of the column.
    """

    type: str
    """
    The type of the column.
    Needs to be like "Mapped[<type>]".
    """

    constructor: Optional[str] = None
    """
    The constructor call for sqlalchemy of the column.
    """

    def __str__(self) -> str:
        if self.constructor:
            return f"{self.name}: {self.type} = {self.constructor}"
        else:
            return f"{self.name}: {self.type}"


@dataclass
class WrappedTable:
    """
    A class that wraps a dataclass and contains all the information needed to create a SQLAlchemy table from it.
    """

    wrapped_clazz: WrappedClass
    """
    The wrapped class that this table wraps.
    """

    ormatic: ORMatic
    """
    Reference to the ORMatic instance that created this WrappedTable.
    """

    builtin_columns: List[ColumnConstructor] = field(default_factory=list, init=False)
    """
    List of columns that can be directly mapped using builtin types
    """

    custom_columns: List[ColumnConstructor] = field(default_factory=list, init=False)
    """
    List for custom columns that need to by fully qualified as triple of (name, type, constructor)
    """

    foreign_keys: List[ColumnConstructor] = field(default_factory=list, init=False)
    """
    List of columns that represent foreign keys as triple of (name, type, constructor)
    """

    relationships: List[ColumnConstructor] = field(default_factory=list, init=False)
    """
    List of relationships that should be added to the table.
    """

    mapper_args: Dict[str, str] = field(default_factory=dict, init=False)

    primary_key_name: str = "id"
    """
    The name of the primary key column.
    """

    polymorphic_on_name: str = "polymorphic_type"
    """
    The name of the column that will be used to identify polymorphic identities if any present.
    """

    skip_fields: List[WrappedField] = field(default_factory=list)
    """
    A list of fields that should be skipped when processing the dataclass.
    """

    @cached_property
    def primary_key(self):
        if self.parent_table is not None:
            column_type = f"ForeignKey({self.parent_table.full_primary_key_name})"
        else:
            column_type = "Integer"

        return f"mapped_column({column_type}, primary_key=True)"

    @property
    def child_tables(self) -> List[WrappedTable]:
        return [
            self.ormatic.class_dependency_graph._dependency_graph[index]
            for index in self.ormatic.inheritance_graph.successors(
                self.wrapped_clazz.index
            )
        ]

    def create_mapper_args(self):

        # this is the root of an inheritance structure
        if self.parent_table is None and len(self.child_tables) > 0:
            self.custom_columns.append(
                (
                    ColumnConstructor(
                        self.polymorphic_on_name,
                        "Mapped[str]",
                        "mapped_column(String(255), nullable=False)",
                    )
                )
            )
            self.mapper_args.update(
                {
                    "'polymorphic_on'": f"'{self.polymorphic_on_name}'",
                    "'polymorphic_identity'": f"'{self.tablename}'",
                }
            )

        # this inherits from something
        if self.parent_table is not None:
            self.mapper_args.update(
                {
                    "'polymorphic_identity'": f"'{self.tablename}'",
                }
            )
            # only needed for joined-table inheritance
            if self.ormatic.inheritance_strategy == InheritanceStrategy.JOINED:
                self.mapper_args.update(
                    {
                        "'inherit_condition'": f"{self.primary_key_name} == {self.parent_table.full_primary_key_name}"
                    }
                )

    @cached_property
    def full_primary_key_name(self):
        if self.ormatic.inheritance_strategy == InheritanceStrategy.SINGLE:
            root = self
            while root.parent_table is not None:
                root = root.parent_table
            return f"{root.tablename}.{root.primary_key_name}"
        return f"{self.tablename}.{self.primary_key_name}"

    @cached_property
    def tablename(self):
        result = self.clazz.__name__
        result += "DAO"
        return result

    @cached_property
    def parent_table(self) -> Optional[WrappedTable]:
        parents = self.ormatic.inheritance_graph.predecessors(self.wrapped_clazz.index)
        if len(parents) == 0:
            return None
        return self.ormatic.wrapped_tables[
            self.ormatic.class_dependency_graph._dependency_graph[parents[0]]
        ]

    @property
    def is_alternatively_mapped(self):
        return issubclass(self.wrapped_clazz.clazz, AlternativeMapping)

    @cached_property
    def fields(self) -> List[WrappedField]:
        """
        :return: The list of fields specified in this associated dataclass that should be mapped.
        """
        self.skip_fields = []

        if self.parent_table is not None:
            self.skip_fields += self.parent_table.skip_fields + self.parent_table.fields

        # get all new fields given by this class
        result = [
            field
            for field in self.wrapped_clazz.fields
            if field not in self.skip_fields
        ]

        # if the parent table is alternatively mapped, we need to remove the fields that are not present in the original class
        if self.parent_table is not None and self.parent_table.is_alternatively_mapped:
            # get the wrapped class of the original parent class
            og_parent_class = self.parent_table.wrapped_clazz.clazz.original_class()
            fields_in_og_class_but_not_in_dao = [
                f for f in fields(og_parent_class) if f not in self.parent_table.fields
            ]

            result = [r for r in result if r not in fields_in_og_class_but_not_in_dao]

        return result

    @lru_cache(maxsize=None)
    def parse_fields(self):

        for f in self.fields:

            logger.info("=" * 80)
            logger.info(
                f"Processing Field {self.wrapped_clazz.clazz.__name__}.{f.field.name}: {f.field.type}."
            )

            # skip private fields
            if f.field.name.startswith("_"):
                logger.info(f"Skipping since the field starts with _.")
                continue

            self.parse_field(f)

        self.create_mapper_args()

    def parse_field(self, wrapped_field: WrappedField):
        """
        Parses a given `WrappedField` and determines its type or relationship to create the
        appropriate column or define relationships in an ORM context.
        The method processes several
        types of fields, such as type types, built-in types, enumerations, one-to-one relationships,
        custom types, JSON containers, and one-to-many relationships.

        This creates the right information in the right place in the table definition to be read later by the jinja
        template.

        :param wrapped_field: An instance of `WrappedField` that contains metadata about the field
            such as its data type, whether it represents a built-in or user-defined type, or if it has
            specific ORM container properties.
        """
        if wrapped_field.is_type_type:
            logger.info(f"Parsing as type.")
            self.create_type_type_column(wrapped_field)

        elif wrapped_field.is_builtin_type or wrapped_field.is_enum:
            logger.info(f"Parsing as builtin type.")
            self.create_builtin_column(wrapped_field)

        # handle one to one relationships
        elif (
            wrapped_field.is_one_to_one_relationship
            and wrapped_field.contained_type in self.ormatic.mapped_classes
        ):
            logger.info(f"Parsing as one to one relationship.")
            self.create_one_to_one_relationship(wrapped_field)

        # handle custom types
        elif (
            wrapped_field.is_one_to_one_relationship
            and wrapped_field.contained_type in self.ormatic.type_mappings
        ):
            logger.info(
                f"Parsing as custom type {self.ormatic.type_mappings[wrapped_field.resolved_type]}."
            )
            self.create_custom_type(wrapped_field)

        # handle JSON containers
        elif wrapped_field.is_collection_of_builtins:
            logger.info(f"Parsing as JSON.")
            self.create_container_of_builtins(wrapped_field)

        # handle one to many relationships
        elif wrapped_field.is_one_to_many_relationship:
            logger.info(f"Parsing as one to many relationship.")
            self.create_one_to_many_relationship(wrapped_field)
        else:
            logger.info("Skipping due to not handled type.")

    def create_builtin_column(self, wrapped_field: WrappedField):
        """
        Creates a built-in column mapping for the given wrapped field. Depending on the
        properties of the `wrapped_field`, this function determines whether it's an enum,
        a built-in type, or requires additional imports. It then constructs appropriate
        column definitions and adds them to the respective list of database mappings.

        :param wrapped_field: The WrappedField instance representing the field
            to create a built-in column for.
        """

        self.ormatic.imported_modules.add(wrapped_field.type_endpoint.__module__)
        inner_type = (
            f"{wrapped_field.type_endpoint}.{wrapped_field.type_endpoint.__name__}"
        )
        type_annotation = (
            f"Optional[{inner_type}]" if wrapped_field.is_optional else inner_type
        )

        self.builtin_columns.append(
            ColumnConstructor(
                name=wrapped_field.field.name, type=f"Mapped[{type_annotation}]"
            )
        )

    def create_type_type_column(self, wrapped_field: WrappedField):
        column_name = wrapped_field.field.name
        column_type = (
            f"Mapped[TypeType]"
            if not wrapped_field.is_optional
            else f"Mapped[Optional[TypeType]]"
        )
        column_constructor = (
            f"mapped_column(TypeType, nullable={wrapped_field.is_optional})"
        )
        self.custom_columns.append((column_name, column_type, column_constructor))

    def create_one_to_one_relationship(self, wrapped_field: WrappedField):
        # create foreign key
        fk_name = f"{wrapped_field.field.name}{self.ormatic.foreign_key_postfix}"
        fk_type = (
            f"Mapped[Optional[int]]" if wrapped_field.is_optional else "Mapped[int]"
        )

        # columns have to be nullable and use_alter=True since the insertion order might be incorrect otherwise
        fk_column_constructor = f"mapped_column(ForeignKey('{self.ormatic.wrapped_tables[wrapped_field.field.type].full_primary_key_name}', use_alter=True), nullable=True)"

        self.foreign_keys.append((fk_name, fk_type, fk_column_constructor))

        # create relationship to remote side
        other_table = self.ormatic.class_dict[field_info.type]
        rel_name = f"{field_info.name}"
        rel_type = f"Mapped[{other_table.tablename}]"
        # relationships have to be post updated since since it won't work in the case of subclasses with another ref otherwise
        rel_constructor = f"relationship('{other_table.tablename}', uselist=False, foreign_keys=[{fk_name}], post_update=True)"
        self.relationships.append((rel_name, rel_type, rel_constructor))

    def create_one_to_many_relationship(self, field_info: FieldInfo):
        # create a foreign key to this on the remote side
        other_table = self.ormatic.class_dict[field_info.type]
        fk_name = f"{self.tablename.lower()}_{field_info.name}{self.ormatic.foreign_key_postfix}"
        fk_type = "Mapped[Optional[int]]"
        fk_column_constructor = f"mapped_column(ForeignKey('{self.full_primary_key_name}', use_alter=True), nullable=True)"
        other_table.foreign_keys.append((fk_name, fk_type, fk_column_constructor))

        # create a relationship with a list to collect the other side
        rel_name = f"{field_info.name}"
        rel_type = f"Mapped[List[{other_table.tablename}]]"
        rel_constructor = f"relationship('{other_table.tablename}', foreign_keys='[{other_table.tablename}.{fk_name}]', post_update=True)"
        self.relationships.append((rel_name, rel_type, rel_constructor))

    def create_container_of_builtins(self, field_info: FieldInfo):
        column_name = field_info.name
        container = "Set" if issubclass(field_info.container, set) else "List"
        column_type = f"Mapped[{container}[{field_info.type.__name__}]]"
        column_constructor = f"mapped_column(JSON, nullable={field_info.optional})"
        self.custom_columns.append((column_name, column_type, column_constructor))

    def create_custom_type(self, field_info: FieldInfo):
        custom_type = self.ormatic.type_mappings[field_info.type]
        column_name = field_info.name
        column_type = (
            f"Mapped[{custom_type.__module__}.{custom_type.__name__}]"
            if not field_info.optional
            else f"Mapped[Optional[{custom_type.__module__}.{custom_type.__name__}]]"
        )

        constructor = f"mapped_column({custom_type.__module__}.{custom_type.__name__}, nullable={field_info.optional})"

        self.custom_columns.append((column_name, column_type, constructor))

    @property
    def to_dao(self) -> Optional[str]:
        if issubclass(self.clazz, AlternativeMapping):
            return f"to_dao = {self.clazz.__module__}.{self.clazz.__name__}.to_dao"
        return None

    @property
    def base_class_name(self):
        if self.parent_table is not None:
            return self.parent_table.tablename
        else:
            return "Base"

    def __hash__(self):
        return hash(self.wrapped_clazz)
