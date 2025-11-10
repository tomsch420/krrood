from __future__ import annotations

from abc import ABC

"""
Custom exception types used by entity_query_language.
"""
from typing_extensions import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .symbolic import SymbolicExpression


class QuantificationError(Exception, ABC):
    """
    Represents a custom exception specific to quantification errors.

    This exception is used to indicate errors related to the quantification
    of the query results.
    """


class GreaterThanExpectedNumberOfSolutions(QuantificationError):
    """
    Represents an error when the number of solutions exceeds the
    expected threshold.
    """

    def __init__(self, expression: SymbolicExpression, expected_number: int):
        super(GreaterThanExpectedNumberOfSolutions, self).__init__(
            f"More than {expected_number} solutions found for the expression {expression}."
        )


class LessThanExpectedNumberOfSolutions(QuantificationError):
    """
    Represents an error that occurs when the number of solutions found
    is lower than the expected number.
    """

    def __init__(
        self, expression: SymbolicExpression, expected_number: int, found_number: int
    ):
        super(LessThanExpectedNumberOfSolutions, self).__init__(
            f"Found {found_number} solutions which is less than the expected {expected_number} solutions for"
            f" the expression {expression}."
        )


class MultipleSolutionFound(GreaterThanExpectedNumberOfSolutions):
    """
    Raised when a query unexpectedly yields more than one solution where a single
    result was expected.
    """

    def __init__(self, expression: SymbolicExpression):
        super(MultipleSolutionFound, self).__init__(expression, 1)


class NoSolutionFound(LessThanExpectedNumberOfSolutions):
    """
    Raised when a query does not yield any solution.
    """

    def __init__(self, expression: SymbolicExpression, expected_number: int = 1):
        super(NoSolutionFound, self).__init__(
            expression,
            expected_number,
            0,
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
            f" as negating them is most likely not what you want"
            f" because it is ambiguous and can be very expensive to compute."
            f"To Negate Conditions do:"
            f" `not_(condition)` instead of `not_(an(entity(..., condition)))`."
        )
