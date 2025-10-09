from __future__ import annotations

import typing
from dataclasses import dataclass, Field
from datetime import datetime
from functools import cached_property
from types import NoneType
from typing import ClassVar, List, Type
from typing_extensions import get_type_hints, get_origin, get_args

from krrood.class_diagrams.class_diagram import WrappedClass, is_builtin_class


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

    container_types: ClassVar[List[Type]] = [
        list,
        set,
        tuple,
    ]
    """
    A list of container types that are supported by the parser.
    """

    @cached_property
    def resolved_type(self):
        return get_type_hints(self.clazz.clazz)[self.field.name]

    @cached_property
    def is_builtin_type(self) -> bool:
        return self.resolved_type in [int, float, str, bool, datetime, NoneType]

    @cached_property
    def is_container(self):
        return get_origin(self.resolved_type) in self.container_types

    @cached_property
    def is_collection_of_builtins(self):
        return self.is_container and all(
            is_builtin_class(field_type) for field_type in get_args(self.resolved_type)
        )

    @cached_property
    def is_optional(self):
        origin = get_origin(self.resolved_type)
        if origin not in [typing.Union, typing.Optional]:
            return False
        if origin == typing.Union:
            args = get_args(self.field.type)
            if len(args) != 2:
                return False
            if NoneType not in args:
                return False
            else:
                return True
        else:
            return True

    @cached_property
    def contained_type(self):
        if not self.is_container and not self.is_optional:
            raise ValueError("Field is not a container")
        if self.is_optional:
            return get_args(self.resolved_type)[1]
        else:
            return get_args(self.resolved_type)[0]
