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
    Union,
)
from weakref import WeakKeyDictionary

from line_profiler import profile
from typing_extensions import DefaultDict

from .failures import UnMonitoredContainerTypeForDescriptor
from .monitored_container import (
    MonitoredContainer,
    monitored_type_map,
    MonitoredList,
    MonitoredSet,
)
from .predicate import Symbol
from .symbol_graph import SymbolGraph
from .utils import make_set, is_iterable
from ..class_diagrams.class_diagram import WrappedClass
from ..class_diagrams.wrapped_field import WrappedField

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

    def on_add(self, domain_value, val: Symbol, inferred: bool = False) -> None:
        """Add a value to the property descriptor."""
        self.add_relation(domain_value, val, inferred=inferred)

    def __get__(self, obj, objtype=None):
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
        if isinstance(value, PropertyDescriptor):
            return
        attr = getattr(obj, self.private_attr_name)
        if isinstance(attr, MonitoredContainer):
            attr._clear()
            for v in make_set(value):
                attr._add_item(v, call_on_add=False)
                self.add_relation(obj, v, set_attr=False)
        else:
            setattr(obj, self.private_attr_name, value)
            self.on_add(obj, value)

    def update_value(
        self,
        domain_value: Symbol,
        range_value: Symbol,
        inferred: bool = False,
    ) -> None:
        """Update the value of the managed attribute

        :param domain_value: The domain value to update (i.e., the instance that this descriptor is attached to).
        :param range_value: The range value to update (i.e., the value to set on the managed attribute).
        :param inferred: Whether the update is due to an inferred relation.
        """
        v = getattr(domain_value, self.private_attr_name)
        updated = False
        if isinstance(v, MonitoredContainer):
            updated = v._update(range_value, call_on_add=False)
        elif v != range_value:
            setattr(domain_value, self.private_attr_name, range_value)
            updated = True
        if not updated:
            return
        for super_domain, super_field in self.get_super_properties(domain_value):
            super_descriptor = super_field.property_descriptor
            super_descriptor.update_value(super_domain, range_value, inferred=True)
        if self.inverse_of:
            inverse_domain, inverse_field = self.get_inverse_field(range_value)
            inverse_field.property_descriptor.update_value(
                inverse_domain, domain_value, inferred=True
            )
        self.add_transitive_relations_to_graph()

    def get_super_properties(
        self, value: Symbol
    ) -> Iterable[Tuple[Symbol, WrappedField]]:
        """
        Find neighboring symbols connected by super edges.

        This method identifies neighboring symbols that are connected
        through edge with predicate types that are superclasses of the current predicate.

        :param value: The symbol for which neighboring symbols are
                evaluated through super predicate type edges.

        :return: A list containing neighboring symbols connected by super type edges.
        """
        class_diagram = SymbolGraph().class_diagram
        wrapped_cls = class_diagram.get_wrapped_class(type(value))
        if not wrapped_cls:
            return
        yield from (
            (value, f)
            for f in class_diagram.get_fields_of_superclass_property_descriptors(
                wrapped_cls, self.__class__
            )
        )
        role_taker_property_fields = class_diagram.get_role_taker_superclass_properties(
            wrapped_cls, self.__class__
        )
        if not role_taker_property_fields:
            return
        yield from (
            (getattr(value, role_taker_property_fields.role_taker.public_name), f)
            for f in role_taker_property_fields.fields
        )

    def get_inverse_field(self, obj: Symbol) -> Tuple[Symbol, WrappedField]:
        """
        Get the inverse of the property descriptor.

        :param obj: The object that has the property descriptor.
        :return: The inverse property descriptor field.
        """
        symbol_graph = SymbolGraph()
        class_diagram = symbol_graph.class_diagram
        obj_type = type(obj)
        inverse_field = class_diagram.get_the_field_of_property_descriptor_type(
            obj_type, self.inverse_of
        )
        if not inverse_field:
            role_taker, inverse_field = (
                self.get_inverse_field_from_role_taker_of_object(obj)
            )
            if inverse_field:
                return role_taker, inverse_field
            else:
                raise ValueError(
                    f"cannot find a field for the inverse {self.inverse_of} defined for {obj_type}"
                )
        return obj, inverse_field

    def get_inverse_field_from_role_taker_of_object(
        self, obj: Symbol
    ) -> Tuple[Optional[Symbol], Optional[WrappedField]]:
        """
        Get the inverse field of the property descriptor from the role taker of the object if it exists.

        :param obj: The object that has a role taker with a possible inverse descriptor of the current descriptor.
        :return: The wrapped field of the inverse descriptor if it exists, None otherwise.
        """
        symbol_graph = SymbolGraph()
        class_diagram = symbol_graph.class_diagram
        role_taker = symbol_graph.get_role_takers_of_instance(obj)
        role_taker_wrapped_cls = class_diagram.get_wrapped_class(type(role_taker))
        if role_taker:
            inverse_field = class_diagram.get_the_field_of_property_descriptor_type(
                role_taker_wrapped_cls, self.inverse_of
            )
            return role_taker, inverse_field
        return None, None

    def add_transitive_relations_to_graph(self, range_value: Symbol):
        """
        Add all transitive relations of this relation type that results from adding this relation to the graph.
        """
        if self.transitive:
            wrapped_instance = SymbolGraph().get_wrapped_instance(range_value)
            for nxt in wrapped_instance.neighbors_with_relation_type(self.__class__):
                self.__class__(self.source, nxt, inferred=True).add_to_graph()
            for nxt in self.source.neighbors_with_relation_type(
                self.__class__, outgoing=False
            ):
                self.__class__(nxt, self.target, inferred=True).add_to_graph()

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
