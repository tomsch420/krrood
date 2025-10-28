from __future__ import annotations

import builtins
import copy
import functools
import math
import operator
import sys
from abc import abstractmethod, ABC
from copy import copy
from dataclasses import dataclass, field, InitVar
from enum import IntEnum

import casadi
import casadi as ca
import numpy as np
from scipy import sparse as sp
from typing_extensions import (
    Optional,
    List,
    Tuple,
    Dict,
    Sequence,
    Any,
    Self,
    ClassVar,
    Iterable,
    Union,
    TypeVar,
    Callable,
)

from krrood.entity_query_language.entity import entity, an, let, contains
from krrood.entity_query_language.predicate import Symbol, symbolic_function
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.symbolic_math.exceptions import HasFreeSymbolsError, NotSquareMatrixError

EPS: float = sys.float_info.epsilon * 4.0


@dataclass
class CompiledFunction:
    """
    A compiled symbolic function that can be efficiently evaluated with CasADi.

    This class compiles symbolic expressions into optimized CasADi functions that can be
    evaluated efficiently. It supports both sparse and dense matrices and handles
    parameter substitution automatically.
    """

    expression: CasadiScalarWrapper
    """
    The symbolic expression to compile.
    """
    symbol_parameters: Optional[List[List[MathSymbol]]] = None
    """
    The input parameters for the compiled symbolic expression.
    """
    sparse: bool = False
    """
    Whether to return a sparse matrix or a dense numpy matrix
    """

    _compiled_casadi_function: ca.Function = field(init=False)

    _function_buffer: ca.FunctionBuffer = field(init=False)
    _function_evaluator: functools.partial = field(init=False)
    """
    Helpers to avoid new memory allocation during function evaluation
    """

    _out: Union[np.ndarray, sp.csc_matrix] = field(init=False)
    """
    The result of a function evaluation is stored in this variable.
    """

    _is_constant: bool = False
    """
    Used to memorize if the result must be recomputed every time.
    """

    def __post_init__(self):
        if self.symbol_parameters is None:
            self.symbol_parameters = [self.expression.free_symbols()]
        else:
            symbols = set()
            for symbol_parameter in self.symbol_parameters:
                symbols.update(set(symbol_parameter))
            missing_symbols = set(self.expression.free_symbols()).difference(symbols)
            if missing_symbols:
                raise HasFreeSymbolsError(missing_symbols)

        if len(self.symbol_parameters) == 1 and len(self.symbol_parameters[0]) == 0:
            self.symbol_parameters = []

        if len(self.expression) == 0:
            self._setup_empty_result()
            return

        self._setup_compiled_function()
        self._setup_output_buffer()
        if len(self.symbol_parameters) == 0:
            self._setup_constant_result()

    def _setup_empty_result(self) -> None:
        """
        Setup result for empty expressions.
        """
        if self.sparse:
            self._out = sp.csc_matrix(np.empty(self.expression.shape))
        else:
            self._out = np.empty(self.expression.shape)
        self._is_constant = True

    def _setup_compiled_function(self) -> None:
        """
        Setup the CasADi compiled function.
        """
        casadi_parameters = []
        if len(self.symbol_parameters) > 0:
            # create an array for each List[Symbol]
            casadi_parameters = [
                Expression(data=p).casadi_sx for p in self.symbol_parameters
            ]

        if self.sparse:
            self._compile_sparse_function(casadi_parameters)
        else:
            self._compile_dense_function(casadi_parameters)

    def _compile_sparse_function(self, casadi_parameters: List[Expression]) -> None:
        """
        Compile function for sparse matrices.
        """
        self.expression.casadi_sx = ca.sparsify(self.expression.casadi_sx)
        self._compiled_casadi_function = ca.Function(
            "f", casadi_parameters, [self.expression.casadi_sx]
        )

        self._function_buffer, self._function_evaluator = (
            self._compiled_casadi_function.buffer()
        )
        self.csc_indices, self.csc_indptr = (
            self.expression.casadi_sx.sparsity().get_ccs()
        )
        self.zeroes = np.zeros(self.expression.casadi_sx.nnz())

    def _compile_dense_function(self, casadi_parameters: List[MathSymbol]) -> None:
        """
        Compile function for dense matrices.

        :param casadi_parameters: List of CasADi parameters for the function
        """
        self.expression.casadi_sx = ca.densify(self.expression.casadi_sx)
        self._compiled_casadi_function = ca.Function(
            "f", casadi_parameters, [self.expression.casadi_sx]
        )

        self._function_buffer, self._function_evaluator = (
            self._compiled_casadi_function.buffer()
        )

    def _setup_output_buffer(self) -> None:
        """
        Setup the output buffer for the compiled function.
        """
        if self.sparse:
            self._setup_sparse_output_buffer()
        else:
            self._setup_dense_output_buffer()

    def _setup_sparse_output_buffer(self) -> None:
        """
        Setup output buffer for sparse matrices.
        """
        self._out = sp.csc_matrix(
            arg1=(
                self.zeroes,
                self.csc_indptr,
                self.csc_indices,
            ),
            shape=self.expression.shape,
        )
        self._function_buffer.set_res(0, memoryview(self._out.data))

    def _setup_dense_output_buffer(self) -> None:
        """
        Setup output buffer for dense matrices.
        """
        if self.expression.shape[1] <= 1:
            shape = self.expression.shape[0]
        else:
            shape = self.expression.shape
        self._out = np.zeros(shape, order="F")
        self._function_buffer.set_res(0, memoryview(self._out))

    def _setup_constant_result(self) -> None:
        """
        Setup result for constant expressions (no parameters).

        For expressions with no free parameters, we can evaluate once and return
        the constant result for all future calls.
        """
        self._function_evaluator()
        self._is_constant = True

    def __call__(self, *args: np.ndarray) -> Union[np.ndarray, sp.csc_matrix]:
        """
        Efficiently evaluate the compiled function with positional arguments, by directly writing the memory of the
        numpy arrays to the memoryview of the compiled function.
        Similarly, the result will be written to the output buffer and doesn't allocate new memory on each eval.

        (Yes, this makes a significant speed different.)

        :param args: A numpy array for each List[Symbol] in self.symbol_parameters.
            .. warning:: Make sure the numpy array is of type float! (check is too expensive)
        :return: The evaluated result as numpy array or sparse matrix
        """
        if self._is_constant:
            return self._out
        for arg_idx, arg in enumerate(args):
            self._function_buffer.set_arg(arg_idx, memoryview(arg))
        self._function_evaluator()
        return self._out

    def call_with_kwargs(self, **kwargs: float) -> np.ndarray:
        """
        Call the object instance with the provided keyword arguments. This method retrieves
        the required arguments from the keyword arguments based on the defined
        `symbol_parameters`, compiles them into an array, and then calls the instance
        with the constructed array.

        :param kwargs: A dictionary of keyword arguments containing the parameters
            that match the symbols defined in `symbol_parameters`.
        :return: A NumPy array resulting from invoking the callable object instance
            with the filtered arguments.
        """
        args = []
        for params in self.symbol_parameters:
            for param in params:
                args.append(kwargs[str(param)])
        filtered_args = np.array(args, dtype=float)
        return self(filtered_args)


