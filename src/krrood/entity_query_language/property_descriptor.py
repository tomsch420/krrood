from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, MISSING, fields
from functools import cached_property
from typing import (
    Generic,
    TypeVar,
    ClassVar,
    Set,
    Optional,
    Callable,
    Type,
    Iterable,
    Any,
    Dict,
)

from . import Predicate, symbol
from .typing_utils import get_range_types
from .utils import make_set

T = TypeVar("T")


@dataclass(frozen=True)
class PropertyDescriptor(Generic[T], Predicate):
    """Descriptor storing values on instances while keeping type metadata on the descriptor.

    When used on dataclass fields and combined with Thing, the descriptor
    injects a hidden dataclass-managed attribute (backing storage) into the owner class
    and collects domain and range types for introspection.
    """

    domain_types: ClassVar[Set[Type]] = set()
    range_types: ClassVar[Set[Type]] = set()
    domain_value: Optional[Any] = None
    range_value: Optional[Any] = None

    @cached_property
    def attr_name(self) -> str:
        return f"_{self.name}_{id(self)}"

    @cached_property
    def name(self) -> str:
        name = self.__class__.__name__
        return name[0].lower() + name[1:]

    @cached_property
    def nullable(self) -> bool:
        return type(None) in self.range_types

    def create_managed_attribute_for_class(self, cls: Type, attr_name: str) -> None:
        """Create hidden dataclass field to store instance values and update type sets."""
        setattr(
            cls,
            self.attr_name,
            field(
                default_factory=list,
                init=False,
                repr=False,
                hash=False,
            ),
        )
        # Preserve the declared annotation for the hidden field
        cls.__annotations__[self.attr_name] = cls.__annotations__[attr_name]

        self.update_domain_types(cls)
        self.update_range_types(cls, attr_name)

    def update_domain_types(self, cls: Type) -> None:
        """
        Add a class to the domain types if it is not already a subclass of any existing domain type.

        This method is used to keep track of the classes that are valid as values for the property descriptor.
        It does not add a class if it is already a subclass of any existing domain type to avoid infinite recursion.
        :param cls: The class to add to the domain types.
        :return: None
        """
        if any(issubclass(cls, domain_type) for domain_type in self.domain_types):
            return
        self.domain_types.add(cls)

    def update_range_types(self, cls: Type, attr_name: str) -> None:
        type_hint = cls.__annotations__[attr_name]
        if isinstance(type_hint, str):
            try:
                type_hint = eval(
                    type_hint, vars(__import__(cls.__module__, fromlist=["*"]))
                )
            except NameError:
                # Try again with the class under construction injected; if still failing, skip for now.
                try:
                    module_globals = vars(
                        __import__(cls.__module__, fromlist=["*"])
                    ).copy()
                    module_globals[cls.__name__] = cls
                    type_hint = eval(type_hint, module_globals)
                except NameError:
                    return
        for new_type in get_range_types(type_hint):
            try:
                is_sub = any(
                    issubclass(new_type, range_cls) for range_cls in self.range_types
                )
            except TypeError:
                # new_type is not a class (e.g., typing constructs); skip subclass check
                is_sub = False
            if is_sub:
                continue
            try:
                self.range_types.add(new_type)
            except TypeError:
                # Unhashable or invalid type; ignore
                continue

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.attr_name)

    def __set__(self, obj, value):
        if isinstance(value, PropertyDescriptor):
            return
        setattr(obj, self.attr_name, value)

    def __call__(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        if hasattr(domain_value, self.attr_name):
            return self.check_relation_value(domain_value, range_value)
        else:
            return self.check_relation_holds_for_subclasses_of_property(
                domain_value=domain_value, range_value=range_value
            )

    def check_relation_holds_for_subclasses_of_property(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        for prop_data in self.get_sub_properties(domain_value):
            if self.check_relation_value(
                prop_data.attr_name, domain_value=domain_value, range_value=range_value
            ):
                return True
        return False

    def get_sub_properties(
        self, domain_value: Optional[Any] = None
    ) -> Iterable[PropertyDescriptor]:
        domain_value = domain_value or self.domain_value
        for f in fields(domain_value):
            if issubclass(type(f.default), self.__class__):
                yield f.default

    def check_relation_value(
        self,
        attr_name: str,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
    ):
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        attr_value = getattr(domain_value, attr_name)
        if make_set(range_value).issubset(make_set(attr_value)):
            return True
        elif self.transitive:
            for v in attr_value:
                if self.__call__(domain_value=v, range_value=range_value):
                    return True
        return False


class DescriptionMeta(type):
    """Metaclass that recognizes PropertyDescriptor class attributes and wires backing storage."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        for attr_name, attr_value in attrs.items():
            if not isinstance(attr_value, PropertyDescriptor):
                continue
            attr_value.create_managed_attribute_for_class(new_class, attr_name)
        return new_class


@symbol
class Thing(metaclass=DescriptionMeta):
    """Base class for things that can be described by property descriptors."""

    ...
