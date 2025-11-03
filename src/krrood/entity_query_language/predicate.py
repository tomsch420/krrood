from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps

from typing_extensions import (
    Callable,
    Optional,
    Any,
    Type,
    Tuple,
    ClassVar,
    Iterable,
)

from .enums import PredicateType, EQLMode
from .symbol_graph import (
    PredicateClassRelation,
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
    ResultQuantifier,
    AND,
    properties_to_expression_tree,
    From,
)
from .utils import is_iterable, make_list
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
        if in_symbolic_mode():
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
        if in_symbolic_mode():
            return cls._symbolic_new_(cls, *args, **kwargs)
        else:
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
                _is_indexed_=index_class_cache(cls),
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

    @abstractmethod
    def __call__(self) -> bool:
        """
        Evaluate the predicate for the supplied values.
        """


@dataclass(eq=False)
class BinaryPredicate(Predicate, ABC):
    """
    A predicate that has a domain and a range.
    """

    transitive: ClassVar[bool] = False
    inverse_of: ClassVar[Optional[Type[BinaryPredicate]]] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.inverse_of is not None:
            if not isinstance(cls.inverse_of, type) or not issubclass(
                cls.inverse_of, BinaryPredicate
            ):
                raise TypeError("inverse_of must be set to a Predicate subclass")
            if cls.inverse_of.inverse_of is None:
                cls.inverse_of.inverse_of = cls

    @classmethod
    @abstractmethod
    def holds_direct(
        cls,
        domain_value: Symbol,
        range_value: Symbol,
    ) -> bool:
        """
        Return True if the relation holds directly (non-transitively) between
        the given domain and range values.
        """
        ...

    @property
    def domain_value(self):
        """
        Property that retrieves the domain value for the current instance.

        This property should be implemented in a subclass where it returns
        the specific domain value. Attempting to access it directly from
        this base implementation will raise a NotImplementedError.

        :raise: NotImplementedError: If the property is accessed and not
                implemented in a subclass.
        """
        raise NotImplementedError

    @property
    def range_value(self):
        """
        Gets the range value. This is an abstract property and must be implemented
        by subclasses to return a value indicating the range.

        :raises NotImplementedError: If not implemented in a subclass.
        """
        raise NotImplementedError

    @classmethod
    def _neighbors(cls, value: Symbol, outgoing: bool = True) -> Iterable[Symbol]:
        """
        Return direct neighbors of the given value to traverse when transitivity is enabled.
        Default is no neighbors (non-transitive or leaf).

        :param value: The value to get neighbors for.
        :param outgoing: Whether to get outgoing neighbors or incoming neighbors.
        :return: Iterable of neighbors.
        """
        wrapped_instance = SymbolGraph().get_wrapped_instance(value)
        if not wrapped_instance:
            return
        if outgoing:
            yield from (
                n.instance
                for n in SymbolGraph().get_outgoing_neighbors_with_predicate_type(
                    wrapped_instance, cls
                )
            )
        else:
            yield from (
                n.instance
                for n in SymbolGraph().get_incoming_neighbors_with_predicate_type(
                    wrapped_instance, cls
                )
            )

    def __call__(
        self,
        domain_value: Optional[Symbol] = None,
        range_value: Optional[Symbol] = None,
    ) -> bool:
        """
        Evaluate the predicate for the supplied values. If `transitive` is set,
        perform a graph traversal using `_neighbors` to determine reachability,
        otherwise rely on `_holds_direct` only.
        """
        domain_value = domain_value or self.domain_value
        range_value = range_value or self.range_value
        return self.holds_direct(domain_value, range_value)

    def add_relation(
        cls,
        domain_value: Symbol,
        range_value: Symbol,
        inferred: bool = False,
    ):
        if range_value is None:
            raise ValueError(
                f"range_value cannot be None for {cls}, domain={domain_value}"
            )
        range_value = make_list(range_value)
        for rv in range_value:
            SymbolGraph().add_edge(cls.get_relation(domain_value, rv, inferred))
            if cls.transitive:
                for nxt in cls._neighbors(rv):
                    cls.add_relation(domain_value, nxt, inferred=True)
                for nxt in cls._neighbors(domain_value, outgoing=False):
                    cls.add_relation(nxt, rv, inferred=True)

    @classmethod
    def get_relation(
        cls,
        domain_value: Symbol,
        range_value: Symbol,
        inferred: bool = False,
    ) -> PredicateClassRelation:
        """
        Gets or creates a relation between two symbols, representing the domain and range
        values. The function ensures that the symbols are wrapped in instances, adding
        them to the symbol graph if they do not already exist. It then creates and returns
        a `PredicateRelation` object linking the domain and range symbols.

        :param domain_value: The symbol representing the domain value.
        :param range_value: The symbol representing the range value.
        :param inferred: A boolean flag indicating whether the relationship is inferred. Defaults to False.

        :return: A `PredicateRelation` instance that links the given domain and range values.
        """
        wrapped_domain_instance = SymbolGraph().get_wrapped_instance(domain_value)
        if not wrapped_domain_instance:
            wrapped_domain_instance = WrappedInstance(domain_value)
            SymbolGraph().add_node(wrapped_domain_instance)
        wrapped_range_instance = SymbolGraph().get_wrapped_instance(range_value)
        if not wrapped_range_instance:
            wrapped_range_instance = WrappedInstance(range_value)
            SymbolGraph().add_node(wrapped_range_instance)
        return PredicateClassRelation(
            wrapped_domain_instance,
            wrapped_range_instance,
            cls(domain_value, range_value),
            inferred=inferred,
        )