@symbolic_function
def to_string(x):
    return str(x)


@dataclass
class CompiledFunctionWithViews:
    """
    A wrapper for CompiledFunction which automatically splits the result array into multiple views, with minimal
    overhead.
    Useful, when many arrays must be evaluated at the same time, especially when they depend on the same symbols.
    """

    expressions: List[Expression]
    """
    The list of expressions to be compiled, the first len(expressions) many results of __call__ correspond to those
    """

    symbol_parameters: List[List[MathSymbol]]
    """
    The input parameters for the compiled symbolic expression.
    """

    additional_views: Optional[List[slice]] = None
    """
    If additional views are required that don't correspond to the expressions directly.
    """

    compiled_function: CompiledFunction = field(init=False)
    """
    Reference to the compiled function.
    """

    split_out_view: List[np.ndarray] = field(init=False)
    """
    Views to the out buffer of the compiled function.
    """

    def __post_init__(self):
        combined_expression = Expression.vstack(self.expressions)
        self.compiled_function = combined_expression.compile(
            parameters=self.symbol_parameters, sparse=False
        )
        slices = []
        start = 0
        for expression in self.expressions[:-1]:
            end = start + expression.shape[0]
            slices.append(end)
            start = end
        self.split_out_view = np.split(self.compiled_function._out, slices)
        if self.additional_views is not None:
            for expression_slice in self.additional_views:
                self.split_out_view.append(
                    self.compiled_function._out[expression_slice]
                )

    def __call__(self, *args: np.ndarray) -> List[np.ndarray]:
        """
        :param args: A numpy array for each List[Symbol] in self.symbol_parameters.
        :return: A np array for each expression, followed by arrays corresponding to the additional views.
            They are all views on self.compiled_function.out.
        """
        self.compiled_function(*args)
        return self.split_out_view


def _operation_type_error(arg1: object, operation: str, arg2: object) -> TypeError:
    return TypeError(
        f"unsupported operand type(s) for {operation}: '{arg1.__class__.__name__}' "
        f"and '{arg2.__class__.__name__}'"
    )


@dataclass(eq=False)
class CasadiScalarWrapper(ABC):
    """
    A wrapper around CasADi's ca.SX, with better usability
    """

    casadi_sx: ca.SX = field(kw_only=True, default_factory=ca.SX)
    """
    Reference to the casadi data structure of type casadi.SX
    """

    @classmethod
    @abstractmethod
    def from_casadi_sx(cls, expression: Expression) -> Self:
        """
        Factory to create this class from an existing expression.

        :param expression: A generic expression to initialize this from.
        :return: An instance of this class is initialized from the given expression.
        """

    def __str__(self):
        return str(self.casadi_sx)

    def pretty_str(self) -> List[List[str]]:
        """
        Turns a symbolic type into a more or less readable string.
        """
        result_list = np.zeros(self.shape).tolist()
        for x_index in range(self.shape[0]):
            for y_index in range(self.shape[1]):
                s = str(self[x_index, y_index])
                parts = s.split(", ")
                result = parts[-1]
                for x in reversed(parts[:-1]):
                    equal_position = len(x.split("=")[0])
                    index = x[:equal_position]
                    sub = x[equal_position + 1 :]
                    result = result.replace(index, sub)
                result_list[x_index][y_index] = result
        return result_list

    def __repr__(self):
        return repr(self.casadi_sx)

    def __hash__(self) -> int:
        return self.casadi_sx.__hash__()

    def __getitem__(
        self,
        item: Union[
            np.ndarray, Union[int, slice], Tuple[Union[int, slice], Union[int, slice]]
        ],
    ) -> Expression:
        if isinstance(item, np.ndarray) and item.dtype == bool:
            item = (np.where(item)[0], slice(None, None))
        return Expression(self.casadi_sx[item])

    def __setitem__(
        self,
        key: Union[Union[int, slice], Tuple[Union[int, slice], Union[int, slice]]],
        value: ScalarData,
    ):
        self.casadi_sx[key] = value.casadi_sx if hasattr(value, "casadi_sx") else value

    @property
    def shape(self) -> Tuple[int, int]:
        return self.casadi_sx.shape

    def __len__(self) -> int:
        return self.shape[0]

    def free_symbols(self) -> List[MathSymbol]:
        all_symbols = [str(s) for s in ca.symvar(self.casadi_sx)]
        with symbolic_mode():
            math_symbols = let(MathSymbol)
            q = an(
                entity(
                    math_symbols,
                    contains(all_symbols, to_string(math_symbols)),
                )
            )

        return list(q.evaluate())

    def is_constant(self) -> bool:
        return len(self.free_symbols()) == 0

    def to_np(self) -> np.ndarray:
        """
        Transforms the data into a numpy array.
        Only works if the expression has no free symbols.
        """
        if not self.is_constant():
            raise HasFreeSymbolsError(self.free_symbols())
        if self.shape[0] == self.shape[1] == 0:
            return np.eye(0)
        elif self.casadi_sx.shape[0] == 1 or self.casadi_sx.shape[1] == 1:
            return np.array(ca.evalf(self.casadi_sx)).ravel()
        else:
            return np.array(ca.evalf(self.casadi_sx))

    def compile(
        self, parameters: Optional[List[List[MathSymbol]]] = None, sparse: bool = False
    ) -> CompiledFunction:
        """
        Compiles the function into a representation that can be executed efficiently. This method
        allows for optional parameterization and the ability to specify whether the compilation
        should consider a sparse representation.

        :param parameters: A list of parameter sets, where each set contains symbols that define
            the configuration for the compiled function. If set to None, no parameters are applied.
        :param sparse: A boolean that determines whether the compiled function should use a
            sparse representation. Defaults to False.
        :return: The compiled function as an instance of CompiledFunction.
        """
        return CompiledFunction(self, parameters, sparse)

    def substitute(
        self,
        old_symbols: List[MathSymbol],
        new_symbols: List[Union[MathSymbol, Expression]],
    ) -> Self:
        """
        Replace symbols in an expression with new symbols or expressions.

        This function substitutes symbols in the given expression with the provided
        new symbols or expressions. It ensures that the original expression remains
        unaltered and creates a new instance with the substitutions applied.

        :param old_symbols: A list of symbols in the expression which need to be replaced.
        :param new_symbols: A list of new symbols or expressions which will replace the old symbols.
            The length of this list must correspond to the `old_symbols` list.
        :return: A new expression with the specified symbols replaced.
        """
        old_symbols = Expression(data=[to_sx(s) for s in old_symbols]).casadi_sx
        new_symbols = Expression(data=[to_sx(s) for s in new_symbols]).casadi_sx
        result = copy(self)
        result.casadi_sx = ca.substitute(self.casadi_sx, old_symbols, new_symbols)
        return result

    def norm(self) -> Expression:
        return Expression(ca.norm_2(self.casadi_sx))

    def equivalent(self, other: ScalarData) -> bool:
        """
        Determines whether two scalar expressions are mathematically equivalent by simplifying
        and comparing them.

        :param other: Second scalar expression to compare
        :return: True if the two expressions are equivalent, otherwise False
        """
        other_expression = to_sx(other)
        return ca.is_equal(
            ca.simplify(self.casadi_sx), ca.simplify(other_expression), 5
        )


