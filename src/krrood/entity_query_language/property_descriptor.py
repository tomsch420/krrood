from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, MISSING
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
)

from . import Predicate, symbol
from .typing_utils import get_range_types
from .utils import make_set

T = TypeVar("T")
NOTSET = object()


@dataclass(frozen=True)
class PropertyDescriptor(Generic[T], Predicate):
    """Descriptor storing values on instances while keeping type metadata on the descriptor.

    When used on dataclass fields and combined with Thing, the descriptor
    injects a hidden dataclass-managed attribute (backing storage) into the owner class
    and collects domain and range types for introspection.
    """

    domain_types: ClassVar[Set[Type]] = set()
    range_types: ClassVar[Set[Type]] = set()
    _registry: ClassVar[dict] = {}

    domain_value: Optional[object] = None
    range_value: Optional[T] = None
    default: Optional[T] = NOTSET
    default_factory: Optional[Callable[[], T]] = NOTSET

    def __post_init__(self):
        self._registry[self.name] = self

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
        default = self.default
        if default is NOTSET:
            default = MISSING
        default_factory = self.default_factory
        if default_factory is NOTSET:
            default_factory = MISSING
        setattr(
            cls,
            self.attr_name,
            field(
                default_factory=default_factory,
                default=default,
                init=False,
                repr=False,
                hash=False,
            ),
        )
        # Preserve the declared annotation for the hidden field
        cls.__annotations__[self.attr_name] = cls.__annotations__[attr_name]

        self.update_domain_types(cls)
        self.update_range_types(cls, attr_name)
        if not hasattr(cls, "_properties_"):
            cls._properties_ = defaultdict(dict)
        cls._properties_[self.__class__][self.attr_name] = self

    def update_domain_types(self, cls: Type) -> None:
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
        if self.check_relation_exists(
            domain_value=domain_value, range_value=range_value
        ):
            return True
        else:
            return self.check_relation_exists_for_subclasses_of_property(
                domain_value=domain_value, range_value=range_value
            )

    def check_relation_exists_for_subclasses_of_property(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        sub_properties = [
            prop_data
            for prop_type, prop_data in domain_value._properties_.items()
            if issubclass(prop_type, self.__class__)
        ]
        for prop_data in sub_properties:
            for prop_name, prop_val in prop_data.items():
                if self.check_relation_exists(
                    prop_name, domain_value=domain_value, range_value=range_value
                ):
                    return True
        return False

    def check_relation_exists(
        self,
        attr_name: Optional[str] = None,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
    ) -> bool:
        attr_name = attr_name or self.attr_name
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        if not hasattr(domain_value, attr_name):
            return False
        return self.check_relation_value(attr_name, domain_value, range_value)

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
