from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps, lru_cache
from typing import Self, Dict

from typing_extensions import (
    Callable,
    Optional,
    Any,
    Type,
    Tuple,
    ClassVar,
)

from .enums import PredicateType, EQLMode
from .symbol_graph import (
    WrappedInstance,
    SymbolGraph,
)
from .symbolic import (
    T,
    SymbolicExpression,
    in_symbolic_mode,
    Variable,
    An,
    Entity,
    properties_to_expression_tree,
    From,
    CanBehaveLikeAVariable,
)
from .utils import is_iterable
from ..utils import recursive_subclasses

cls_args = {}
"""
Cache of class arguments.
"""


def symbolic_function(
    function: Callable[..., T],
) -> Callable[..., SymbolicExpression[T]]:
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
        function_arg_names = [
            pname
            for pname, p in inspect.signature(function).parameters.items()
            if p.default == inspect.Parameter.empty
        ]
        kwargs.update(dict(zip(function_arg_names, args)))
        return Variable(
            _name__=function.__name__,
            _type_=function,
            _kwargs_=kwargs,
            _predicate_type_=PredicateType.DecoratedMethod,
        )
        return function(*args, **kwargs)

    return wrapper


@dataclass
class Symbol:
    """Base class for things that can be described by property descriptors."""

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        update_cache(instance)
        return instance

    @classmethod
    def _symbolic_new_(cls, *args, **kwargs):
        predicate_type = (
            PredicateType.SubClassOfPredicate if issubclass(cls, Predicate) else None
        )
        domain, kwargs = update_domain_and_kwargs_from_args(cls, *args, **kwargs)
        # This mode is when we try to infer new instances of variables, this includes also evaluating predicates
        # because they also need to be inferred. So basically this mode is when there is no domain available and
        # we need to infer new values.
        if not domain and (in_symbolic_mode(EQLMode.Rule) or predicate_type):
            var = Variable(
                _name__=cls.__name__,
                _type_=cls,
                _kwargs_=kwargs,
                _predicate_type_=predicate_type,
            )
            return var
        else:
            # In this mode, we either have a domain through the `domain` provided here, or through the cache if
            # the domain is not provided. Then we filter this domain by the provided constraints on the variable
            # attributes given as keyword arguments.
            var, expression = extract_selected_variable_and_expression(
                cls, domain, predicate_type, **kwargs
            )
            return An(Entity(expression, [var])) if expression else var


@dataclass(eq=False)
class Predicate(Symbol, ABC):
    """
    The super predicate class that represents a filtration operation or asserts a relation.
    """

    is_expensive: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs):
        all_kwargs = {}
        for name, arg in zip(get_cls_args(cls)[1:], args):
            all_kwargs[name] = arg

        all_kwargs.update(kwargs)

        if cls._any_of_the_kwargs_is_a_variable(all_kwargs):
            return Variable(
                _type_=cls,
                _name__=cls.__name__,
                _kwargs_=all_kwargs,
                _predicate_type_=PredicateType.SubClassOfPredicate,
            )
        return super().__new__(cls)

    @classmethod
    def _any_of_the_kwargs_is_a_variable(cls, bindings: Dict[str, Any]) -> bool:
        return any(
            isinstance(binding, CanBehaveLikeAVariable) for binding in bindings.values()
        )

    @abstractmethod
    def __call__(self) -> bool:
        """
        Evaluate the predicate for the supplied values.
        """


@dataclass(eq=False)
class HasType(Predicate):
    """
    Represents a predicate to check if a given variable is an instance of a specified type.

    This class is used to evaluate whether the domain value belongs to a given type by leveraging
    Python's built-in `isinstance` functionality. It provides methods to retrieve the domain and
    range values and perform direct checks.
    """

    variable: Any
    """
    The variable whose type is being checked.
    """
    types_: Type
    """
    The type or tuple of types against which the `variable` is validated.
    """

    def __call__(self) -> bool:
        return isinstance(self.variable, self.types_)


@dataclass(eq=False)
class HasTypes(HasType):
    """
    Represents a specialized data structure holding multiple types.

    This class is a data container designed to store and manage a tuple of
    types. It inherits from the `HasType` class and extends its functionality
    to handle multiple types efficiently. The primary goal of this class is to
    allow structured representation and access to a collection of type
    information with equality comparison explicitly disabled.
    """

    types_: Tuple[Type, ...]
    """
    A tuple containing Type objects that are associated with this instance.
    """


def update_domain_and_kwargs_from_args(symbolic_cls: Type, *args, **kwargs):
    """
    Set the domain if provided as the first argument and update the kwargs with the remaining arguments.

    :param symbolic_cls: The constructed class.
    :param args: The positional arguments to the class constructor and optionally the domain.
    :param kwargs: The keyword arguments to the class constructor.
    :return: The domain and updated kwargs.
    """
    domain = None
    get_cls_args(symbolic_cls)
    init_args = cls_args[symbolic_cls]
    for i, arg in enumerate(args):
        if isinstance(arg, From):
            domain = arg
            if i != 1:
                raise ValueError(
                    f"First non-keyword-argument to {symbolic_cls.__name__} in symbolic mode should be"
                    f" a domain using `From()`."
                )
        elif i > 0:
            arg_name = init_args[i]  # to skip `self`
            kwargs[arg_name] = arg
    return domain, kwargs


def extract_selected_variable_and_expression(
    symbolic_cls: Type,
    domain: Optional[From] = None,
    predicate_type: Optional[PredicateType] = None,
    **kwargs,
):
    """
    Extracts a variable and constructs its expression tree for the given symbolic class.

    This function generates a variable of the specified `symbolic_cls` and uses the
    provided domain, predicate type, and additional arguments to create its expression
    tree. The domain can optionally be filtered when iterating through its elements
    if specified or retrieved from the cache keys associated with the symbolic class.

    :param symbolic_cls: The symbolic class type to be used for variable creation.
    :param domain: Optional domain to provide constraints for the variable.
    :param predicate_type: Optional predicate type associated with the variable.
    :param kwargs: Additional properties to define and construct the variable.
    :return: A tuple containing the generated variable and its corresponding expression tree.
    """
    cache_keys = [symbolic_cls] + recursive_subclasses(symbolic_cls)
    if not domain and cache_keys:
        domain = From(
            (
                instance
                for instance in SymbolGraph()._class_to_wrapped_instances[symbolic_cls]
            )
        )
    elif domain and is_iterable(domain.domain):
        domain.domain = filter(lambda v: isinstance(v, symbolic_cls), domain.domain)

    var = Variable(
        _name__=symbolic_cls.__name__,
        _type_=symbolic_cls,
        _domain_source_=domain,
        _predicate_type_=predicate_type,
    )

    expression = properties_to_expression_tree(var, kwargs)

    return var, expression


def update_cache(instance: Symbol):
    """
    Updates the cache with the given instance of a symbolic type.

    :param instance: The symbolic instance to be cached.
    """
    if not isinstance(instance, Predicate):
        SymbolGraph().add_node(WrappedInstance(instance))


@lru_cache
def get_cls_args(symbolic_cls: Type):
    """
    Updates the global `cls_args` dictionary with the constructor arguments
    of the given symbolic class, if it is not already present. The keys in
    `cls_args` are symbolic class types, and the values are lists of
    constructor parameter names for those classes.

    This function inspects the signature of the `__init__` method of the
    given symbolic class and stores the parameter names if the class
    is not already in the global `cls_args`.

    :param symbolic_cls: A symbolic class type to be inspected.
    """
    return list(inspect.signature(symbolic_cls.__init__).parameters.keys())