class BasicOperatorMixin:
    """
    Base class providing arithmetic operations for symbolic types.
    """

    casadi_sx: ca.SX
    """
    Reference to the casadi data structure of type casadi.SX
    """

    def _binary_operation(
        self, other: ScalarData, operation: Callable, reverse: bool = False
    ) -> Expression:
        """
        Performs a binary operation between the current instance and another operand.

        Symbol only allows ScalarData on the righthand sight and implements the reverse version only for NumericalScalaer

        :param other: The operand to be used in the binary operation. Either `ScalarData`
            or `NumericalScalar` types are expected, depending on the context.
        :param operation_name: The name of the binary operation (e.g., "add", "sub", "mul").
        :param reverse: A boolean indicating whether the operation is a reverse operation.
            Defaults to `False`.
        :return: An `Expression` instance resulting from the binary operation, or
            `NotImplemented` if the operand type does not match the expected type.
        """
        if reverse:
            # For reverse operations, check if other is NumericalScalar
            if not isinstance(other, NumericalScalar):
                return NotImplemented
            return Expression(operation(other, self.casadi_sx))
        else:
            # For regular operations, check if other is ScalarData
            if isinstance(other, SymbolicScalar):
                other = other.casadi_sx
            elif not isinstance(other, NumericalScalar):
                return NotImplemented
            return Expression(operation(self.casadi_sx, other))

    # %% arthimetic operators
    def __neg__(self) -> Expression:
        return Expression(self.casadi_sx.__neg__())

    def __add__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.add)

    def __radd__(self, other: NumericalScalar) -> Expression:
        return self._binary_operation(other, operator.add, reverse=True)

    def __sub__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.sub)

    def __rsub__(self, other: NumericalScalar) -> Expression:
        return self._binary_operation(other, operator.sub, reverse=True)

    def __mul__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.mul)

    def __rmul__(self, other: NumericalScalar) -> Expression:
        return self._binary_operation(other, operator.mul, reverse=True)

    def __truediv__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.truediv)

    def __rtruediv__(self, other: NumericalScalar) -> Expression:
        return self._binary_operation(other, operator.truediv, reverse=True)

    def __pow__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.pow)

    def __rpow__(self, other: NumericalScalar) -> Expression:
        return self._binary_operation(other, operator.pow, reverse=True)

    def __floordiv__(self, other: ScalarData) -> Expression:
        return floor(self / other)

    def __rfloordiv__(self, other: ScalarData) -> Expression:
        return floor(other / self)

    def __mod__(self, other: ScalarData) -> Expression:
        return fmod(self.casadi_sx, other)

    def __rmod__(self, other: ScalarData) -> Expression:
        return fmod(other, self.casadi_sx)

    def __divmod__(self, other: ScalarData) -> Tuple[Expression, Expression]:
        return self // other, self % other

    def __rdivmod__(self, other: ScalarData) -> Tuple[Expression, Expression]:
        return other // self, other % self

    # %% logical operators

    def __invert__(self) -> Expression:
        return logic_not(self.casadi_sx)

    def __eq__(self, other: ScalarData) -> Expression:
        if isinstance(other, CasadiScalarWrapper):
            other = other.casadi_sx
        return Expression(self.casadi_sx.__eq__(other))

    def __ne__(self, other):
        if isinstance(other, CasadiScalarWrapper):
            other = other.casadi_sx
        return Expression(self.casadi_sx.__ne__(other))

    def __or__(self, other: ScalarData) -> Expression:
        return logic_or(self.casadi_sx, other)

    def __and__(self, other: ScalarData) -> Expression:
        return logic_and(self.casadi_sx, other)

    def __lt__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.lt)

    def __le__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.le)

    def __gt__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.gt)

    def __ge__(self, other: ScalarData) -> Expression:
        return self._binary_operation(other, operator.ge)

    def safe_division(
        self,
        other: ScalarData,
        if_nan: Optional[ScalarData] = None,
    ) -> Expression:
        """
        A version of division where no sub-expression is ever NaN. The expression would evaluate to 'if_nan', but
        you should probably never work with the 'if_nan' result. However, if one sub-expressions is NaN, the whole expression
        evaluates to NaN, even if it is only in a branch of an if-else, that is not returned.
        This method is a workaround for such cases.
        """
        other = Expression(data=other)
        if if_nan is None:
            if_nan = 0
        if_nan = Expression(data=if_nan)
        save_denominator = if_eq_zero(
            condition=other, if_result=Expression(data=1), else_result=other
        )
        return if_eq_zero(other, if_result=if_nan, else_result=self / save_denominator)


class VectorOperationsMixin:
    casadi_sx: ca.SX
    """
    Reference to the casadi data structure of type casadi.SX
    """

    def euclidean_distance(self, other: Self) -> Expression:
        difference = self - other
        distance = difference.norm()
        return distance


