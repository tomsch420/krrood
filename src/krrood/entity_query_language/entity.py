from __future__ import annotations

from .symbol_graph import SymbolGraph
from .utils import is_iterable

"""
User interface (grammar & vocabulary) for entity query language.
"""
import operator

from typing_extensions import Any, Optional, Union, Iterable, TypeVar, Type, Tuple, List

from .symbolic import (
    SymbolicExpression,
    Entity,
    SetOf,
    The,
    An,
    AND,
    Comparator,
    chained_logic,
    CanBehaveLikeAVariable,
    ResultQuantifier,
    From,
    Variable,
    optimize_or,
    Flatten,
    ForAll,
    Exists,
    Literal,
)
from .conclusion import Infer

from .predicate import (
    Predicate,
    symbolic_function,  # type: ignore
    Symbol,  # type: ignore
)

T = TypeVar("T")  # Define type variable "T"

ConditionType = Union[SymbolicExpression, bool, Predicate]
"""
The possible types for conditions.
"""
EntityType = Union[SetOf[T], Entity[T], T, Iterable[T], Type[T]]
"""
The possible types for entities.
"""


def an(
    entity_: EntityType,
    at_least: Optional[int] = None,
    at_most: Optional[int] = None,
    exactly: Optional[int] = None,
) -> Union[An[T], T, SymbolicExpression[T]]:
    """
    Select a single element satisfying the given entity description.

    :param entity_: An entity or a set expression to quantify over.
    :param at_least: Optional minimum number of results.
    :param at_most: Optional maximum number of results.
    :param exactly: Optional exact number of results.
    :return: A quantifier representing "an" element.
    :rtype: An[T]
    """
    return select_one_or_select_many_or_infer(
        An, entity_, _at_least_=at_least, _at_most_=at_most, _exactly_=exactly
    )


a = an
"""
This is an alias to accommodate for words not starting with vowels.
"""


def the(
    entity_: EntityType,
) -> Union[The[T], T]:
    """
    Select the unique element satisfying the given entity description.

    :param entity_: An entity or a set expression to quantify over.
    :return: A quantifier representing "an" element.
    :rtype: The[T]
    """
    return select_one_or_select_many_or_infer(The, entity_)


def infer(
    entity_: EntityType,
) -> Infer[T]:
    return select_one_or_select_many_or_infer(Infer, entity_)


def select_one_or_select_many_or_infer(
    quantifier: Type[ResultQuantifier],
    entity_: EntityType,
    **kwargs,
) -> ResultQuantifier[T]:
    """
    Selects one or many entities or infers the result based on the provided quantifier
    and entity type. This function facilitates creating or managing quantified results
    depending on the entity type and additional keyword arguments.

    :param quantifier: A type of ResultQuantifier used to quantify the entity.
    :param entity_: The entity or quantifier to be selected or converted to a quantifier.
    :param kwargs: Additional keyword arguments for quantifier initialization.
    :return: A result quantifier of the provided type, inferred type, or directly the
        one provided.
    :raises ValueError: If the provided entity is invalid.
    """
    if isinstance(entity_, ResultQuantifier):
        if isinstance(entity_, quantifier):
            return entity_

        entity_._child_._parent_ = None
        return quantifier(entity_._child_, **kwargs)

    if isinstance(entity_, (Entity, SetOf)):
        return quantifier(entity_, **kwargs)

    raise ValueError(f"Invalid entity: {entity_}")

def entity(
    selected_variable: T,
    *properties: ConditionType,
) -> Entity[T]:
    """
    Create an entity descriptor from a selected variable and its properties.

    :param selected_variable: The variable to select in the result.
    :type selected_variable: T
    :param properties: Conditions that define the entity.
    :type properties: Union[SymbolicExpression, bool]
    :return: Entity descriptor.
    :rtype: Entity[T]
    """
    selected_variables, expression = _extract_variables_and_expression(
        [selected_variable], *properties
    )
    return Entity(selected_variables=selected_variables, _child_=expression)


def set_of(
    selected_variables: Iterable[T],
    *properties: ConditionType,
) -> SetOf[T]:
    """
    Create a set descriptor from selected variables and their properties.

    :param selected_variables: Iterable of variables to select in the result set.
    :type selected_variables: Iterable[T]
    :param properties: Conditions that define the set.
    :type properties: Union[SymbolicExpression, bool]
    :return: Set descriptor.
    :rtype: SetOf[T]
    """
    selected_variables, expression = _extract_variables_and_expression(
        selected_variables, *properties
    )
    return SetOf(selected_variables=selected_variables, _child_=expression)


