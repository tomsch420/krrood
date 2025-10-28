from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple, Union

from typing_extensions import Optional, List, Type, TYPE_CHECKING, Callable


if TYPE_CHECKING:
    from .symbolic_math import Symbol


class LogicalError(Exception):
    """
    An error that happens due to mistake in the logical operation or usage of the API during runtime.
    """


class UsageError(LogicalError):
    """
    An exception raised when an incorrect usage of the API is encountered.
    """


class SymbolManagerException(Exception):
    """
    Exceptions related to the symbol manager for special types.
    """


@dataclass
class SymbolResolutionError(SymbolManagerException):
    """
    Represents an error that occurs when a symbol in a symbolic expression cannot be resolved.

    This exception is raised when the resolution of a symbol fails due to
    underlying exceptions or unresolved states. It provides details about
    the symbol that caused the error and the original exception responsible
    for the failure.
    """

    symbol: Symbol
    original_exception: Exception

    def __post_init__(self):
        super().__init__(
            f'Symbol "{self.symbol.name}" could not be resolved. '
            f"({self.original_exception.__class__.__name__}: {str(self.original_exception)})"
        )


class SymbolicMathError(UsageError):
    pass


@dataclass
class WrongDimensionsError(SymbolicMathError):
    expected_dimensions: Union[Tuple[int, int], str]
    actual_dimensions: Tuple[int, int]

    def __post_init__(self):
        msg = f"Expected {self.expected_dimensions} dimensions, but got {self.actual_dimensions}."
        super().__init__(msg)


@dataclass
class NotSquareMatrixError(SymbolicMathError):
    actual_dimensions: Tuple[int, int]

    def __post_init__(self):
        msg = f"Expected a square matrix, but got {self.actual_dimensions} dimensions."
        super().__init__(msg)


@dataclass
class HasFreeSymbolsError(SymbolicMathError):
    """
    Raised when an operation can't be performed on an expression with free symbols.
    """

    symbols: Iterable[Symbol]

    def __post_init__(self):
        msg = f"Operation can't be performed on expression with free symbols: {list(self.symbols)}."
        super().__init__(msg)