class MatrixOperationsMixin:
    casadi_sx: ca.SX
    """
    Reference to the casadi data structure of type casadi.SX
    """
    shape: Tuple[int, int]

    def sum(self) -> Expression:
        """
        the equivalent to np.sum(matrix)
        """
        return Expression(ca.sum1(ca.sum2(self.casadi_sx)))

    def sum_row(self) -> Expression:
        """
        the equivalent to np.sum(matrix, axis=0)
        """
        return Expression(ca.sum1(self.casadi_sx))

    def sum_column(self) -> Expression:
        """
        the equivalent to np.sum(matrix, axis=1)
        """
        return Expression(ca.sum2(self.casadi_sx))

    def trace(self) -> Expression:
        if not self.is_square():
            raise NotSquareMatrixError(actual_dimensions=self.casadi_sx.shape)
        s = 0
        for i in range(self.casadi_sx.shape[0]):
            s += self.casadi_sx[i, i]
        return Expression(s)

    def det(self) -> Expression:
        """
        Calculate the determinant of the given expression.

        This function computes the determinant of the provided mathematical expression.
        The input can be an instance of either `Expression`, `RotationMatrix`, or
        `TransformationMatrix`. The result is returned as an `Expression`.

        :return: An `Expression` representing the determinant of the input.
        """
        if not self.is_square():
            raise NotSquareMatrixError(actual_dimensions=self.casadi_sx.shape)
        return Expression(ca.det(self.casadi_sx))

    def is_square(self):
        return self.casadi_sx.shape[0] == self.casadi_sx.shape[1]

    def entrywise_product(self, other: Expression) -> Expression:
        """
        Computes the entrywise (element-wise) product of two matrices, assuming they have the same dimensions. The
        operation multiplies each corresponding element of the input matrices and stores the result in a new matrix
        of the same shape.

        :param other: The second matrix, represented as an object of type `Expression`, whose shape
                        must match the shape of `matrix1`.
        :return: A new matrix of type `Expression` containing the entrywise product of `matrix1` and `matrix2`.
        """
        assert self.shape == other.shape
        result = Expression.zeros(*self.shape)
        for i in range(self.shape[0]):
            for j in range(self.shape[1]):
                result[i, j] = self[i, j] * other[i, j]
        return result


@dataclass(eq=False)
class MathSymbol(CasadiScalarWrapper, BasicOperatorMixin, Symbol):
    """
    A symbolic expression, which should be only a single symbols.
    No matrix and no numbers.
    """

    name: str = field(kw_only=True)

    casadi_sx: ca.SX = field(kw_only=True, init=False, default=None)

    _registry: ClassVar[Dict[str, ca.SX]] = {}
    """
    To avoid two symbols with the same name, references to existing symbols are stored on a class level.
    """

    def __post_init__(self):
        """
        Multiton design pattern prevents two symbol instances with the same name.
        """
        cls = self.__class__
        if self.name in cls._registry:
            self.casadi_sx = cls._registry[self.name]
        else:
            self.casadi_sx = ca.SX.sym(self.name)
            cls._registry[self.name] = self.casadi_sx

    @classmethod
    def from_casadi_sx(cls, expression: casadi.SX) -> Self:
        raise NotImplementedError("You cannot create a symbol from an expression")

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Symbol({self})"

    def __hash__(self):
        return hash(self.name)