def _extract_variables_and_expression(
    selected_variables: Iterable[T], *properties: ConditionType
) -> Tuple[List[T], SymbolicExpression]:
    """
    Extracts the variables and expressions from the selected variables.

    :param selected_variables: Iterable of variables to select in the result set.
    :param properties: Conditions on the selected variables.
    :return: Tuple of selected variables and expressions.
    """
    expression_list = list(properties)
    selected_variables = list(selected_variables)
    expression = None
    if len(expression_list) > 0:
        expression = (
            and_(*expression_list) if len(expression_list) > 1 else expression_list[0]
        )
    return selected_variables, expression


def let(
    type_: Type[T], domain: Optional[Iterable], name: Optional[str] = None
) -> Union[T, CanBehaveLikeAVariable[T], Variable[T]]:
    """
    Declare a symbolic variable that can be used inside queries.

    Filters the domain to elements that are instances of T.

    .. warning::

        If no domain is provided, the domain will be inferred from the SymbolGraph, which may contain unnecessarily many
        elements.

    :param type_: The type of variable.
    :param domain: Iterable of potential values for the variable.
    :param name: The variable name, only required for pretty printing.
    :return: A Variable that can be queried for.
    """
    if domain is None:
        domain = SymbolGraph().get_instances_of_type(type_)
    else:
        if is_iterable(domain):
            domain = filter(lambda x: isinstance(x, type_), domain)

    if name is None:
        name = type_.__name__

    result = Variable(_type_=type_, _domain_source_=From(domain), _name__=name)

    return result


def and_(*conditions: ConditionType):
    """
    Logical conjunction of conditions.

    :param conditions: One or more conditions to combine.
    :type conditions: SymbolicExpression | bool
    :return: An AND operator joining the conditions.
    :rtype: SymbolicExpression
    """
    return chained_logic(AND, *conditions)


def or_(*conditions):
    """
    Logical disjunction of conditions.

    :param conditions: One or more conditions to combine.
    :type conditions: SymbolicExpression | bool
    :return: An OR operator joining the conditions.
    :rtype: SymbolicExpression
    """
    return chained_logic(optimize_or, *conditions)


def not_(operand: SymbolicExpression):
    """
    A symbolic NOT operation that can be used to negate symbolic expressions.
    """
    if not isinstance(operand, SymbolicExpression):
        operand = Literal(operand)
    return operand.__invert__()


def contains(container: Union[Iterable, CanBehaveLikeAVariable[T]], item: Any):
    """
    Check whether a container contains an item.

    :param container: The container expression.
    :param item: The item to look for.
    :return: A comparator expression equivalent to ``item in container``.
    :rtype: SymbolicExpression
    """
    return in_(item, container)


def in_(item: Any, container: Union[Iterable, CanBehaveLikeAVariable[T]]):
    """
    Build a comparator for membership: ``item in container``.

    :param item: The candidate item.
    :param container: The container expression.
    :return: Comparator expression for membership.
    :rtype: Comparator
    """
    return Comparator(container, item, operator.contains)


def flatten(
    var: Union[CanBehaveLikeAVariable[T], Iterable[T]],
) -> Union[CanBehaveLikeAVariable[T], T]:
    """
    Flatten a nested iterable domain into individual items while preserving the parent bindings.
    This returns a DomainMapping that, when evaluated, yields one solution per inner element
    (similar to SQL UNNEST), keeping existing variable bindings intact.
    """
    return Flatten(var)


def for_all(
    universal_variable: Union[CanBehaveLikeAVariable[T], T],
    condition: ConditionType,
):
    """
    A universal on variable that finds all sets of variable bindings (values) that satisfy the condition for **every**
     value of the universal_variable.

    :param universal_variable: The universal on variable that the condition must satisfy for all its values.
    :param condition: A SymbolicExpression or bool representing a condition that must be satisfied.
    :return: A SymbolicExpression that can be evaluated producing every set that satisfies the condition.
    """
    return ForAll(universal_variable, condition)


def exists(
    universal_variable: Union[CanBehaveLikeAVariable[T], T],
    condition: ConditionType,
):
    """
    A universal on variable that finds all sets of variable bindings (values) that satisfy the condition for **any**
     value of the universal_variable.

    :param universal_variable: The universal on variable that the condition must satisfy for any of its values.
    :param condition: A SymbolicExpression or bool representing a condition that must be satisfied.
    :return: A SymbolicExpression that can be evaluated producing every set that satisfies the condition.
    """
    return Exists(universal_variable, condition)


def create(type_: Type[T]) -> Union[Variable[T], Type[T]]:
    """
    This returns a factory function that creates a new variable of the given type and takes keyword arguments for the
    type constructor.

    :param type_: The type of the variable (i.e., The class you want to instantiate).
    :return: The factory function for creating a new variable.
    """
    return lambda **kwargs: Variable(
        _type_=type_, _name__=type_.__name__, _kwargs_=kwargs, _is_inferred_=True
    )
