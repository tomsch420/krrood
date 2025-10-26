from __future__ import annotations

import enum
import importlib
import inspect
import logging
import sys
from dataclasses import dataclass, Field
from datetime import datetime
from functools import cached_property, lru_cache
from types import NoneType
from collections.abc import Sequence

from typing_extensions import (
    get_type_hints,
    get_origin,
    get_args,
    ClassVar,
    List,
    Type,
    TYPE_CHECKING,
    Optional,
    Union,
)

from .utils import is_builtin_class
from ..ormatic.utils import module_and_class_name

if TYPE_CHECKING:
    from .class_diagram import WrappedClass


@dataclass
class TypeResolutionError(TypeError):
    """
    Error raised when a type cannot be resolved, even if searched for manually.
    """

    name: str

    def __post_init__(self):
        super().__init__(f"Could not resolve type for {self.name}")


@dataclass
class WrappedField:
    """
    A class that wraps a field of dataclass and provides some utility functions.
    """

    clazz: WrappedClass
    """
    The wrapped class that the field was created from.
    """

    field: Field
    """
    The dataclass field object that is wrapped.
    """

    container_types: ClassVar[List[Type]] = [list, set, tuple, type, Sequence]
    """
    A list of container types that are supported by the parser.
    """

    def __hash__(self):
        return hash((self.clazz.clazz, self.field))

    def __eq__(self, other):
        return (self.clazz.clazz, self.field) == (
            other.clazz.clazz,
            other.field,
        )

    def __repr__(self):
        return f"{module_and_class_name(self.clazz.clazz)}.{self.field.name}"

    @cached_property
    def resolved_type(self):
        try:
            result = get_type_hints(self.clazz.clazz)[self.field.name]
            return result
        except NameError as e:
            # First try to find the class in the class diagram
            potential_matching_classes = [
                cls.clazz
                for cls in self.clazz._class_diagram.wrapped_classes
                if cls.clazz.__name__ == e.name
            ]
            if len(potential_matching_classes) > 0:
                locals()[e.name] = potential_matching_classes[0]
            else:
                raise e
            result = get_type_hints(self.clazz.clazz, localns=locals())[self.field.name]
            return result

    @cached_property
    def is_builtin_type(self) -> bool:

        return self.type_endpoint in [int, float, str, bool, datetime, NoneType]

    @cached_property
    def is_container(self) -> bool:
        return get_origin(self.resolved_type) in self.container_types

    @cached_property
    def container_type(self) -> Optional[Type]:
        if not self.is_container:
            return None
        return get_origin(self.resolved_type)

    @cached_property
    def is_collection_of_builtins(self):
        return self.is_container and all(
            is_builtin_class(field_type) for field_type in get_args(self.resolved_type)
        )

    @cached_property
    def is_optional(self):
        origin = get_origin(self.resolved_type)
        if origin not in [Union, Optional]:
            return False
        if origin == Union:
            args = get_args(self.resolved_type)
            return len(args) == 2 and NoneType in args
        return True

    @cached_property
    def contained_type(self):
        if not self.is_container and not self.is_optional:
            raise ValueError("Field is not a container")
        if self.is_optional:
            return get_args(self.resolved_type)[0]
        else:
            try:
                return get_args(self.resolved_type)[0]
            except IndexError:
                if self.resolved_type is Type:
                    return self.resolved_type
                else:
                    raise

    @cached_property
    def is_type_type(self) -> bool:
        return get_origin(self.resolved_type) is type

    @cached_property
    def is_enum(self) -> bool:
        if self.is_container:
            return False
        if self.is_optional:
            return issubclass(self.contained_type, enum.Enum)

        return issubclass(self.resolved_type, enum.Enum)

    @cached_property
    def is_one_to_one_relationship(self) -> bool:
        return not self.is_container and not self.is_builtin_type

    @cached_property
    def is_one_to_many_relationship(self) -> bool:
        return self.is_container and not self.is_builtin_type and not self.is_optional

    @cached_property
    def type_endpoint(self) -> Type:
        if self.is_container or self.is_optional:
            return self.contained_type
        else:
            return self.resolved_type