@dataclass(eq=False)
class Expression(
    CasadiScalarWrapper,
    BasicOperatorMixin,
    VectorOperationsMixin,
    MatrixOperationsMixin,
):
    """
    Represents symbolic expressions with rich mathematical capabilities, including matrix
    operations, derivatives, and manipulation of symbolic representations.

    This class is designed to encapsulate symbolic mathematical expressions and provide a wide
    range of features for computations, including matrix constructions (zeros, ones, identity),
    derivative computations (Jacobian, total derivatives, Hessian), reshaping, and scaling.
    It is essential to symbolic computation workflows in applications that require gradient
    analysis, second-order derivatives, or other advanced mathematical operations. The class
    leverages symbolic computation libraries for handling low-level symbolic details efficiently.
    """

    casadi_sx: ca.SX = field(kw_only=True, default_factory=lambda: ca.SX())

    data: InitVar[
        Optional[
            Union[
                SymbolicData,
                NumericalScalar,
                NumericalArray,
                Numerical2dMatrix,
                Iterable[MathSymbol],
                Iterable[Expression],
            ]
        ]
    ] = None

    def __post_init__(
        self,
        data: Optional[
            Union[
                ca.SX,
                SymbolicData,
                NumericalScalar,
                NumericalArray,
                Numerical2dMatrix,
                Iterable[MathSymbol],
            ]
        ],
    ):
        if data is None:
            return
        if isinstance(data, ca.SX):
            self.casadi_sx = data
        elif isinstance(data, CasadiScalarWrapper):
            self.casadi_sx = data.casadi_sx
        elif isinstance(data, Iterable):
            self._from_iterable(data)
        else:
            self.casadi_sx = ca.SX(data)

    @classmethod
    def from_casadi_sx(cls, expression: ca.SX) -> Self:
        return cls(expression)

    def _from_iterable(
        self, data: Union[NumericalArray, Numerical2dMatrix, Iterable[MathSymbol]]
    ):
        x = len(data)
        if x == 0:
            self.casadi_sx = ca.SX()
            return
        if (
            isinstance(data[0], list)
            or isinstance(data[0], tuple)
            or isinstance(data[0], np.ndarray)
        ):
            y = len(data[0])
        else:
            y = 1
        casadi_sx = ca.SX(x, y)
        for i in range(casadi_sx.shape[0]):
            if y > 1:
                for j in range(casadi_sx.shape[1]):
                    casadi_sx[i, j] = to_sx(data[i][j])
            else:
                casadi_sx[i] = to_sx(data[i])
        self.casadi_sx = casadi_sx

    @classmethod
    def zeros(cls, rows: int, columns: int) -> Expression:
        return cls(casadi_sx=ca.SX.zeros(rows, columns))

    @classmethod
    def ones(cls, x: int, y: int) -> Expression:
        return cls(casadi_sx=ca.SX.ones(x, y))

    @classmethod
    def tri(cls, dimension: int) -> Expression:
        return cls(data=np.tri(dimension))

    @classmethod
    def eye(cls, size: int) -> Expression:
        return cls(casadi_sx=ca.SX.eye(size))

    @classmethod
    def diag(cls, args: Union[List[ScalarData], Expression]) -> Expression:
        return cls(casadi_sx=ca.diag(to_sx(args)))

    @classmethod
    def vstack(
        cls,
        list_of_matrices: List[SymbolicArray],
    ) -> Self:
        if len(list_of_matrices) == 0:
            return cls(data=[])
        return cls(casadi_sx=ca.vertcat(*[to_sx(x) for x in list_of_matrices]))

    @classmethod
    def hstack(
        cls,
        list_of_matrices: List[SymbolicArray],
    ) -> Self:
        """
        Similar to np.hstack
        :param list_of_matrices:
        :return:
        """
        if len(list_of_matrices) == 0:
            return cls(data=[])
        return cls(casadi_sx=ca.horzcat(*[to_sx(x) for x in list_of_matrices]))

    @classmethod
    def diag_stack(cls, list_of_matrices: List[SymbolicArray]) -> Expression:
        """
        Similar to np.diag_stack
        :param list_of_matrices:
        :return:
        """
        num_rows = int(math.fsum(e.shape[0] for e in list_of_matrices))
        num_columns = int(math.fsum(e.shape[1] for e in list_of_matrices))
        combined_matrix = Expression.zeros(num_rows, num_columns)
        row_counter = 0
        column_counter = 0
        for matrix in list_of_matrices:
            combined_matrix[
                row_counter : row_counter + matrix.shape[0],
                column_counter : column_counter + matrix.shape[1],
            ] = matrix
            row_counter += matrix.shape[0]
            column_counter += matrix.shape[1]
        return combined_matrix

    def remove(self, rows: List[int], columns: List[int]):
        self.casadi_sx.remove(rows, columns)

    def split(self) -> List[Expression]:
        assert self.shape[0] == 1 and self.shape[1] == 1
        parts = [
            Expression(self.casadi_sx.dep(i)) for i in range(self.casadi_sx.n_dep())
        ]
        return parts

    def __copy__(self) -> Expression:
        return Expression(copy(self.casadi_sx))

    def dot(self, other: Expression) -> Expression:
        if isinstance(other, Expression):
            if self.shape[1] == 1 and other.shape[1] == 1:
                return Expression(ca.mtimes(self.T.casadi_sx, other.casadi_sx))
            return Expression(ca.mtimes(self.casadi_sx, other.casadi_sx))
        raise _operation_type_error(self, "dot", other)

    @property
    def T(self) -> Expression:
        return Expression(self.casadi_sx.T)

    def reshape(self, new_shape: Tuple[int, int]) -> Expression:
        return Expression(self.casadi_sx.reshape(new_shape))

    def jacobian(self, symbols: Iterable[MathSymbol]) -> Expression:
        """
        Compute the Jacobian matrix of a vector of expressions with respect to a vector of symbols.

        This function calculates the Jacobian matrix, which is a matrix of all first-order
        partial derivatives of a vector of functions with respect to a vector of variables.

        :param symbols: The symbols with respect to which the partial derivatives are taken.
        :return: The Jacobian matrix as an Expression.
        """
        return Expression(
            ca.jacobian(self.casadi_sx, Expression(data=symbols).casadi_sx)
        )

    def jacobian_dot(
        self, symbols: Iterable[MathSymbol], symbols_dot: Iterable[MathSymbol]
    ) -> Expression:
        """
        Compute the total derivative of the Jacobian matrix.

        This function calculates the time derivative of a Jacobian matrix given
        a set of expressions and symbols, along with their corresponding
        derivatives. For each element in the Jacobian matrix, this method
        computes the total derivative based on the provided symbols and
        their time derivatives.

        :param symbols: Iterable containing the symbols with respect to which
            the Jacobian is calculated.
        :param symbols_dot: Iterable containing the time derivatives of the
            corresponding symbols in `symbols`.
        :return: The time derivative of the Jacobian matrix.
        """
        Jd = self.jacobian(symbols)
        for i in range(Jd.shape[0]):
            for j in range(Jd.shape[1]):
                Jd[i, j] = Jd[i, j].total_derivative(symbols, symbols_dot)
        return Jd

    def jacobian_ddot(
        self,
        symbols: Iterable[MathSymbol],
        symbols_dot: Iterable[MathSymbol],
        symbols_ddot: Iterable[MathSymbol],
    ) -> Expression:
        """
        Compute the second-order total derivative of the Jacobian matrix.

        This function computes the Jacobian matrix of the given expressions with
        respect to specified symbols and further calculates the second-order
        total derivative for each element in the Jacobian matrix with respect to
        the provided symbols, their first-order derivatives, and their second-order
        derivatives.

        :param symbols: An iterable of symbolic variables representing the
            primary variables with respect to which the Jacobian and derivatives
            are calculated.
        :param symbols_dot: An iterable of symbolic variables representing the
            first-order derivatives of the primary variables.
        :param symbols_ddot: An iterable of symbolic variables representing the
            second-order derivatives of the primary variables.
        :return: A symbolic matrix representing the second-order total derivative
            of the Jacobian matrix of the provided expressions.
        """
        Jdd = self.jacobian(symbols)
        for i in range(Jdd.shape[0]):
            for j in range(Jdd.shape[1]):
                Jdd[i, j] = Jdd[i, j].second_order_total_derivative(
                    symbols, symbols_dot, symbols_ddot
                )
        return Jdd

    def total_derivative(
        self,
        symbols: Iterable[MathSymbol],
        symbols_dot: Iterable[MathSymbol],
    ) -> Expression:
        """
        Compute the total derivative of an expression with respect to given symbols and their derivatives
        (dot symbols).

        The total derivative accounts for a dependent relationship where the specified symbols represent
        the variables of interest, and the dot symbols represent the time derivatives of those variables.

        :param symbols: Iterable of symbols with respect to which the derivative is computed.
        :param symbols_dot: Iterable of dot symbols representing the derivatives of the symbols.
        :return: The expression resulting from the total derivative computation.
        """
        symbols = Expression(data=symbols)
        symbols_dot = Expression(data=symbols_dot)
        return Expression(
            ca.jtimes(self.casadi_sx, symbols.casadi_sx, symbols_dot.casadi_sx)
        )

    def second_order_total_derivative(
        self,
        symbols: Iterable[MathSymbol],
        symbols_dot: Iterable[MathSymbol],
        symbols_ddot: Iterable[MathSymbol],
    ) -> Expression:
        """
        Computes the second-order total derivative of an expression with respect to a set of symbols.

        This function takes an expression and computes its second-order total derivative
        using provided symbols, their first-order derivatives, and their second-order
        derivatives. The computation internally constructs a Hessian matrix of the
        expression and multiplies it by a vector that combines the provided derivative
        data.

        :param symbols: Iterable containing the symbols with respect to which the derivative is calculated.
        :param symbols_dot: Iterable containing the first-order derivatives of the symbols.
        :param symbols_ddot: Iterable containing the second-order derivatives of the symbols.
        :return: The computed second-order total derivative, returned as an `Expression`.
        """
        symbols = Expression(data=symbols)
        symbols_dot = Expression(data=symbols_dot)
        symbols_ddot = Expression(data=symbols_ddot)
        v = []
        for i in range(len(symbols)):
            for j in range(len(symbols)):
                if i == j:
                    v.append(symbols_ddot[i].casadi_sx)
                else:
                    v.append(symbols_dot[i].casadi_sx * symbols_dot[j].casadi_sx)
        v = Expression(data=v)
        H = Expression(ca.hessian(self.casadi_sx, symbols.casadi_sx)[0])
        H = H.reshape((1, len(H) ** 2))
        return H.dot(v)

    def hessian(self, symbols: Iterable[MathSymbol]) -> Expression:
        """
        Calculate the Hessian matrix of a given expression with respect to specified symbols.

        The function computes the second-order partial derivatives (Hessian matrix) for a
        provided mathematical expression using the specified symbols. It utilizes a symbolic
        library for the internal operations to generate the Hessian.

        :param symbols: An iterable containing the symbols with respect to which the derivatives
            are calculated.
        :return: The resulting Hessian matrix as an expression.
        """
        expressions = self.casadi_sx
        return Expression(
            ca.hessian(expressions, Expression(data=symbols).casadi_sx)[0]
        )

    def inverse(self) -> Expression:
        """
        Computes the matrix inverse. Only works if the expression is square.
        """
        assert self.shape[0] == self.shape[1]
        return Expression(ca.inv(self.casadi_sx))

    def scale(self, a: ScalarData) -> Expression:
        return self.safe_division(self.norm()) * a

    def kron(self, other: Expression) -> Expression:
        """
        Compute the Kronecker product of two given matrices.

        The Kronecker product is a block matrix construction, derived from the
        direct product of two matrices. It combines the entries of the first
        matrix (`m1`) with each entry of the second matrix (`m2`) by a rule
        of scalar multiplication. This operation extends to any two matrices
        of compatible shapes.

        :param other: The second matrix to be used in calculating the Kronecker product.
                   Supports symbolic or numerical matrix types.
        :return: An Expression representing the resulting Kronecker product as a
                 symbolic or numerical matrix of appropriate size.
        """
        m1 = to_sx(self)
        m2 = to_sx(other)
        return Expression(ca.kron(m1, m2))


