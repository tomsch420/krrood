from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from functools import cached_property, lru_cache

from typing_extensions import List, Dict, TYPE_CHECKING, Optional, Tuple

from .dao import AlternativeMapping
from .field_info import FieldInfo
from ..class_diagrams.class_diagram import (
    WrappedClass,
)
from ..class_diagrams.wrapped_field import WrappedField

if TYPE_CHECKING:
    from .ormatic import ORMatic, InheritanceStrategy

logger = logging.getLogger(__name__)


@dataclass
class WrappedTable:
    """
    A class that wraps a dataclass and contains all the information needed to create a SQLAlchemy table from it.
    """

    wrapped_clazz: WrappedClass
    """
    The dataclass that this WrappedTable wraps.
    """

    ormatic: ORMatic
    """
    Reference to the ORMatic instance that created this WrappedTable.
    """

    builtin_columns: List[Tuple[str, str]] = field(default_factory=list, init=False)
    """
    List of columns that can be directly mapped using builtin types
    """

    custom_columns: List[Tuple[str, str, str]] = field(default_factory=list, init=False)
    """
    List for custom columns that need to by fully qualified
    """

    foreign_keys: List[Tuple[str, str, str]] = field(default_factory=list, init=False)
    """
    List of columns that represent foreign keys
    """

    relationships: List[Tuple[str, str, str]] = field(default_factory=list, init=False)
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
                    self.polymorphic_on_name,
                    "Mapped[str]",
                    "mapped_column(String(255), nullable=False)",
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

    def parse_field(self, field_info: WrappedField):
        if field_info.is_type_type:
            logger.info(f"Parsing as type.")
            self.create_type_type_column(field_info)

        elif (
            field_info.is_builtin_class or field_info.is_enum or field_info.is_datetime
        ):
            logger.info(f"Parsing as builtin type.")
            self.create_builtin_column(field_info)

        # handle on to one relationships
        elif not field_info.container and field_info.type in self.ormatic.class_dict:
            logger.info(f"Parsing as one to one relationship.")
            self.create_one_to_one_relationship(field_info)

        elif not field_info.container and field_info.type in self.ormatic.type_mappings:
            logger.info(
                f"Parsing as custom type {self.ormatic.type_mappings[field_info.type]}."
            )
            self.create_custom_type(field_info)

        elif field_info.container:
            if field_info.is_container_of_builtin:
                logger.info(f"Parsing as JSON.")
                self.create_container_of_builtins(field_info)
            elif field_info.type in self.ormatic.class_dict:
                logger.info(f"Parsing as one to many relationship.")
                self.create_one_to_many_relationship(field_info)
        else:
            logger.info("Skipping due to not handled type.")

    def create_builtin_column(self, field_info: FieldInfo):
        if field_info.is_enum:
            self.ormatic.extra_imports[field_info.type.__module__] |= {
                field_info.type.__name__
            }

        if not field_info.is_builtin_class:
            self.ormatic.imports |= {field_info.type.__module__}
            inner_type = f"{field_info.type.__module__}.{field_info.type.__name__}"
        else:
            inner_type = f"{field_info.type.__name__}"
        if field_info.optional:
            inner_type = f"Optional[{inner_type}]"

        if issubclass(field_info.type, str):
            self.custom_columns.append(
                (
                    field_info.name,
                    f"Mapped[{inner_type}]",
                    f"mapped_column(String(255), nullable={field_info.optional})",
                )
            )
        else:
            self.builtin_columns.append((field_info.name, f"Mapped[{inner_type}]"))

    def create_type_type_column(self, field_info: FieldInfo):
        column_name = field_info.name
        column_type = (
            f"Mapped[TypeType]"
            if not field_info.optional
            else f"Mapped[Optional[TypeType]]"
        )
        column_constructor = f"mapped_column(TypeType, nullable={field_info.optional})"
        self.custom_columns.append((column_name, column_type, column_constructor))

    def create_one_to_one_relationship(self, field_info: FieldInfo):
        # create foreign key
        fk_name = f"{field_info.name}{self.ormatic.foreign_key_postfix}"
        fk_type = f"Mapped[Optional[int]]" if field_info.optional else "Mapped[int]"

        # columns have to be nullable and use_alter=True since the insertion order might be incorrect otherwise
        fk_column_constructor = f"mapped_column(ForeignKey('{self.ormatic.class_dict[field_info.type].full_primary_key_name}', use_alter=True), nullable=True)"

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
