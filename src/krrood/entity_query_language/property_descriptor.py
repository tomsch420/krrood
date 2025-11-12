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
    Dict,
    Union,
)
from weakref import WeakKeyDictionary

from typing_extensions import DefaultDict

from .failures import UnMonitoredContainerTypeForDescriptor
from .monitored_container import (
    MonitoredContainer,
    monitored_type_map,
    MonitoredList,
    MonitoredSet,
)
from .predicate import Symbol
from .symbol_graph import PredicateClassRelation
from .utils import make_set, is_iterable
from ..class_diagrams.class_diagram import WrappedClass
from ..class_diagrams.wrapped_field import WrappedField

SymbolType = Type[Symbol]
"""
Type alias for symbol types.
"""
DomainRangeMap = Dict[SymbolType, SymbolType]
"""
Type alias for the domain-range map.
"""


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
    def range(self) -> SymbolType:
        """
        The range type for this descriptor instance.
        """
        return self.domain_range_map[self.__class__][self.domain]

    @cached_property
    def domain(self) -> SymbolType:
        """
        The domain type for this descriptor instance.
        """
        domain_type = self.wrapped_field.clazz.clazz
        assert issubclass(domain_type, Symbol)
        return domain_type

    def add_relation_to_the_graph(
        self, domain_value: Symbol, range_value: Symbol, inferred: bool = False
    ) -> None:
        """
        Add the relation between the domain_value and the range_value to the symbol graph.

        :param domain_value: The domain value (i.e., the instance that this descriptor is attached to).
        :param range_value: The range value (i.e., the value to set on the managed attribute, and is the target of the
         relation).
        :param inferred: Whether the relation is inferred or not.
        """
        PredicateClassRelation(
            domain_value, range_value, self.wrapped_field, inferred=inferred
        ).add_to_graph()

    def __get__(self, obj, objtype=None):
        """
        Get the value of the managed attribute. In addition, ensure that the value is a monitored container type if
        it is an iterable and that the owner instance is bound to the monitored container.

        :param obj: The owner instance (i.e., the instance that this descriptor is attached to).
        :param objtype: The owner type.
        """
        if obj is None:
            return self
        value = getattr(obj, self.private_attr_name)
        value = self._ensure_monitored_type(value, obj)
        self._bind_owner_if_container_type(value, owner=obj)
        return value

    @staticmethod
    def _bind_owner_if_container_type(
        value: Union[Iterable[Symbol], Symbol], owner: Optional[Any] = None
    ):
        """
        Bind the owner instance to the monitored container if the value is a MonitoredContainer type.

        :param value: The value to check and bind the owner to if it is a MonitoredContainer type.
        :param owner: The owner instance.
        """
        if (
            isinstance(value, MonitoredContainer)
            and getattr(value, "owner", None) is not owner
        ):
            value._bind_owner(owner)

    def _ensure_monitored_type(
        self, value: Union[Iterable[Symbol], Symbol], obj: Optional[Any] = None
    ) -> Union[MonitoredContainer[Symbol], Symbol]:
        """
        Ensure that the value is a monitored container type or is not iterable.

        :param value: The value to ensure its type.
        :param obj: The owner instance.
        :return: The value with a monitored container-type if it is iterable, otherwise the value itself.
        """
        if is_iterable(value) and not isinstance(value, MonitoredContainer):
            try:
                monitored_type = monitored_type_map[type(value)]
            except KeyError:
                raise UnMonitoredContainerTypeForDescriptor(
                    f"Cannot use the descriptor on field {self.wrapped_field} from {obj} because it has a container type"
                    f"that is not monitored (i.e., is not a subclass of {MonitoredContainer}). Either use one of "
                    f"{MonitoredList} or {MonitoredSet} or implement a custom monitored container type."
                )
            value = monitored_type(descriptor=self)
        return value

    def __set__(self, obj, value):
        """
        Set the value of the managed attribute and add it to the symbol graph.

        :param obj: The owner instance.
        :param value: The value to set.
        """
        if isinstance(value, PropertyDescriptor):
            return
        attr = getattr(obj, self.private_attr_name)
        if isinstance(attr, MonitoredContainer):
            attr._clear()
            for v in make_set(value):
                attr._add_item(v, inferred=False)
        else:
            setattr(obj, self.private_attr_name, value)
            self.add_relation_to_the_graph(obj, value)

    def update_value(
        self,
        domain_value: Symbol,
        range_value: Symbol,
    ) -> bool:
        """Update the value of the managed attribute

        :param domain_value: The domain value to update (i.e., the instance that this descriptor is attached to).
        :param range_value: The range value to update (i.e., the value to set on the managed attribute).
        """
        v = getattr(domain_value, self.private_attr_name)
        updated = False
        if isinstance(v, MonitoredContainer):
            updated = v._update(range_value, add_relation_to_the_graph=False)
        elif v != range_value:
            setattr(domain_value, self.private_attr_name, range_value)
            updated = True
        return updated