def create_symbols(names: Union[List[str], int]) -> List[MathSymbol]:
    """
    Generates a list of symbolic objects based on the input names or an integer value.

    This function takes either a list of names or an integer. If an integer is
    provided, it generates symbolic objects with default names in the format
    `s_<index>` for numbers up to the given integer. If a list of names is
    provided, it generates symbolic objects for each name in the list.

    :param names: A list of strings representing names of symbols or an integer
        specifying the number of symbols to generate.
    :return: A list of symbolic objects created based on the input.
    """
    if isinstance(names, int):
        names = [f"s_{i}" for i in range(names)]
    return [MathSymbol(name=x) for x in names]


def diag(args: Union[List[ScalarData], Expression]) -> Expression:
    return Expression.diag(args)


def vstack(args: Union[List[Expression], Expression]) -> Expression:
    return Expression.vstack(args)


def hstack(args: Union[List[Expression], Expression]) -> Expression:
    return Expression.hstack(args)


def diag_stack(args: Union[List[Expression], Expression]) -> Expression:
    return Expression.diag_stack(args)


def abs(x: CasadiScalarWrapper) -> Expression:
    x_sx = to_sx(x)
    result = ca.fabs(x_sx)
    return Expression(result)


def max(x: ScalarData, y: ScalarData) -> Expression:
    x = to_sx(x)
    y = to_sx(y)
    return Expression(ca.fmax(x, y))


def min(x: ScalarData, y: ScalarData) -> Expression:
    x = to_sx(x)
    y = to_sx(y)
    return Expression(ca.fmin(x, y))


def limit(
    x: ScalarData, lower_limit: ScalarData, upper_limit: ScalarData
) -> Expression:
    return Expression(data=max(lower_limit, min(upper_limit, x)))


def to_sx(thing: Union[ca.SX, CasadiScalarWrapper]) -> ca.SX:
    if isinstance(thing, CasadiScalarWrapper):
        return thing.casadi_sx
    if isinstance(thing, ca.SX):
        return thing
    return ca.SX(thing)


def dot(e1: Expression, e2: Expression) -> Expression:
    return e1.dot(e2)


def fmod(a: ScalarData, b: ScalarData) -> Expression:
    a = to_sx(a)
    b = to_sx(b)
    return Expression(ca.fmod(a, b))


def normalize_angle_positive(angle: ScalarData) -> Expression:
    """
    Normalizes the angle to be 0 to 2*pi
    It takes and returns radians.
    """
    return fmod(fmod(angle, 2.0 * ca.pi) + 2.0 * ca.pi, 2.0 * ca.pi)


def normalize_angle(angle: ScalarData) -> Expression:
    """
    Normalizes the angle to be -pi to +pi
    It takes and returns radians.
    """
    a = normalize_angle_positive(angle)
    return if_greater(a, ca.pi, a - 2.0 * ca.pi, a)


def shortest_angular_distance(
    from_angle: ScalarData, to_angle: ScalarData
) -> Expression:
    """
    Given 2 angles, this returns the shortest angular
    difference.  The inputs and outputs are of course radians.

    The result would always be -pi <= result <= pi. Adding the result
    to "from" will always get you an equivalent angle to "to".
    """
    return normalize_angle(to_angle - from_angle)


def safe_acos(angle: ScalarData) -> Expression:
    """
    Limits the angle between -1 and 1 to avoid acos becoming NaN.
    """
    angle = limit(angle, -1, 1)
    return acos(angle)


def floor(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.floor(x))


def ceil(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.ceil(x))


def sign(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.sign(x))


def cos(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.cos(x))


def sin(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.sin(x))


def exp(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.exp(x))


def log(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.log(x))


def tan(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.tan(x))


def cosh(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.cosh(x))


def sinh(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.sinh(x))


def sqrt(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.sqrt(x))


def acos(x: ScalarData) -> Expression:
    x = to_sx(x)
    return Expression(ca.acos(x))


def atan2(x: ScalarData, y: ScalarData) -> Expression:
    x = to_sx(x)
    y = to_sx(y)
    return Expression(ca.atan2(x, y))


