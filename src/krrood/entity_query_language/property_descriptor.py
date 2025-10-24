from __future__ import annotations

from copy import copy
from dataclasses import Field, dataclass, field, MISSING, fields
from functools import cached_property
from typing import (
    Generic,
    ClassVar,
    Set,
    Type,
    Optional,
    Any,
    Iterable,
    TypeVar,
    Tuple,
    Dict,
)
from weakref import WeakKeyDictionary, ref as weakref_ref

from line_profiler import profile

from krrood.entity_query_language.predicate import Symbol, T, Predicate
from krrood.entity_query_language.typing_utils import get_range_types
from krrood.entity_query_language.utils import make_set


class ThingMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        for attr_name, attr_value in copy(attrs).items():
            if attr_name.startswith("__"):
                continue
            if isinstance(attr_value, Field):
                if isinstance(attr_value.default_factory, type) and issubclass(
                    attr_value.default_factory, PropertyDescriptor
                ):
                    instance = attr_value.default_factory(_cls_=cls)
                    instance.create_managed_attribute_for_class(cls, attr_name)

                    # Important: remove original annotation so dataclass does not shadow the descriptor
                    if attr_name in cls.__annotations__:
                        del cls.__annotations__[attr_name]

                    # Bind the descriptor at the class attribute name so __get__/__set__ are used
                    setattr(cls, attr_name, instance)


@dataclass
class Thing(Symbol, metaclass=ThingMeta): ...


T = TypeVar("T")


class MonitoredSet(set):

    def __init__(self, *args, **kwargs):
        self.descriptor: PropertyDescriptor = kwargs.pop("descriptor")
        self._owner_ref = None  # weakref to owner instance
        super().__init__(*args, **kwargs)

    def bind_owner(self, owner) -> "MonitoredSet":
        """
        Bind the owning instance via a weak reference and return self.
        """
        # Import locally to avoid top-level dependency if you prefer
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


@dataclass
class PropertyDescriptor(Generic[T], Predicate):
    """Descriptor storing values on instances while keeping type metadata on the descriptor.

    When used on dataclass fields and combined with Thing, the descriptor
    injects a hidden dataclass-managed attribute (backing storage) into the owner class
    and collects domain and range types for introspection.
    """

    domain_types: ClassVar[Set[Type]] = set()
    range_types: ClassVar[Set[Type]] = set()

    _domain_value: Optional[Any] = None
    _range_value: Optional[Any] = None
    _cls_: Optional[Type] = None

    # Cache of discovered sub-properties per domain class and per descriptor subclass.
    # Weak keys prevent memory leaks when domain classes are unloaded.
    _subprops_cache: ClassVar[WeakKeyDictionary] = WeakKeyDictionary()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain_types = set()
        cls.range_types = set()

    @property
    def domain_value(self) -> Optional[Any]:
        return self._domain_value

    @property
    def range_value(self) -> Optional[Any]:
        return self._range_value

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
                default_factory=lambda: MonitoredSet(descriptor=self),
                init=False,
                repr=False,
                hash=False,
            ),
        )
        # Preserve the declared annotation for the hidden field
        cls.__annotations__[self.attr_name] = cls.__annotations__[attr_name]

        self.update_domain_types()
        self.update_range_types()

    def on_add(self, domain_value, val: Symbol, inferred: bool = False) -> None:
        """Add a value to the property descriptor."""
        self.add_relation(domain_value, val, inferred=inferred)

    def update_domain_types(self) -> None:
        """
        Add a class to the domain types if it is not already a subclass of any existing domain type.

        This method is used to keep track of the classes that are valid as values for the property descriptor.
        It does not add a class if it is already a subclass of any existing domain type to avoid infinite recursion.
        :return: None
        """
        cls = self._cls_
        if any(issubclass(cls, domain_type) for domain_type in self.domain_types):
            return
        self.domain_types.add(cls)

    @property
    def range_type(self):
        type_hint = self._cls_.__annotations__[self.attr_name]
        if isinstance(type_hint, str):
            try:
                type_hint = eval(
                    type_hint, vars(__import__(self._cls_.__module__, fromlist=["*"]))
                )
            except NameError:
                # Try again with the class under construction injected; if still failing, skip for now.
                try:
                    module_globals = vars(
                        __import__(self._cls_.__module__, fromlist=["*"])
                    ).copy()
                    module_globals[self._cls_.__name__] = self._cls_
                    type_hint = eval(type_hint, module_globals)
                except NameError:
                    return
        return get_range_types(type_hint)

    def update_range_types(self) -> None:
        range_types = self.range_type
        if range_types is None:
            return
        for new_type in range_types:
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
        container = getattr(obj, self.attr_name)
        # Bind the owner so subsequent `add` calls know the instance
        if getattr(container, "owner", None) is not obj:
            container.bind_owner(obj)
        return container

    def __set__(self, obj, value):
        if isinstance(value, PropertyDescriptor):
            return
        setattr(obj, self.attr_name, value)
        self.add_relation(obj, value, set_attr=False)

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
        if hasattr(domain_value, self.attr_name):
            return self._check_relation_value(
                attr_name=self.attr_name,
                domain_value=domain_value,
                range_value=range_value,
            )
        return False

    @profile
    def _check_relation_holds_for_subclasses_of_property(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        for prop_data in self.get_sub_properties(domain_value):
            if self._check_relation_value(
                prop_data.attr_name, domain_value=domain_value, range_value=range_value
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
