from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, fields, InitVar
from functools import cached_property
from typing import (
    ClassVar,
    Set,
    Type,
    Optional,
    Any,
    Iterable,
    Tuple,
    Dict,
)
from weakref import WeakKeyDictionary, ref as weakref_ref

from line_profiler import profile
from typing_extensions import DefaultDict

from .predicate import Symbol
from .utils import make_set
from ..class_diagrams.class_diagram import WrappedClass
from ..class_diagrams.wrapped_field import WrappedField


class MonitoredSet(set):

    def __init__(self, *args, **kwargs):
        self.descriptor: PropertyDescriptor = kwargs.pop("descriptor")
        self._owner_ref = None  # weakref to owner instance
        super().__init__(*args, **kwargs)

    def bind_owner(self, owner) -> "MonitoredSet":
        """
        Bind the owning instance via a weak reference and return self.
        """
        self._owner_ref = weakref_ref(owner)
        return self

    @property
    def owner(self):
        return self._owner_ref() if self._owner_ref is not None else None

    def add(self, value, inferred: bool = False, call_on_add: bool = True):
        super().add(value)
        # route through descriptor with the concrete owner instance
        owner = self.owner
        if owner is not None and call_on_add:
            self.descriptor.on_add(owner, value, inferred=inferred)


SymbolType = Type[Symbol]
DomainRangeMap = Dict[SymbolType, SymbolType]