def solve_for(
    expression: Expression,
    target_value: float,
    start_value: float = 0.0001,
    max_tries: int = 10000,
    eps: float = 1e-10,
    max_step: float = 1,
) -> float:
    """
    Solves for a value `x` such that the given mathematical expression, when evaluated at `x`,
    is approximately equal to the target value. The solver iteratively adjusts the value of `x`
    using a numerical approach based on the derivative of the expression.

    :param expression: The mathematical expression to solve. It is assumed to be differentiable.
    :param target_value: The value that the expression is expected to approximate.
    :param start_value: The initial guess for the iterative solver. Defaults to 0.0001.
    :param max_tries: The maximum number of iterations the solver will perform. Defaults to 10000.
    :param eps: The maximum tolerated absolute error for the solution. If the difference
        between the computed value and the target value is less than `eps`, the solution is considered valid. Defaults to 1e-10.
    :param max_step: The maximum adjustment to the value of `x` at each iteration step. Defaults to 1.
    :return: The estimated value of `x` that solves the equation for the given expression and target value.
    :raises ValueError: If no solution is found within the allowed number of steps or if convergence criteria are not met.
    """
    f_dx = expression.jacobian(expression.free_symbols()).compile()
    f = expression.compile()
    x = start_value
    for tries in range(max_tries):
        err = f(np.array([x]))[0] - target_value
        if builtins.abs(err) < eps:
            return x
        slope = f_dx(np.array([x]))[0]
        if slope == 0:
            if start_value > 0:
                slope = -0.001
            else:
                slope = 0.001
        x -= builtins.max(builtins.min(err / slope, max_step), -max_step)
    raise ValueError("no solution found")


def gauss(n: ScalarData) -> Expression:
    """
    Calculate the sum of the first `n` natural numbers using the Gauss formula.

    This function computes the sum of an arithmetic series where the first term
    is 1, the last term is `n`, and the total count of the terms is `n`. The
    result is derived from the formula `(n * (n + 1)) / 2`, which simplifies
    to `(n ** 2 + n) / 2`.

    :param n: The upper limit of the sum, representing the last natural number
              of the series to include.
    :return: The sum of the first `n` natural numbers.
    """
    return (n**2 + n) / 2


# %% binary logic
BinaryTrue = Expression(data=True)
BinaryFalse = Expression(data=False)


def is_false_symbol(expression: Expression) -> bool:
    try:
        return bool((expression == BinaryFalse).to_np())
    except Exception as e:
        return False


def logic_and(*args: ScalarData) -> ScalarData:
    assert len(args) >= 2, "and must be called with at least 2 arguments"
    # if there is any False, return False
    if [x for x in args if is_false_symbol(x)]:
        return BinaryFalse
    # filter all True
    args = [x for x in args if not is_true_symbol(x)]
    if len(args) == 0:
        return BinaryTrue
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        cas_a = to_sx(args[0])
        cas_b = to_sx(args[1])
        return Expression(ca.logic_and(cas_a, cas_b))
    else:
        return Expression(
            ca.logic_and(args[0].casadi_sx, logic_and(*args[1:]).casadi_sx)
        )


def logic_not(expression: ScalarData) -> Expression:
    cas_expr = to_sx(expression)
    return Expression(ca.logic_not(cas_expr))


def logic_any(args: Expression) -> ScalarData:
    return Expression(ca.logic_any(args.casadi_sx))


def logic_all(args: Expression) -> ScalarData:
    return Expression(ca.logic_all(args.casadi_sx))


def logic_or(*args: ScalarData, simplify: bool = True) -> ScalarData:
    assert len(args) >= 2, "and must be called with at least 2 arguments"
    # if there is any True, return True
    if simplify and [x for x in args if is_true_symbol(x)]:
        return BinaryTrue
    # filter all False
    if simplify:
        args = [x for x in args if not is_false_symbol(x)]
    if len(args) == 0:
        return BinaryFalse
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        return Expression(ca.logic_or(to_sx(args[0]), to_sx(args[1])))
    else:
        return Expression(
            ca.logic_or(to_sx(args[0]), to_sx(logic_or(*args[1:], False)))
        )


def is_true_symbol(expression: Expression) -> bool:
    try:
        equality_expr = expression == BinaryTrue
        return bool(equality_expr.to_np())
    except Exception as e:
        return False


# %% trinary logic
TrinaryFalse: Expression = Expression(data=0.0)
TrinaryUnknown: Expression = Expression(data=0.5)
TrinaryTrue: Expression = Expression(data=1.0)


def trinary_logic_not(expression: ScalarData) -> Expression:
    return Expression(data=1 - expression)


def trinary_logic_and(*args: ScalarData) -> ScalarData:
    assert len(args) >= 2, "and must be called with at least 2 arguments"
    # if there is any False, return False
    if [x for x in args if is_false_symbol(x)]:
        return TrinaryFalse
    # filter all True
    args = [x for x in args if not is_true_symbol(x)]
    if len(args) == 0:
        return TrinaryTrue
    if len(args) == 1:
        return args[0]
    if len(args) == 2:
        cas_a = to_sx(args[0])
        cas_b = to_sx(args[1])
        return min(cas_a, cas_b)
    else:
        return trinary_logic_and(args[0], trinary_logic_and(*args[1:]))


def trinary_logic_or(a: ScalarData, b: ScalarData) -> ScalarData:
    cas_a = to_sx(a)
    cas_b = to_sx(b)
    return max(cas_a, cas_b)


def is_trinary_true(expression: Union[MathSymbol, Expression]) -> Expression:
    return expression == TrinaryTrue


def is_trinary_true_symbol(expression: Expression) -> bool:
    try:
        return bool((expression == TrinaryTrue).to_np())
    except Exception as e:
        return False


def is_trinary_false(expression: Union[MathSymbol, Expression]) -> Expression:
    return expression == TrinaryFalse


def is_trinary_false_symbol(expression: Expression) -> bool:
    try:
        return bool((expression == TrinaryFalse).to_np())
    except Exception as e:
        return False


def is_trinary_unknown(expression: Union[MathSymbol, Expression]) -> Expression:
    return expression == TrinaryUnknown


def is_trinary_unknown_symbol(expression: Expression) -> bool:
    try:
        return bool((expression == TrinaryUnknown).to_np())
    except Exception as e:
        return False