@dataclass(eq=False)
class HasType(BinaryPredicate):
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

    @classmethod
    def holds_direct(cls, domain_value: Any, range_value: Type) -> bool:
        return isinstance(domain_value, range_value)

    @property
    def domain_value(self):
        return self.variable

    @property
    def range_value(self):
        return self.types_


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


def bind_first_argument_of_predicate_if_in_query_context(
    node: SymbolicExpression, predicate_type: Optional[PredicateType], *args
):
    """
    Binds the first argument of a predicate to a result quantifier's selected variable if
    in a query context and predicate type is specified.

    :param node: The symbolic expression node to evaluate or use.
    :param predicate_type: The type of predicate, can be None.
    :param args: Additional arguments to bind with the predicate.

    :return: A list of arguments where the first argument of the predicate is potentially
        replaced by the result quantifier's selected variable.
    """
    if predicate_type and node and in_symbolic_mode(EQLMode.Query):
        if not isinstance(node, ResultQuantifier):
            result_quantifier = node._parent_._parent_
        else:
            result_quantifier = node
        args = list(args)
        args.insert(1, result_quantifier._child_.selected_variables[0])
    return args


def update_query_child_expression_if_in_query_context(
    node: SymbolicExpression,
    predicate_type: Optional[PredicateType],
    var: SymbolicExpression,
):
    """
    Updates the child expression of a given symbolic expression node in the context of a
    query mode. This function modifies the structure of the symbolic expression to inject
    a logical condition involving the provided variable, based on the specified predicate
    type and the current query mode.

    :param node: The symbolic expression node whose child expression may be updated.
    :param predicate_type: The type of logical predicate guiding the behavior of this update.
    :param var: The symbolic expression to be integrated into the node's child expression if applicable.
    :raise: AssertionError: If any condition for in_symbolic_mode or other logical assertions fail during
        execution.
    """
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
        domain = From(lambda: SymbolGraph()._class_to_wrapped_instances[symbolic_cls])
    elif domain and is_iterable(domain.domain):
        domain.domain = filter(lambda v: isinstance(v, symbolic_cls), domain.domain)

    var = Variable(
        _name__=symbolic_cls.__name__,
        _type_=symbolic_cls,
        _domain_source_=domain,
        _predicate_type_=predicate_type,
        _is_indexed_=index_class_cache(symbolic_cls),
    )

    expression, _ = properties_to_expression_tree(var, kwargs)

    return var, expression


def update_cache(instance: Symbol):
    """
    Updates the cache with the given instance of a symbolic type. The function ensures
    proper handling of symbolic class cache, updates associated arguments, and adds
    relevant instances to the variable cache and symbol graph. This function operates
    based on the type and characteristics of the given instance.

    :param instance: The symbolic instance to be cached, which can include types such as
        Symbol or BinaryPredicate, among others.
    :return: Returns the updated instance that has been added to the cache.
    """
    SymbolGraph().add_node(WrappedInstance(instance))
    return instance


def update_cls_args(symbolic_cls: Type):
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
    global cls_args
    if symbolic_cls not in cls_args:
        cls_args[symbolic_cls] = list(
            inspect.signature(symbolic_cls.__init__).parameters.keys()
        )


def index_class_cache(symbolic_cls: Type) -> bool:
    """
    Determine whether the class cache should be indexed.

    :param symbolic_cls: The symbolic class type.
    """
    return issubclass(symbolic_cls, BinaryPredicate) and symbolic_cls.is_expensive
