from __future__ import annotations

"""
Custom exception types used by entity_query_language.
"""
from typing_extensions import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .symbolic import SymbolicExpression


class MultipleSolutionFound(Exception):
    """
    Raised when a query unexpectedly yields more than one solution where a single
    result was expected.

    :param first_val: The first solution encountered.
    :param second_val: The second solution encountered.
    """

    def __init__(self, first_val, second_val):
        super(MultipleSolutionFound, self).__init__(
            f"Multiple solutions found, the first two are {first_val}\n{second_val}"
        )


class NoSolutionFound(Exception):
    """
    Raised when a query does not yield any solution.
    """

    def __init__(self, expression: SymbolicExpression):
        super(NoSolutionFound, self).__init__(
            f"No solution found for expression {expression}"
        )


class UsageError(Exception):
    """
    Raised when there is an incorrect usage of the entity query language API.
    """

    def __init__(self, message: str):
        super(UsageError, self).__init__(message)


class UnsupportedOperation(UsageError):
    """
    Raised when an operation is not supported by the entity query language API.
    """

    ...


class UnsupportedNegation(UnsupportedOperation):
    """
    Raised when negating quantifiers.
    """

    def __init__(self, operation_type: Type[SymbolicExpression]):
        super().__init__(
            f"Symbolic NOT operations on {operation_type} types"
            f" operands are not allowed, you can negate the conditions instead,"
            f" as negating quantifiers is most likely not what you want"
            f" because it is ambiguous and can be very expensive to compute."
        )