def replace_with_trinary_logic(expression: Expression) -> Expression:
    """
    Converts a given logical expression into a three-valued logic expression.

    This function recursively processes a logical expression and replaces it
    with its three-valued logic equivalent. The three-valued logic can represent
    true, false, or an indeterminate state. The method identifies specific
    operations like NOT, AND, and OR and applies three-valued logic rules to them.

    :param expression: The logical expression to be converted.
    :return: The converted logical expression in three-valued logic.
    """
    cas_expr = to_sx(expression)
    if cas_expr.n_dep() == 0:
        if is_true_symbol(cas_expr):
            return TrinaryTrue
        if is_false_symbol(cas_expr):
            return TrinaryFalse
        return expression
    op = cas_expr.op()
    if op == ca.OP_NOT:
        return trinary_logic_not(replace_with_trinary_logic(cas_expr.dep(0)))
    if op == ca.OP_AND:
        return trinary_logic_and(
            replace_with_trinary_logic(cas_expr.dep(0)),
            replace_with_trinary_logic(cas_expr.dep(1)),
        )
    if op == ca.OP_OR:
        return trinary_logic_or(
            replace_with_trinary_logic(cas_expr.dep(0)),
            replace_with_trinary_logic(cas_expr.dep(1)),
        )
    return expression


# %% ifs
def _get_return_type(thing: Any):
    """
    Determines the return type based on the input's type and returns the appropriate type.
    Used in "if" expressions.

    :param thing: The input whose type is analyzed.
    :return: The appropriate type based on the input type. If the input type is `int`, `float`, or `Symbol`,
        the return type is `Expression`. Otherwise, the return type is the input's type.
    """
    return_type = type(thing)
    if return_type in (int, float, MathSymbol):
        return Expression
    return return_type


T = TypeVar("T", bound=CasadiScalarWrapper)


def if_else(
    condition: ScalarData,
    if_result: T,
    else_result: T,
) -> T:
    """
    Creates an expression that represents:
    if condition:
        return if_result
    else:
        return else_result
    """
    condition = to_sx(condition)
    if isinstance(if_result, NumericalScalar):
        if_result = Expression(data=if_result)
    if isinstance(else_result, NumericalScalar):
        else_result = Expression(data=else_result)
    return_type = type(else_result)
    if issubclass(return_type, MathSymbol):
        return_type = Expression
    if_result = to_sx(if_result)
    else_result = to_sx(else_result)
    return return_type.from_casadi_sx(ca.if_else(condition, if_result, else_result))


def if_greater(
    a: ScalarData,
    b: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if a > b:
        return if_result
    else:
        return else_result
    """
    a = to_sx(a)
    b = to_sx(b)
    return if_else(ca.gt(a, b), if_result, else_result)


def if_less(
    a: ScalarData,
    b: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if a < b:
        return if_result
    else:
        return else_result
    """
    a = to_sx(a)
    b = to_sx(b)
    return if_else(ca.lt(a, b), if_result, else_result)


def if_greater_zero(
    condition: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if condition > 0:
        return if_result
    else:
        return else_result
    """
    condition = to_sx(condition)
    return if_else(ca.gt(condition, 0), if_result, else_result)


def if_greater_eq_zero(
    condition: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if condition >= 0:
        return if_result
    else:
        return else_result
    """
    return if_greater_eq(condition, 0, if_result, else_result)


def if_greater_eq(
    a: ScalarData,
    b: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if a >= b:
        return if_result
    else:
        return else_result
    """
    a = to_sx(a)
    b = to_sx(b)
    return if_else(ca.ge(a, b), if_result, else_result)


def if_less_eq(
    a: ScalarData,
    b: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if a <= b:
        return if_result
    else:
        return else_result
    """
    return if_greater_eq(b, a, if_result, else_result)


def if_eq_zero(
    condition: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if condition == 0:
        return if_result
    else:
        return else_result
    """
    return if_else(condition, else_result, if_result)


def if_eq(
    a: ScalarData,
    b: ScalarData,
    if_result: Expression,
    else_result: Expression,
) -> Expression:
    """
    Creates an expression that represents:
    if a == b:
        return if_result
    else:
        return else_result
    """
    a = to_sx(a)
    b = to_sx(b)
    return if_else(ca.eq(a, b), if_result, else_result)


def if_eq_cases(
    a: ScalarData,
    b_result_cases: Iterable[Tuple[ScalarData, Expression]],
    else_result: Expression,
) -> Expression:
    """
    if a == b_result_cases[0][0]:
        return b_result_cases[0][1]
    elif a == b_result_cases[1][0]:
        return b_result_cases[1][1]
    ...
    else:
        return else_result
    """
    a = to_sx(a)
    result = to_sx(else_result)
    for b, b_result in b_result_cases:
        b = to_sx(b)
        b_result = to_sx(b_result)
        result = ca.if_else(ca.eq(a, b), b_result, result)
    return type(else_result).from_casadi_sx(result)


def if_cases(
    cases: Sequence[Tuple[ScalarData, Expression]],
    else_result: Expression,
) -> Expression:
    """
    if cases[0][0]:
        return cases[0][1]
    elif cases[1][0]:
        return cases[1][1]
    ...
    else:
        return else_result
    """
    else_result = to_sx(else_result)
    result = to_sx(else_result)
    for i in reversed(range(len(cases))):
        case = to_sx(cases[i][0])
        case_result = to_sx(cases[i][1])
        result = ca.if_else(case, case_result, result)
    return type(else_result).from_expression(result)


def if_less_eq_cases(
    a: ScalarData,
    b_result_cases: Sequence[Tuple[ScalarData, Expression]],
    else_result: Expression,
) -> Expression:
    """
    This only works if b_result_cases is sorted in ascending order.
    if a <= b_result_cases[0][0]:
        return b_result_cases[0][1]
    elif a <= b_result_cases[1][0]:
        return b_result_cases[1][1]
    ...
    else:
        return else_result
    """

    a = to_sx(a)
    result = to_sx(else_result)
    for i in reversed(range(len(b_result_cases))):
        b = to_sx(b_result_cases[i][0])
        b_result = to_sx(b_result_cases[i][1])
        result = ca.if_else(ca.le(a, b), b_result, result)
    return type(else_result).from_casadi_sx(result)


# %% type hints

NumericalScalar = Union[int, float, IntEnum]
NumericalArray = Union[np.ndarray, Iterable[NumericalScalar]]
Numerical2dMatrix = Union[np.ndarray, Iterable[NumericalArray]]
NumericalData = Union[NumericalScalar, NumericalArray, Numerical2dMatrix]

SymbolicScalar = Union[MathSymbol, Expression]
SymbolicArray = Union[Expression]
Symbolic2dMatrix = Union[Expression]
SymbolicData = Union[SymbolicScalar, SymbolicArray, Symbolic2dMatrix]

ScalarData = Union[NumericalScalar, SymbolicScalar]
ArrayData = Union[NumericalArray, SymbolicArray]
Matrix2dData = Union[Numerical2dMatrix, Symbolic2dMatrix]
