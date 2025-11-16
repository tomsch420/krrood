"""
This module defines some custom exception types used by the entity_query_language package.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from ..utils import DataclassException

from typing_extensions import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .symbolic import SymbolicExpression


@dataclass
class QuantificationError(DataclassException, ABC):
    """
    Represents a custom exception specific to quantification errors.

    This exception is used to indicate errors related to the quantification
    of the query results.
    """

    expression: SymbolicExpression
    expected_number: int


@dataclass
class GreaterThanExpectedNumberOfSolutions(QuantificationError):
    """
    Represents an error when the number of solutions exceeds the
    expected threshold.
    """

    def __post_init__(self):
        self.message = f"More than {self.expected_number} solutions found for the expression {self.expression}."
        super().__post_init__()


@dataclass
class LessThanExpectedNumberOfSolutions(QuantificationError):
    """
    Represents an error that occurs when the number of solutions found
    is lower than the expected number.
    """

    found_number: int

    def __post_init__(self):
        self.message = (
            f"Found {self.found_number} solutions which is less than the expected {self.expected_number} "
            f"solutions for the expression {self.expression}."
        )
        super().__post_init__()


@dataclass
class MultipleSolutionFound(GreaterThanExpectedNumberOfSolutions):
    """
    Raised when a query unexpectedly yields more than one solution where a single
    result was expected.
    """

    expected_number: int = 1


@dataclass
class NoSolutionFound(LessThanExpectedNumberOfSolutions):
    """
    Raised when a query does not yield any solution.
    """

    expected_number: int = 1
    found_number: int = 0


@dataclass
class UsageError(DataclassException):
    """
    Raised when there is an incorrect usage of the entity query language API.
    """

    ...


@dataclass
class UnsupportedOperation(UsageError):
    """
    Raised when an operation is not supported by the entity query language API.
    """

    ...


@dataclass
class UnsupportedNegation(UnsupportedOperation):
    """
    Raised when negating quantifiers.
    """

    operation_type: Type[SymbolicExpression]

    def __post_init__(self):
        self.message = (
            f"Symbolic NOT operations on {self.operation_type} types"
            f" operands are not allowed, you can negate the conditions instead,"
            f" as negating them is most likely not what you want"
            f" because it is ambiguous and can be very expensive to compute."
            f"To Negate Conditions do:"
            f" `not_(condition)` instead of `not_(an(entity(..., condition)))`."
        )
        super().__post_init__()
@dataclass
class CardinalitySpecificationError(UsageError):
    """
    Raised when the cardinality constraints specified on the query results are invalid or inconsistent.
    """


@dataclass
class CardinalityConsistencyError(CardinalitySpecificationError):
    """
    Raised when the cardinality constraints specified on the query results are inconsistent.
    """

    ...


@dataclass
class NegativeCardinalityError(CardinalityConsistencyError):
    """
    Raised when the cardinality constraints specified on the query results have a negative value.
    """

    message: str = f"ResultQuantificationConstraint must be a non-negative integer."


@dataclass
class InvalidEntityType(UsageError):
    """
    Raised when an invalid entity type is given to the quantification operation.
    """

    entity_type: Type

    def __post_init__(self):
        self.message = (
            f"The entity type {self.entity_type} is not valid. It must be a subclass of QueryObjectDescriptor class."
            f"e.g. Entity, or SetOf"
        )
        super().__post_init__()
