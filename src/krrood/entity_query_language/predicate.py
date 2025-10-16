from __future__ import annotations

import inspect
import typing
from abc import ABC, abstractmethod
from collections import deque
from copy import copy
from dataclasses import dataclass, field, Field, fields
from functools import wraps, cached_property
from typing import (
    Iterable,
    List,
    Type,
    dataclass_transform,
    Optional,
    Callable,
    TypeVar,
    Generic,
    ClassVar,
    Set,
    Any,
)

from typing_extensions import Callable, Optional, Any, Type, Tuple

from typing_extensions import ClassVar

from .cache_data import get_cache_keys_for_class_, yield_class_values_from_cache
from .enums import PredicateType, EQLMode
from .hashed_data import HashedValue
from .symbol_graph import PredicateRelation, SymbolGraph, WrappedInstance
from .symbolic import (
    T,
    SymbolicExpression,
    in_symbolic_mode,
    Variable,
    An,
    Entity,
    ResultQuantifier,
    AND,
    properties_to_expression_tree,
    From,
)
from .typing_utils import get_range_types
from .utils import is_iterable, make_list, make_set
from ..class_diagrams import ClassDiagram


symbols_registry: typing.Set[Type] = set()
cls_args = {}


def predicate(function: Callable[..., T]) -> Callable[..., SymbolicExpression[T]]:
    """
    Function decorator that constructs a symbolic expression representing the function call
     when inside a symbolic_rule context.

    When symbolic mode is active, calling the method returns a Call instance which is a SymbolicExpression bound to
    representing the method call that is not evaluated until the evaluate() method is called on the query/rule.

    :param function: The function to decorate.
    :return: The decorated function.
    """

    @wraps(function)
    def wrapper(*args, **kwargs) -> Optional[Any]:
        if in_symbolic_mode():
            function_arg_names = [
                pname
                for pname, p in inspect.signature(function).parameters.items()
                if p.default == inspect.Parameter.empty
            ]
            kwargs.update(dict(zip(function_arg_names, args)))
            return Variable(
                function.__name__,
                function,
                _kwargs_=kwargs,
                _predicate_type_=PredicateType.DecoratedMethod,
            )
        return function(*args, **kwargs)

    return wrapper


def recursive_subclasses(cls_):
    subclasses = cls_.__subclasses__()
    for subclass in subclasses:
        yield from recursive_subclasses(subclass)
        yield subclass


class DescriptionMeta(type):
    """Metaclass that recognizes PropertyDescriptor class attributes and wires backing storage."""

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        for attr_name, attr_value in attrs.items():
            if attr_value.__class__.__name__ != "PropertyDescriptor":
                continue
            attr_value.create_managed_attribute_for_class(new_class, attr_name)


@dataclass
class Symbol:
    """Base class for things that can be described by property descriptors."""

    def __new__(cls, *args, **kwargs):
        if in_symbolic_mode():
            return cls._symbolic_new_(cls, *args, **kwargs)
        else:
            instance = instantiate_class_and_update_cache(
                cls, super().__new__, *args, **kwargs
            )
            symbols_registry.add(cls)
            return instance

    @classmethod
    def _symbolic_new_(cls, *args, **kwargs):
        predicate_type = (
            PredicateType.SubClassOfPredicate if issubclass(cls, Predicate) else None
        )
        node = SymbolicExpression._current_parent_()
        args = bind_first_argument_of_predicate_if_in_query_context(
            node, predicate_type, *args
        )
        domain, kwargs = update_domain_and_kwargs_from_args(cls, *args, **kwargs)
        # This mode is when we try to infer new instances of variables, this includes also evaluating predicates
        # because they also need to be inferred. So basically this mode is when there is no domain available and
        # we need to infer new values.
        if not domain and (in_symbolic_mode(EQLMode.Rule) or predicate_type):
            var = Variable(
                cls.__name__,
                cls,
                _kwargs_=kwargs,
                _predicate_type_=predicate_type,
                _is_indexed_=index_class_cache(cls),
            )
            update_query_child_expression_if_in_query_context(node, predicate_type, var)
            return var
        else:
            # In this mode, we either have a domain through the `domain` provided here, or through the cache if
            # the domain is not provided. Then we filter this domain by the provided constraints on the variable
            # attributes given as keyword arguments.
            var, expression = extract_selected_variable_and_expression(
                cls, domain, predicate_type, **kwargs
            )
            return An(Entity(expression, [var])) if expression else var


class ThingMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        for attr_name, attr_value in attrs.items():
            if attr_name.startswith("__"):
                continue
            if isinstance(attr_value, Field):
                if isinstance(attr_value.default_factory, type) and issubclass(
                    attr_value.default_factory, PropertyDescriptor
                ):
                    instance = attr_value.default_factory()
                    instance.create_managed_attribute_for_class(cls, attr_name)
                    attr_value.default_factory = lambda: instance