@dataclass
class PropertyDescriptor:
    """Descriptor managing a data class field while giving it metadata like superproperties,
    sub-properties, inverse, transitivity, ...etc.

    The descriptor injects a hidden dataclass-managed attribute (backing storage) into the owner class
    and collects domain and range types for introspection.

    The way this should be used is after defining your dataclasses you declare either in the same file or in a separate
    file the descriptors for each field that is considered a relation between two symbol types.

    Example:
        >>> from dataclasses import dataclass
        >>> from krrood.entity_query_language.property_descriptor import PropertyDescriptor
        >>> @dataclass
        ... class Company(Symbol):
        ...     name: str
        ...     members: Set[Person] = field(default_factory=set)
        ...
        >>> @dataclass
        ... class Person(Symbol):
        ...     name: str
        ...     works_for: Set[Company] = field(default_factory=set)
        ...
        >>> @dataclass
        >>> class Member(PropertyDescriptor):
        ...     pass
        ...
        >>> @dataclass
        ... class MemberOf(PropertyDescriptor):
        ...     inverse_of = Member
        ...
        >>> @dataclass
        >>> class WorksFor(MemberOf):
        ...     pass
        ...
        >>> Person.works_for = WorksFor(Person, "works_for")
        >>> Company.members = Member(Company, "members")
    """

    domain_type: InitVar[SymbolType]
    """
    The domain type for this descriptor instance.
    """
    field_name: InitVar[str]
    """
    The name of the field on the domain type that this descriptor instance manages.
    """
    wrapped_field: WrappedField = field(init=False)
    """
    The wrapped field instance that this descriptor instance manages.
    """
    _subprops_cache: ClassVar[WeakKeyDictionary] = WeakKeyDictionary()
    """
    Cache of discovered sub-properties per domain class and per descriptor subclass. Weak keys prevent memory leaks
     when domain classes are unloaded.
    """
    domain_range_map: ClassVar[
        DefaultDict[Type[PropertyDescriptor], DomainRangeMap]
    ] = defaultdict(dict)
    """
    A mapping from descriptor class to the mapping from domain types to range types for that descriptor class.
    """
    all_domains: ClassVar[Set[SymbolType]] = set()
    """
    A set of all domain types for this descriptor class.
    """
    all_ranges: ClassVar[Set[SymbolType]] = set()
    """
    A set of all range types for this descriptor class.
    """
    transitive: ClassVar[bool] = False
    """
    If the relation is transitive or not.
    """
    inverse_of: ClassVar[Optional[Type[PropertyDescriptor]]] = None
    """
    The inverse of the relation if it exists.
    """

    def __init_subclass__(cls, **kwargs):
        """
        Hook to set up inverse_of class variable automatically.
        """
        super().__init_subclass__(**kwargs)
        if cls.inverse_of is not None:
            cls.inverse_of.inverse_of = cls

    def __post_init__(
        self, domain_type: Optional[SymbolType] = None, field_name: Optional[str] = None
    ):
        self._validate_non_redundant_domain(domain_type)
        self._update_wrapped_field(domain_type, field_name)
        self._update_domain_and_range(domain_type)

    @cached_property
    def private_attr_name(self) -> str:
        """
        The name of the private attribute that stores the values on the owner instance.
        """
        return f"_{self.wrapped_field.name}"

    def _validate_non_redundant_domain(self, domain_type: SymbolType):
        """
        Validate that this exact descriptor type has not already been defined for this domain type.

        :param domain_type: The domain type to validate.
        """
        if domain_type in self.domain_range_map[self.__class__]:
            raise ValueError(
                f"Domain {domain_type} already exists, cannot define same descriptor more than once in "
                f"the same class"
            )

    def _update_wrapped_field(self, domain_type: SymbolType, field_name: str):
        """
        Set the wrapped field attribute using the domain type and field name.

        :param domain_type:  The domain type for this descriptor instance.
        :param field_name:  The field name that this descriptor instance manages.
        """
        field_ = [f for f in fields(domain_type) if f.name == field_name][0]
        self.wrapped_field = WrappedField(WrappedClass(domain_type), field_)

    def _update_domain_and_range(self, domain_type: SymbolType):
        """
        Update the domain and range sets and the domain-range map for this descriptor type.

        :param domain_type: The domain type for this descriptor instance.
        """
        range_type = self.wrapped_field.type_endpoint
        assert issubclass(range_type, Symbol)
        self.domain_range_map[self.__class__][domain_type] = range_type
        self.all_domains.add(domain_type)
        self.all_ranges.add(range_type)

    @cached_property
    def range(self):
        return self.domain_range_map[self.__class__][self.domain]

    @cached_property
    def domain(self):
        domain_type = self.wrapped_field.clazz.clazz
        assert issubclass(domain_type, Symbol)
        return domain_type

    def on_add(self, domain_value, val: Symbol, inferred: bool = False) -> None:
        """Add a value to the property descriptor."""
        self.add_relation(domain_value, val, inferred=inferred)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        container = getattr(obj, self.private_attr_name)
        # Bind the owner so subsequent `add` calls know the instance
        if getattr(container, "owner", None) is not obj:
            container.bind_owner(obj)
        return container

    def __set__(self, obj, value):
        if isinstance(value, PropertyDescriptor):
            return
        attr = getattr(obj, self.private_attr_name)
        attr.clear()
        for v in make_set(value):
            attr.add(v, call_on_add=False)
            self.add_relation(obj, v, set_attr=False)

    def add_relation(
        self,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
        inferred: bool = False,
        set_attr: bool = True,
    ) -> None:
        """Add a relation to the property descriptor."""
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        super().add_relation(domain_value, range_value, inferred=inferred)
        if set_attr:
            getattr(domain_value, self.attr_name).add(range_value, call_on_add=False)

    @profile
    def _holds_direct(
        self, domain_value: Optional[Any], range_value: Optional[Any]
    ) -> bool:
        """Return True if `range_value` is contained directly in the property of `domain_value`.
        Also consider sub-properties declared on the domain type.
        """
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value

        # If the concrete instance has our backing attribute, check it directly.
        if hasattr(domain_value, self.private_attr_name):
            if self._check_relation_value(
                attr_name=self.private_attr_name,
                domain_value=domain_value,
                range_value=range_value,
            ):
                return True
        # Fallback: check subclass properties declared on the domain type
        return self._check_relation_holds_for_subclasses_of_property(
            domain_value=domain_value, range_value=range_value
        )

    @profile
    def _check_relation_holds_for_subclasses_of_property(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        for prop_data in self.get_sub_properties(domain_value):
            if self._check_relation_value(
                prop_data.private_attr_name,
                domain_value=domain_value,
                range_value=range_value,
            ):
                return True
        return False

    def _check_relation_value(
        self,
        attr_name: str,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        attr_value = getattr(domain_value, attr_name)
        if make_set(range_value).issubset(make_set(attr_value)):
            return True
        # Do not handle transitivity here; it is now centralized in Predicate.__call__
        return False

    def get_sub_properties(
        self, domain_value: Optional[Any] = None
    ) -> Iterable["PropertyDescriptor"]:
        """Return sub-properties declared on the domain type.

        The result is cached per domain class and per descriptor subclass.
        """
        domain_value = domain_value or self.domain_value
        owner = domain_value.__class__
        prop_cls: Type[PropertyDescriptor] = self.__class__

        # Two-level cache: domain class -> (descriptor subclass -> tuple of sub-props)
        level1: Dict[Type, Dict[Type, Tuple[PropertyDescriptor, ...]]] = (
            self._subprops_cache
        )
        per_owner = level1.get(owner)
        if per_owner is not None:
            cached = per_owner.get(prop_cls)
            if cached is not None:
                return cached

        # Compute and store
        props: Tuple[PropertyDescriptor, ...] = tuple(
            getattr(owner, name)
            for name in dir(owner)
            if not name.startswith("_")
            for attr in (getattr(owner, name),)
            if issubclass(type(attr), prop_cls)
        )

        if per_owner is None:
            per_owner = {}
            level1[owner] = per_owner
        per_owner[prop_cls] = props
        return props

    @classmethod
    def clear_subproperties_cache(cls, owner: Optional[Type] = None) -> None:
        """Clear the sub-properties cache.

        If a domain class is provided, only its cached entries are removed.
        Use this when mutating classes at runtime.
        """
        cache: WeakKeyDictionary = cls._subprops_cache
        if owner is None:
            cache.clear()
            return
        per_owner = cache.get(owner)
        if per_owner is not None:
            per_owner.clear()
            # Remove the empty mapping for cleanliness
            try:
                del cache[owner]
            except KeyError:
                pass