@dataclass
class Thing(Symbol, metaclass=ThingMeta): ...


@dataclass(eq=False)
class Predicate(Symbol, ABC):
    """
    The super predicate class that represents a filtration operation.
    """

    is_expensive: ClassVar[bool] = False
    transitive: ClassVar[bool] = False
    inverse_of: ClassVar[Optional[Type[Predicate]]] = None
    symbol_graph: ClassVar[SymbolGraph] = SymbolGraph(ClassDiagram([]))

    @classmethod
    def build_symbol_graph(cls, classes: List[Type] = None):
        if not classes:
            for cls_ in copy(symbols_registry):
                symbols_registry.update(recursive_subclasses(cls_))
            classes = symbols_registry
        cls.symbol_graph = SymbolGraph(ClassDiagram(list(classes)))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        inverse = getattr(cls, "inverse_of", None)
        if inverse is not None:
            if not isinstance(inverse, type) or not issubclass(inverse, Predicate):
                raise TypeError("inverse_of must be set to a Predicate subclass")
            if getattr(inverse, "inverse_of", None) is None:
                inverse.inverse_of = cls

    @property
    @abstractmethod
    def domain_value(self): ...

    @property
    @abstractmethod
    def range_value(self): ...

    # New: subclasses implement these two hooks.
    @abstractmethod
    def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
        """
        Return True if the relation holds directly (non-transitively) between
        the given domain and range values.
        """
        ...

    def _neighbors(self, value: Any) -> Iterable[Any]:
        """
        Return direct neighbors of the given value to traverse when transitivity is enabled.
        Default is no neighbors (non-transitive or leaf).
        """
        wrapped_instance = self.symbol_graph.get_wrapped_instance(value)
        if not wrapped_instance:
            return
        yield from (
            n.instance
            for n in self.symbol_graph.get_outgoing_neighbors_with_edge_type(
                wrapped_instance, self.__class__
            )
        )

    def __call__(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        """
        Evaluate the predicate for the supplied values. If `transitive` is set,
        perform a graph traversal using `_neighbors` to determine reachability,
        otherwise rely on `_holds_direct` only.
        """
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value

        if self._holds_direct(domain_value, range_value):
            self.add_relation(domain_value, range_value)
            return True
        if not self.transitive:
            return False

        # BFS with cycle protection
        visited = set()
        queue = deque()

        start = HashedValue(domain_value)
        visited.add(start)
        queue.append(domain_value)

        while queue:
            current = queue.popleft()
            for nxt in self._neighbors(current):
                if self._holds_direct(nxt, range_value):
                    self.add_relation(domain_value, range_value, inferred=True)
                    return True
                key = HashedValue(nxt)
                if key not in visited:
                    visited.add(key)
                    queue.append(nxt)
        return False

    @property
    def inverse(self) -> Optional[Predicate]:
        return None

    def add_relation(
        self,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
        inferred: bool = False,
    ):
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        if range_value is None:
            raise ValueError(
                f"range_value cannot be None for {self.__class__}, domain={domain_value}"
            )
        range_value = make_list(range_value)
        for rv in range_value:
            self.symbol_graph.add_edge(self.get_relation(domain_value, rv, inferred))
            if self.inverse:
                self.inverse.add_relation(rv, domain_value)

    def get_relation(
        self,
        domain_value: Optional[Any] = None,
        range_value: Optional[Any] = None,
        inferred: bool = False,
    ) -> PredicateRelation:
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        wrapped_domain_instance = self.symbol_graph.get_wrapped_instance(domain_value)
        if not wrapped_domain_instance:
            wrapped_domain_instance = WrappedInstance(domain_value)
            self.symbol_graph.add_node(wrapped_domain_instance)
        wrapped_range_instance = self.symbol_graph.get_wrapped_instance(range_value)
        if not wrapped_range_instance:
            wrapped_range_instance = WrappedInstance(range_value)
            self.symbol_graph.add_node(wrapped_range_instance)
        return PredicateRelation(
            wrapped_domain_instance,
            wrapped_range_instance,
            self,
            inferred=inferred,
        )


@dataclass(eq=False)
class HasType(Predicate):
    variable: Any
    types_: Type
    is_expensive: ClassVar[bool] = False

    def _holds_direct(
        self, domain_value: Optional[Any] = None, range_value: Optional[Any] = None
    ) -> bool:
        return isinstance(self.variable, self.types_)

    @property
    def domain_value(self):
        return self.variable

    @property
    def range_value(self):
        return self.types_


@dataclass(eq=False)
class HasTypes(HasType):
    types_: Tuple[Type, ...]


def bind_first_argument_of_predicate_if_in_query_context(
    node: SymbolicExpression, predicate_type: Optional[PredicateType], *args
):
    if predicate_type and node and in_symbolic_mode(EQLMode.Query):
        if not isinstance(node, ResultQuantifier):
            result_quantifier = node._parent_._parent_
        else:
            result_quantifier = node
        args = [result_quantifier._child_.selected_variables[0]] + list(args)
    return args


def update_query_child_expression_if_in_query_context(
    node: SymbolicExpression,
    predicate_type: Optional[PredicateType],
    var: SymbolicExpression,
):
    if predicate_type and node and in_symbolic_mode(EQLMode.Query):
        if node._child_._child_:
            node._child_._child_ = AND(node._child_._child_, var)
        else:
            node._child_._child_ = var


def update_domain_and_kwargs_from_args(symbolic_cls: Type, *args, **kwargs):
    """
    Set the domain if provided as the first argument and update the kwargs with the remaining arguments.

    :param symbolic_cls: The constructed class.
    :param args: The positional arguments to the class constructor and optionally the domain.
    :param kwargs: The keyword arguments to the class constructor.
    :return: The domain and updated kwargs.
    """
    domain = None
    update_cls_args(symbolic_cls)
    init_args = cls_args[symbolic_cls]
    for i, arg in enumerate(args):
        if isinstance(arg, From):
            domain = arg
            if i != 1:
                raise ValueError(
                    f"First non-keyword-argument to {symbolic_cls.__name__} in symbolic mode should be"
                    f" a domain using `From()`."
                )
        elif 0 < i < (len(args) - 1):
            arg_name = init_args[i + 1]  # to skip `self`
            kwargs[arg_name] = arg
    return domain, kwargs


def extract_selected_variable_and_expression(
    symbolic_cls: Type,
    domain: Optional[From] = None,
    predicate_type: Optional[PredicateType] = None,
    **kwargs,
):
    """
    :param symbolic_cls: The constructed class.
    :param domain: The domain source for the values of the variable by.
    :param predicate_type: The predicate type.
    :param kwargs: The keyword arguments to the class constructor.
    :return: The selected variable and expression.
    """
    cache_keys = get_cache_keys_for_class_(Variable._cache_, symbolic_cls)
    if not domain and cache_keys:
        domain = From(
            (
                v
                for a, v in yield_class_values_from_cache(
                    Variable._cache_,
                    symbolic_cls,
                    from_index=False,
                    cache_keys=cache_keys,
                )
            )
        )
    elif domain and is_iterable(domain.domain):
        domain.domain = filter(lambda v: isinstance(v, symbolic_cls), domain.domain)

    var = Variable(
        symbolic_cls.__name__,
        symbolic_cls,
        _domain_source_=domain,
        _predicate_type_=predicate_type,
        _is_indexed_=index_class_cache(symbolic_cls),
    )

    expression, _ = properties_to_expression_tree(var, kwargs)

    return var, expression


def instantiate_class_and_update_cache(
    symbolic_cls: Type, original_new: Callable, *args, **kwargs
):
    """
    :param symbolic_cls: The constructed class.
    :param original_new: The original class __new__ method.
    :param args: The positional arguments to the class constructor.
    :param kwargs: The keyword arguments to the class constructor.
    :return: The instantiated class.
    """
    instance = original_new(symbolic_cls)
    index = index_class_cache(symbolic_cls)
    if index:
        update_cls_args(symbolic_cls)
        kwargs = {
            f: HashedValue(getattr(instance, f)) for f in cls_args[symbolic_cls][1:]
        }
        if (
            symbolic_cls not in Variable._cache_
            or not Variable._cache_[symbolic_cls].keys
        ):
            Variable._cache_[symbolic_cls].keys = kwargs.keys()
    else:
        kwargs = {}
    Variable._cache_[symbolic_cls].insert(kwargs, HashedValue(instance), index=index)
    if not isinstance(instance, Predicate):
        Predicate.symbol_graph.add_node(WrappedInstance(instance))
    return instance


def update_cls_args(symbolic_cls: Type):
    global cls_args
    if symbolic_cls not in cls_args:
        cls_args[symbolic_cls] = list(
            inspect.signature(symbolic_cls.__init__).parameters.keys()
        )


def index_class_cache(symbolic_cls: Type) -> bool:
    """
    Determine whether the class cache should be indexed.
    """
    return issubclass(symbolic_cls, Predicate) and symbolic_cls.is_expensive


T = TypeVar("T")


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

    def __set_name__(self, owner, name):
        # Only wire once per owner
        if not hasattr(owner, self.attr_name):
            self.create_managed_attribute_for_class(owner, name)

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
        self.add_relation(obj, value)

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
        # Otherwise, look through sub-properties of this property.
        return self._check_relation_holds_for_subclasses_of_property(
            domain_value=domain_value, range_value=range_value
        )

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
    ) -> Iterable[PropertyDescriptor]:
        domain_value = domain_value or self.domain_value
        for f in fields(domain_value):
            if issubclass(type(f.default), self.__class__):
                yield f.default
