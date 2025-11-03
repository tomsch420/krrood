from __future__ import annotations

from collections import UserDict, defaultdict
from contextlib import contextmanager
from copy import copy

from . import logger
from .enums import EQLMode, PredicateType
from .rxnode import RWXNode, ColorLegend
from .symbol_graph import SymbolGraph
from ..class_diagrams import ClassRelation
from ..class_diagrams.class_diagram import Association, WrappedClass
from ..class_diagrams.wrapped_field import WrappedField

"""
Core symbolic expression system used to build and evaluate entity queries.

This module defines the symbolic types (variables, sources, logical and
comparison operators) and the evaluation mechanics.
"""
import contextvars
import operator
import typing
from abc import abstractmethod, ABC
from dataclasses import dataclass, field, fields, MISSING
from functools import lru_cache, cached_property

from typing_extensions import (
    Iterable,
    Any,
    Optional,
    Type,
    Dict,
    ClassVar,
    Union as TypingUnion,
    Generic,
    TypeVar,
    TYPE_CHECKING,
    List,
    Tuple,
    Callable,
)


from .cache_data import (
    is_caching_enabled,
    SeenSet,
    IndexedCache,
)
from .failures import MultipleSolutionFound, NoSolutionFound
from .utils import IDGenerator, is_iterable, generate_combinations
from .hashed_data import HashedValue, HashedIterable, T

if TYPE_CHECKING:
    from .conclusion import Conclusion
    from .predicate import Symbol

_symbolic_mode = contextvars.ContextVar("symbolic_mode", default=None)


def _set_symbolic_mode(mode: EQLMode):
    """
    Set symbolic construction mode.

    :param mode: Can be Query or Rule.
    """
    _symbolic_mode.set(mode)


def in_symbolic_mode(mode: Optional[EQLMode] = None) -> bool:
    """
    Check whether symbolic construction mode is currently active.

    :returns: True if symbolic mode is enabled, otherwise False.
    """
    current_mode = _symbolic_mode.get()
    return current_mode == mode if mode else current_mode is not None


T = TypeVar("T")

id_generator = IDGenerator()

RWXNode.enclosed_name = "Selected Variable"


@dataclass(eq=False)
class SymbolicExpression(Generic[T], ABC):
    """
    Base class for all symbolic expressions.

    Symbolic expressions form a tree and are evaluated lazily to produce
    bindings for variables, subject to logical constraints.

    :ivar _child_: Optional child expression.
    :ivar _id_: Unique identifier of this node.
    :ivar _node_: Backing anytree.Node for visualization and traversal.
    :ivar _conclusion_: Set of conclusion actions attached to this node.
    :ivar _yield_when_false__: If True, may yield even when the expression is false.
    :ivar _is_false_: Internal flag indicating evaluation result for this node.
    """

    _child_: Optional[SymbolicExpression] = field(init=False)
    _id_: int = field(init=False, repr=False, default=None)
    _node_: RWXNode = field(init=False, default=None, repr=False)
    _id_expression_map_: ClassVar[Dict[int, SymbolicExpression]] = {}
    _conclusion_: typing.Set[Conclusion] = field(init=False, default_factory=set)
    _symbolic_expression_stack_: ClassVar[List[SymbolicExpression]] = []
    _yield_when_false_: bool = field(init=False, repr=False, default=False)
    _is_false_: bool = field(init=False, repr=False, default=False)
    _seen_parent_values_by_parent_: Dict[int, Dict[bool, SeenSet]] = field(
        default_factory=dict, init=False, repr=False
    )
    _eval_parent_: Optional[SymbolicExpression] = field(
        default=None, init=False, repr=False
    )
    _plot_color__: Optional[ColorLegend] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not self._id_:
            self._id_ = id_generator(self)
            self._create_node_()
            self._id_expression_map_[self._id_] = self
        if hasattr(self, "_child_") and self._child_ is not None:
            self._update_child_()

    def _update_child_(self, child: Optional[SymbolicExpression] = None):
        child = child or self._child_
        self._child_ = self._update_children_(child)[0]

    def _update_children_(
        self, *children: SymbolicExpression
    ) -> Tuple[SymbolicExpression, ...]:
        children: Dict[int, SymbolicExpression] = dict(enumerate(children))
        for k, v in children.items():
            if not isinstance(v, SymbolicExpression):
                children[k] = Literal(v)
        for k, v in children.items():
            # With graph structure, do not copy nodes; just connect an edge.
            v._node_.parent = self._node_
        return tuple(children.values())

    def _create_node_(self):
        self._node_ = RWXNode(self._name_, data=self, color=self._plot_color_)

    def _reset_cache_(self) -> None:
        """
        Reset the cache of the symbolic expression and its children.
        """
        self._reset_only_my_cache_()
        for child in self._children_:
            child._reset_cache_()

    def _reset_only_my_cache_(self) -> None:
        """
        Reset only the cache of this symbolic expression.
        """
        # Also reset per-parent duplicate tracking and runtime eval parent to ensure reevaluation works
        self._seen_parent_values_by_parent_ = {}
        self._eval_parent_ = None

    @abstractmethod
    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Evaluate the symbolic expression and set the operands indices.
        This method should be implemented by subclasses.
        """
        pass

    def _add_conclusion_(self, conclusion: Conclusion):
        self._conclusion_.add(conclusion)

    @lru_cache(maxsize=None)
    def _projection_(self, when_true: Optional[bool] = True) -> HashedIterable[int]:
        """
        Return the set of variable ids that uniquely identify an output of this node
        for its parent, on the given truth branch.

        The default implementation asks the parent for its projection, and augments it
        with variables referenced by this node's conclusions when the branch can yield.
        """
        if self._parent_:
            projection = self._parent_._projection_(when_true=when_true)
        else:
            projection = HashedIterable()

        if when_true or (when_true is None):
            for child in self._children_:
                for conclusion in child._conclusion_:
                    projection.update(conclusion._unique_variables_)
        return projection

    @property
    def _parent_(self) -> Optional[SymbolicExpression]:
        if self._eval_parent_ is not None:
            return self._eval_parent_
        elif self._node_.parent is not None:
            return self._node_.parent.data
        return None

    @_parent_.setter
    def _parent_(self, value: Optional[SymbolicExpression]):
        self._node_.parent = value._node_ if value is not None else None
        if value is not None and hasattr(value, "_child_"):
            value._child_ = self

    @property
    @lru_cache(maxsize=None)
    def _conditions_root_(self) -> SymbolicExpression:
        """
        Get the root of the symbolic expression tree that contains conditions.
        """
        conditions_root = self._root_
        while conditions_root._child_ is not None:
            conditions_root = conditions_root._child_
            if isinstance(conditions_root._parent_, QueryObjectDescriptor):
                break
        return conditions_root

    @property
    def _root_(self) -> SymbolicExpression:
        """
        Get the root of the symbolic expression tree.
        """
        return self._node_.root.data

    @property
    @abstractmethod
    def _name_(self) -> str:
        pass

    @property
    def _all_nodes_(self) -> List[SymbolicExpression]:
        return [self] + self._descendants_

    @property
    def _descendants_(self) -> List[SymbolicExpression]:
        return [d.data for d in self._node_.descendants]

    @property
    def _children_(self) -> List[SymbolicExpression]:
        return [c.data for c in self._node_.children]

    @classmethod
    def _current_parent_(cls) -> Optional[SymbolicExpression]:
        if cls._symbolic_expression_stack_:
            return cls._symbolic_expression_stack_[-1]
        return None

    @property
    def _sources_(self):
        vars = [v.data for v in self._node_.leaves]
        while any(isinstance(v, SymbolicExpression) for v in vars):
            vars = {
                (
                    v._domain_source_.domain
                    if isinstance(v, Variable) and v._domain_source_
                    else v
                )
                for v in vars
            }
            for v in copy(vars):
                if isinstance(v, SymbolicExpression):
                    vars.remove(v)
                    vars.update(set(v._all_variable_instances_))
        sources = set(HashedIterable(vars))
        return sources

    @property
    @lru_cache(maxsize=None)
    def _unique_variables_(self) -> HashedIterable[Variable]:
        unique_variables = HashedIterable()
        for var in self._all_variable_instances_:
            unique_variables.add(var)
        return unique_variables

    @property
    @abstractmethod
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        """
        Get the leaf instances of the symbolic expression.
        This is useful for accessing the leaves of the symbolic expression tree.
        """
        ...

    def _is_duplicate_output_(self, output: Dict[int, HashedValue]) -> bool:
        """
        Check if the output has been seen before for the current parent and truth branch.
        """
        projection = self._projection_(when_true=not self._is_false_)
        if not projection:
            return False

        required_output = {k: v for k, v in output.items() if k in projection}
        if not required_output:
            return False

        # Use a per-parent seen set to avoid suppressing outputs across different parent contexts
        parent_id = self._parent_._id_ if self._parent_ else self._id_
        seen_by_truth = self._seen_parent_values_by_parent_.setdefault(
            parent_id, {True: SeenSet(), False: SeenSet()}
        )
        seen_set = seen_by_truth[not self._is_false_]

        if seen_set.check(required_output):
            return True
        seen_set.add(required_output)
        return False

    @property
    def _plot_color_(self) -> ColorLegend:
        return self._plot_color__

    @_plot_color_.setter
    def _plot_color_(self, value: ColorLegend):
        self._plot_color__ = value
        self._node_.color = value

    def __and__(self, other):
        return AND(self, other)

    def __or__(self, other):
        return _optimize_or(self, other)

    def __invert__(self):
        return Not(self)

    def __enter__(self, in_rule_mode: bool = False):
        node = self
        to_return = self
        if in_rule_mode or in_symbolic_mode(EQLMode.Rule):
            if (node is self._root_) or (node._parent_ is self._root_):
                node = node._conditions_root_
        if isinstance(node, Variable) and node._parent_ is None:
            node = An(Entity(selected_variables=[node]))
            to_return = node
        SymbolicExpression._symbolic_expression_stack_.append(node)
        return to_return

    def __exit__(self, *args):
        SymbolicExpression._symbolic_expression_stack_.pop()

    def __hash__(self):
        return hash(id(self))

    def __repr__(self):
        return self._name_


@dataclass(eq=False, repr=False)
class CanBehaveLikeAVariable(SymbolicExpression[T], ABC):
    """
    This class adds the monitoring/tracking behaviour on variables that tracks attribute access, calling,
    and comparison operations.
    """

    _var_: CanBehaveLikeAVariable[T] = field(init=False, default=None)
    """
    A variable that is used if the child class to this class want to provide a variable to be tracked other than 
    itself, this is specially useful for child classes that holds a variable instead of being a variable and want
     to delegate the variable behaviour to the variable it has instead.
    For example, this is the case for the ResultQuantifiers & QueryDescriptors that operate on a single selected
    variable.
    """
    _path_: List[ClassRelation] = field(init=False, default_factory=list)
    """
    The path of the variable in the symbol graph as a sequence of relation instances.
    """

    _type_: Type = field(init=False, default=None)
    """
    The type of the variable.
    """

    def __getattr__(self, name: str) -> CanBehaveLikeAVariable[T]:
        # Prevent debugger/private attribute lookups from being interpreted as symbolic attributes
        if not in_symbolic_mode():
            raise AttributeError(
                f"{self.__class__.__name__} object has no attribute {name}, maybe you forgot to "
                f"use the symbolic_mode context manager?"
            )
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(
                f"{self.__class__.__name__} object has no attribute {name}"
            )
        return Attribute(self, name, self._type__)

    @cached_property
    def _type__(self):
        return self._var_._type_ if self._var_ else None

    def __getitem__(self, key) -> CanBehaveLikeAVariable[T]:
        self._if_not_in_symbolic_mode_raise_error_("__getitem__")
        return Index(self, key)

    def __call__(self, *args, **kwargs) -> CanBehaveLikeAVariable[T]:
        self._if_not_in_symbolic_mode_raise_error_("__call__")
        return Call(self, args, kwargs)

    def __eq__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__eq__")
        return Comparator(self, other, operator.eq)

    def __contains__(self, item) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__contains__")
        return Comparator(item, self, operator.contains)

    def __ne__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__ne__")
        return Comparator(self, other, operator.ne)

    def __lt__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__lt__")
        return Comparator(self, other, operator.lt)

    def __le__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__le__")
        return Comparator(self, other, operator.le)

    def __gt__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__gt__")
        return Comparator(self, other, operator.gt)

    def __ge__(self, other) -> Comparator:
        self._if_not_in_symbolic_mode_raise_error_("__ge__")
        return Comparator(self, other, operator.ge)

    def _if_not_in_symbolic_mode_raise_error_(self, method_name: str) -> None:
        if not in_symbolic_mode():
            raise AttributeError(
                f"You are not in symbolic_mode {self.__class__.__name__} object has no attribute"
                f" {method_name}"
            )

    def __hash__(self):
        return super().__hash__()


@dataclass(eq=False)
class ResultQuantifier(CanBehaveLikeAVariable[T], ABC):
    """
    Base for quantifiers that return concrete results from entity/set queries
    (e.g., An, The).
    """

    _child_: QueryObjectDescriptor[T]

    def __post_init__(self):
        super().__post_init__()
        self._var_ = (
            self._child_._var_
            if isinstance(self._child_, CanBehaveLikeAVariable)
            else None
        )
        self._node_.wrap_subtree = True

    @cached_property
    def _type_(self):
        if self._var_:
            return self._var_._type_
        else:
            raise ValueError("No type available as _var_ is None")

    @property
    def _name_(self) -> str:
        return f"{self.__class__.__name__}()"

    def evaluate(
        self,
    ) -> Iterable[TypingUnion[T, Dict[TypingUnion[T, SymbolicExpression[T]], T]]]:
        SymbolGraph().remove_dead_instances()
        with symbolic_mode(mode=None):
            results = self._evaluate__()
            assert not in_symbolic_mode()
            yield from map(self._process_result_, results)
        self._reset_cache_()

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[T]:
        sources = sources or {}
        self._eval_parent_ = parent
        if self._id_ in sources:
            yield sources
            return
        values = self._child_._evaluate__(
            sources, yield_when_false=yield_when_false, parent=self
        )
        for value in values:
            self._is_false_ = self._child_._is_false_
            if self._var_:
                value[self._id_] = value[self._var_._id_]
            yield value

    @lru_cache(maxsize=None)
    def _projection_(self, when_true: Optional[bool] = True) -> HashedIterable[int]:
        """
        Return the projection for result quantifiers.

        Includes selected variables from the child and conclusion variables when applicable.
        """
        projection = (
            self._parent_._projection_(when_true=when_true)
            if self._parent_
            else HashedIterable()
        )
        child = self._child_
        for var in child.selected_variables:
            projection.add(var)
            projection.update(var._unique_variables_)
        if when_true or (when_true is None):
            for conclusion in child._conclusion_:
                projection.update(conclusion._unique_variables_)
        return projection

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        return self._child_._all_variable_instances_

    def _process_result_(
        self, result: Dict[int, HashedValue]
    ) -> TypingUnion[T, UnificationDict]:
        if isinstance(self._child_, Entity):
            return result[self._child_.selected_variable._id_].value
        elif isinstance(self._child_, SetOf):
            selected_variables_ids = [v._id_ for v in self._child_.selected_variables]
            return UnificationDict(
                {
                    self._id_expression_map_[var_id]: value
                    for var_id, value in result.items()
                    if var_id in selected_variables_ids
                }
            )
        else:
            raise NotImplementedError(f"Unknown child type {type(self._child_)}")

    def visualize(
        self,
        figsize=(35, 30),
        node_size=7000,
        font_size=25,
        spacing_x: float = 4,
        spacing_y: float = 4,
        layout: str = "tidy",
        edge_style: str = "orthogonal",
        label_max_chars_per_line: Optional[int] = 13,
    ):
        """
        Visualize the query graph, for arguments' documentation see `rustworkx_utils.RWXNode.visualize`.
        """
        self._node_.visualize(
            figsize=figsize,
            node_size=node_size,
            font_size=font_size,
            spacing_x=spacing_x,
            spacing_y=spacing_y,
            layout=layout,
            edge_style=edge_style,
            label_max_chars_per_line=label_max_chars_per_line,
        )

    @property
    def _plot_color_(self) -> ColorLegend:
        return ColorLegend("ResultQuantifier", "#9467bd")

    @_plot_color_.setter
    def _plot_color_(self, value: ColorLegend):
        self._plot_color__ = value
        self._node_.color = value


class UnificationDict(UserDict):
    """
    A dictionary which maps all expressions that are on a single variable to the original variable id.
    """

    def __getitem__(self, key: CanBehaveLikeAVariable[T]) -> T:
        key = key._id_expression_map_[key._var_._id_]
        return super().__getitem__(key).value


@dataclass(eq=False)
class The(ResultQuantifier[T]):
    """
    Quantifier that expects exactly one result; raises MultipleSolutionFound if more.
    """

    def evaluate(
        self,
    ) -> TypingUnion[T, Dict[TypingUnion[T, SymbolicExpression[T]], T]]:
        all_results = []
        for result in super().evaluate():
            all_results.append(result)
            if len(all_results) > 1:
                raise MultipleSolutionFound(all_results[0], all_results[1])
        if len(all_results) == 0:
            raise NoSolutionFound(self._child_)
        return all_results[0]


@dataclass(eq=False, repr=False)
class An(ResultQuantifier[T]):
    """Quantifier that yields all matching results one by one."""

    ...


@dataclass(eq=False)
class QueryObjectDescriptor(SymbolicExpression[T], ABC):
    """
    Describes the queried object(s), could be a query over a single variable or a set of variables,
    also describes the condition(s)/properties of the queried object(s).
    """

    _child_: Optional[SymbolicExpression[T]] = field(default=None)
    selected_variables: List[CanBehaveLikeAVariable[T]] = field(default_factory=list)
    warned_vars: typing.Set = field(default_factory=set, init=False)

    def __post_init__(self):
        super().__post_init__()
        for variable in self.selected_variables:
            variable._var_._node_.enclosed = True

    @cached_property
    def _type_(self):
        if self._var_:
            return self._var_._type_
        else:
            raise ValueError("No type available as _var_ is None")

    @lru_cache(maxsize=None)
    def _projection_(self, when_true: Optional[bool] = True) -> HashedIterable[int]:
        """
        Return the projection for query object descriptors.

        Includes selected variables and conclusion variables when applicable.
        """
        projection = (
            self._parent_._projection_(when_true=when_true)
            if self._parent_
            else HashedIterable()
        )
        projection.update(self.selected_variables)
        for var in self.selected_variables:
            projection.update(var._unique_variables_)
        if self._child_ and (when_true or (when_true is None)):
            for conclusion in self._child_._conclusion_:
                projection.update(conclusion._unique_variables_)
        return projection

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        self._eval_parent_ = parent
        if self._id_ in sources:
            yield sources
        for values in self.get_constrained_values(sources, yield_when_false):
            values = self.update_data_from_child(values)
            if self._is_false_ and not yield_when_false:
                continue
            self._warn_on_unbound_variables_(values, self.selected_variables)
            if any(var._id_ not in values for var in self.selected_variables):
                yield from self.generate_combinations_with_unbound_variables(values)
            else:
                yield values

    def update_data_from_child(self, sources: Optional[Dict[int, HashedValue]]):
        if self._child_:
            self._is_false_ = self._child_._is_false_
            if self._is_false_:
                return sources
            for conclusion in self._child_._conclusion_:
                sources = conclusion._evaluate__(sources, parent=self)
        return sources

    def get_constrained_values(
        self, sources: Optional[Dict[int, HashedValue]], yield_when_false: bool
    ) -> Iterable[Dict[int, HashedValue]]:
        if self._child_:
            yield from self._child_._evaluate__(
                sources, yield_when_false=yield_when_false, parent=self
            )
        else:
            yield from [sources]

    def generate_combinations_with_unbound_variables(
        self, sources: Dict[int, HashedValue]
    ):
        var_val_gen = {
            var: var._evaluate__(copy(sources), parent=self)
            for var in self.selected_variables
        }
        for sol in generate_combinations(var_val_gen):
            v = copy(sources)
            var_val = {var._id_: sol[var][var._id_] for var in self.selected_variables}
            v.update(var_val)
            yield v

    def _warn_on_unbound_variables_(
        self,
        sources: Dict[int, HashedValue],
        selected_vars: Iterable[CanBehaveLikeAVariable],
    ):
        """
        Warn the user if there are unbound variables in the query descriptor, because this will result in a cartesian
        product join operation.

        :param sources: The bound values after applying the conditions.
        :param selected_vars: The variables selected in the query descriptor.
        """
        unbound_variables = HashedIterable()
        for var in selected_vars:
            unbound_variables.update(
                var._unique_variables_.difference(HashedIterable(values=sources))
            )
        unbound_variables_with_domain = HashedIterable()
        for var in unbound_variables:
            if var.value._domain_ and len(var.value._domain_.values) > 20:
                if var not in self.warned_vars:
                    self.warned_vars.add(var)
                    unbound_variables_with_domain.add(var)
        if unbound_variables_with_domain:
            logger.warning(
                f"\nCartesian Product: "
                f"The following variables are not constrained "
                f"{unbound_variables_with_domain.unwrapped_values}"
                f"\nfor the query descriptor {self._name_}"
            )

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        vars = []
        if self.selected_variables:
            vars.extend(self.selected_variables)
        if self._child_:
            vars.extend(self._child_._all_variable_instances_)
        return vars

    def __repr__(self):
        return self._name_

    @property
    def _plot_color_(self) -> ColorLegend:
        return ColorLegend("ObjectDescriptor", "#d62728")

    @property
    def _name_(self) -> str:
        return f"({', '.join(var._name_ for var in self.selected_variables)})"


@dataclass(eq=False)
class SetOf(QueryObjectDescriptor[T]):
    """
    A query over a set of variables.
    """

    ...


@dataclass(eq=False)
class Entity(QueryObjectDescriptor[T], CanBehaveLikeAVariable[T]):
    """
    A query over a single variable.
    """

    def __post_init__(self):
        self._var_ = self.selected_variable
        super().__post_init__()

    @property
    def selected_variable(self):
        return self.selected_variables[0] if self.selected_variables else None


@dataclass(eq=False)
class Infer(An[T]):

    def __post_init__(self):
        super().__post_init__()
        for v in self._child_.selected_variables:
            v._is_inferred_ = True
        self._node_.wrap_subtree = False

    @property
    def _plot_color_(self) -> ColorLegend:
        return ColorLegend("Infer", "#EAC9FF")


@dataclass
class From:
    """
    A dataclass that holds the domain for a symbolic variable, this will be used instead of the global cache
    of the variable class type.
    """

    domain: Any
    """
    The domain to use for the symbolic variable.
    """


@dataclass(eq=False)
class Variable(CanBehaveLikeAVariable[T]):
    """
    A Variable that queries will assign. The Variable produces results of type `T`.
    """

    _type_: Type = field(default=MISSING, repr=False)
    """
    The result type of the variable. (The value of `T`)
    """

    _name__: str
    """
    The name of the variable.
    """

    _kwargs_: Dict[str, Any] = field(default_factory=dict)
    """
    The properties of the variable as keyword arguments.
    """

    _domain_source_: Optional[From] = field(default=None, kw_only=True, repr=False)
    """
    An optional source for the variable domain. If not given, the global cache of the variable class type will be used
    as the domain, or if kwargs are given the type and the kwargs will be used to create/infer new values for the
    variable.
    """
    _domain_: HashedIterable = field(
        default_factory=HashedIterable, kw_only=True, repr=False
    )
    """
    The iterable domain of values for this variable.
    """
    _invert_: bool = field(init=False, default=False, repr=False)
    """
    Redefined from super class to give it a default value.
    """
    _predicate_type_: Optional[PredicateType] = field(default=None, repr=False)
    """
    If this symbol is an instance of the Predicate class.
    """
    _is_inferred_: bool = field(default=False, repr=False)
    """
    Whether this variable should be inferred.
    """
    _is_indexed_: bool = field(default=True, repr=False)
    """
    Whether this variable cache is indexed or flat.
    """

    _child_vars_: Optional[Dict[str, SymbolicExpression]] = field(
        default_factory=dict, init=False, repr=False
    )
    """
    A dictionary mapping child variable names to variables, these are from the _kwargs_ dictionary. 
    """

    def __post_init__(self):
        self._validate_inputs_and_fill_missing_ones_()
        self._var_ = self
        super().__post_init__()
        # has to be after super init because this needs the node of this variable to be initialized first.
        self._update_child_vars_from_kwargs_()

    def _validate_inputs_and_fill_missing_ones_(self):
        if self._kwargs_ and not self._type_:
            raise ValueError(
                f"Variable {self._name_} has class keyword arguments but no type is specified."
            )
        self._child_ = None
        if self._domain_source_:
            self._update_domain_(self._domain_source_.domain)

    def _update_domain_(self, domain):
        if domain:
            if isinstance(domain, HashedIterable):
                self._domain_ = domain
                return
            elif not is_iterable(domain):
                domain = [HashedValue(domain)]
            self._domain_.set_iterable(domain)

    def _update_child_vars_from_kwargs_(self):
        for k, v in self._kwargs_.items():
            if isinstance(v, SymbolicExpression):
                self._child_vars_[k] = v
            else:
                self._child_vars_[k] = Literal(v, name=k)
        self._update_children_(*self._child_vars_.values())

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        A variable either is already bound in sources by other constraints (Symbolic Expressions).,
        or will yield from current domain if exists,
        or has no domain and will instantiate new values by constructing the type if the type is given.
        """
        self._eval_parent_ = parent
        sources = sources or {}
        if self._id_ in sources:
            yield sources
        elif self._domain_:
            for v in self:
                yield {**sources, **v}
        elif self._should_be_instantiated_:
            yield from self._instantiate_using_child_vars_and_yield_results_(
                sources, yield_when_false
            )
        else:
            raise ValueError("Cannot evaluate variable.")

    @cached_property
    def _should_be_instantiated_(self):
        return self._is_inferred_ or self._predicate_type_

    def _instantiate_using_child_vars_and_yield_results_(
        self, sources: Dict[int, HashedValue], yield_when_false: bool
    ) -> Iterable[Dict[int, HashedValue]]:
        for kwargs in self._generate_combinations_for_child_vars_values_(sources):
            # Build once: unwrapped hashed kwargs for already provided child vars
            bound_kwargs = {k: v[self._child_vars_[k]._id_] for k, v in kwargs.items()}
            instance = self._type_(**{k: hv.value for k, hv in bound_kwargs.items()})
            if self._predicate_type_ == PredicateType.SubClassOfPredicate:
                instance = instance()
            # Compute truth considering inversion
            result_truthy = bool(instance)
            self._is_false_ = result_truthy if self._invert_ else not result_truthy
            if not self._is_false_ or yield_when_false:
                yield self._process_output_and_update_values_(instance, kwargs)

    def _generate_combinations_for_child_vars_values_(
        self, sources: Optional[Dict[int, HashedValue]] = None
    ):
        # Use backtracking generator for early pruning instead of full Cartesian product
        yield from generate_combinations(
            {k: var._evaluate__(sources) for k, var in self._child_vars_.items()}
        )

    def _process_output_and_update_values_(
        self, instance: Any, kwargs: Dict[str, Any]
    ) -> Dict[int, HashedValue]:
        """
        Process the predicate/variable instance and get the results.

        :param instance: The created instance.
        :param kwargs: The keyword arguments of the predicate/variable.
        :return: The results' dictionary.
        """
        hv = HashedValue(instance)
        # kwargs is a mapping from name -> {var_id: HashedValue};
        # we need a single dict {var_id: HashedValue}
        values = {self._id_: hv}
        for d in kwargs.values():
            values.update(d)
        return values

    @property
    def _name_(self):
        return self._name__

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        variables = [self]
        for v in self._child_vars_.values():
            variables.extend(v._all_variable_instances_)
        return variables

    @property
    def _plot_color_(self) -> ColorLegend:
        if self._plot_color__:
            return self._plot_color__
        else:
            return ColorLegend("Variable", "cornflowerblue")

    @_plot_color_.setter
    def _plot_color_(self, value: ColorLegend):
        self._plot_color__ = value
        self._node_.color = value

    def __iter__(self):
        for v in self._domain_:
            yield {self._id_: HashedValue(v)}

    def __repr__(self):
        return self._name_


@dataclass(eq=False, init=False)
class Literal(Variable[T]):
    """
    Literals are variables that are not constructed by their type but by their given data.
    """

    def __init__(
        self, data: Any, name: Optional[str] = None, type_: Optional[Type] = None
    ):
        original_data = data
        data = [data]
        if not is_iterable(data):
            data = HashedIterable([data])
        if not type_:
            first_value = next(iter(data), None)
            type_ = type(first_value) if first_value else None
        if name is None:
            if type_:
                name = type_.__name__
            else:
                name = type(original_data).__name__
        super().__init__(_name__=name, _type_=type_, _domain_source_=From(data))

    @property
    def _plot_color_(self) -> ColorLegend:
        if self._plot_color__:
            return self._plot_color__
        else:
            return ColorLegend("Literal", "#949292")


@dataclass(eq=False)
class DomainMapping(CanBehaveLikeAVariable[T], ABC):
    """
    A symbolic expression the maps the domain of symbolic variables.
    """

    _child_: CanBehaveLikeAVariable[T]
    _invert_: bool = field(init=False, default=False)

    def __post_init__(self):
        super().__post_init__()
        self._var_ = self

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        return self._child_._all_variable_instances_

    @cached_property
    def _type_(self):
        return self._child_._type_

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        self._eval_parent_ = parent
        if self._id_ in sources:
            yield sources
            return
        child_val = self._child_._evaluate__(
            sources, yield_when_false=yield_when_false, parent=self
        )
        for child_v in child_val:
            for v in self._apply_mapping_(child_v[self._child_._id_]):
                self._update_truth_value_(v)
                if yield_when_false or not self._is_false_:
                    yield {**child_v, self._id_: v}

    def _update_truth_value_(self, current_value: HashedValue):
        if (not self._invert_ and current_value.value) or (
            self._invert_ and not current_value.value
        ):
            self._is_false_ = False
        else:
            self._is_false_ = True

    @abstractmethod
    def _apply_mapping_(self, value: HashedValue) -> Iterable[HashedValue]:
        """
        Apply the domain mapping to a symbolic value.
        """
        pass

    @property
    def _plot_color_(self) -> ColorLegend:
        if self._plot_color__:
            return self._plot_color__
        else:
            return ColorLegend("DomainMapping", "#8FC7B8")

    @_plot_color_.setter
    def _plot_color_(self, value: ColorLegend):
        self._plot_color__ = value
        self._node_.color = value


@dataclass(eq=False)
class Attribute(DomainMapping):
    """
    A symbolic attribute that can be used to access attributes of symbolic variables.
    """

    _attr_name_: str
    _child_type_: Type

    def __post_init__(self):
        super().__post_init__()
        with symbolic_mode(mode=None):
            if self._child_wrapped_cls_:
                self._path_ = self._child_._path_ + [
                    Association(
                        self._child_wrapped_cls_,
                        self._wrapped_type_,
                        self._wrapped_field_,
                    )
                ]

    def _update_path_(self):
        self._path_ = self._child_._path_ + [self._relation_]

    @cached_property
    def _relation_(self):
        return Association(
            self._child_wrapped_cls_, self._wrapped_type_, self._wrapped_field_
        )

    @cached_property
    def _wrapped_type_(self):
        return SymbolGraph().class_diagram.get_wrapped_class(self._type_)

    @cached_property
    def _type_(self):
        if self._child_wrapped_cls_:
            # try to get the type endpoint from a field
            try:
                return self._wrapped_field_.type_endpoint
            except (KeyError, AttributeError):
                return None
        else:
            wrapped_cls = WrappedClass(self._child_type_)
            wrapped_cls._class_diagram = SymbolGraph().class_diagram
            wrapped_field = WrappedField(
                wrapped_cls,
                [f for f in fields(self._child_type_) if f.name == self._attr_name_][0],
            )
            try:
                return wrapped_field.type_endpoint
            except (AttributeError, RuntimeError):
                return None

    @cached_property
    def _wrapped_field_(self) -> Optional[WrappedField]:
        return self._child_wrapped_cls_._wrapped_field_name_map_.get(
            self._attr_name_, None
        )

    @cached_property
    def _child_wrapped_cls_(self):
        return SymbolGraph().class_diagram.get_wrapped_class(self._child_type_)

    def _apply_mapping_(self, value: HashedValue) -> Iterable[HashedValue]:
        yield HashedValue(id_=value.id_, value=getattr(value.value, self._attr_name_))

    @property
    def _name_(self):
        return f"{self._child_._var_._name_}.{self._attr_name_}"


@dataclass(eq=False)
class Index(DomainMapping):
    """
    A symbolic indexing operation that can be used to access items of symbolic variables via [] operator.
    """

    _key_: Any

    def _apply_mapping_(self, value: HashedValue) -> Iterable[HashedValue]:
        yield HashedValue(id_=value.id_, value=value.value[self._key_])

    @property
    def _name_(self):
        return f"{self._child_._var_._name_}[{self._key_}]"


@dataclass(eq=False)
class Call(DomainMapping):
    """
    A symbolic call that can be used to call methods on symbolic variables.
    """

    _args_: Tuple[Any, ...] = field(default_factory=tuple)
    _kwargs_: Dict[str, Any] = field(default_factory=dict)

    def _apply_mapping_(self, value: HashedValue) -> Iterable[HashedValue]:
        if len(self._args_) > 0 or len(self._kwargs_) > 0:
            yield HashedValue(
                id_=value.id_, value=value.value(*self._args_, **self._kwargs_)
            )
        else:
            yield HashedValue(id_=value.id_, value=value.value())

    @property
    def _name_(self):
        return f"{self._child_._var_._name_}()"


@dataclass(eq=False)
class Flatten(DomainMapping):
    """
    Domain mapping that flattens an iterable-of-iterables into a single iterable of items.

    Given a child expression that evaluates to an iterable (e.g., Views.bodies), this mapping yields
    one solution per inner element while preserving the original bindings (e.g., the View instance),
    similar to UNNEST in SQL.
    """

    def __post_init__(self):
        if not isinstance(self._child_, SymbolicExpression):
            self._child_ = Literal(self._child_)
        super().__post_init__()
        self._path_ = self._child_._path_

    def _apply_mapping_(self, value: HashedValue) -> Iterable[HashedValue]:
        for inner_v in value.value:
            yield HashedValue(inner_v)

    @cached_property
    def _name_(self):
        return f"Flatten({self._child_._name_})"


@dataclass(eq=False)
class BinaryOperator(SymbolicExpression, ABC):
    """
    A base class for binary operators that can be used to combine symbolic expressions.
    """

    left: SymbolicExpression
    right: SymbolicExpression
    _child_: SymbolicExpression = field(init=False, default=None)
    _cache_: IndexedCache = field(default_factory=IndexedCache, init=False)

    def __post_init__(self):
        super().__post_init__()
        self.left, self.right = self._update_children_(self.left, self.right)
        combined_vars = self.left._unique_variables_.union(
            self.right._unique_variables_
        )
        self._cache_.keys = [
            v.id_
            for v in combined_vars.filter(lambda v: not isinstance(v.value, Literal))
        ]

    def _reset_only_my_cache_(self) -> None:
        super()._reset_only_my_cache_()
        self._cache_.clear()

    def yield_final_output_from_cache(
        self, variables_sources, cache: Optional[IndexedCache] = None
    ) -> Iterable[Dict[int, HashedValue]]:
        cache = self._cache_ if cache is None else cache
        for output, is_false in cache.retrieve(variables_sources):
            self._is_false_ = is_false
            if is_false and self._is_duplicate_output_(output):
                continue
            yield output

    def update_cache(
        self, values: Dict[int, HashedValue], cache: Optional[IndexedCache] = None
    ):
        if not is_caching_enabled():
            return
        cache = self._cache_ if cache is None else cache
        filtered = {k: v for k, v in values.items() if k in cache.keys}
        cache.insert(filtered, output=self._is_false_)

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        """
        Get the leaf instances of the symbolic expression.
        This is useful for accessing the leaves of the symbolic expression tree.
        """
        return self.left._all_variable_instances_ + self.right._all_variable_instances_

    @lru_cache(maxsize=None)
    def _projection_(self, when_true: Optional[bool] = True) -> HashedIterable[int]:
        """
        Return the projection for binary operators.

        Includes variables from both operands symmetrically to ensure non-empty dedup keys.
        """
        projection = HashedIterable()
        # Include variables from both left and right operands symmetrically
        projection.update(self.left._unique_variables_)
        projection.update(self.right._unique_variables_)
        if when_true or (when_true is None):
            for conclusion in self._conclusion_:
                projection.update(conclusion._unique_variables_)
        if self._parent_:
            projection.update(self._parent_._projection_(when_true))
        return projection


@dataclass(eq=False)
class ForAll(BinaryOperator):

    solution_set: List[Dict[int, HashedValue]] = field(init=False, default_factory=list)

    @property
    def _name_(self) -> str:
        return self.__class__.__name__

    @property
    def variable(self):
        return self.left

    @variable.setter
    def variable(self, value):
        self.left = value

    @property
    def condition(self):
        return self.right

    @condition.setter
    def condition(self, value):
        self.right = value

    @property
    @lru_cache(maxsize=None)
    def condition_unique_variable_ids(self) -> List[int]:
        return [
            v.id_
            for v in self.condition._unique_variables_.difference(
                self.left._unique_variables_
            )
        ]

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        self._eval_parent_ = parent

        # Always reset per evaluation
        self.solution_set = []

        var_val_index = 0

        for var_val in self.variable._evaluate__(sources, parent=self):
            ctx = {**sources, **var_val}
            current = []

            # Evaluate the condition under this particular universal value
            for condition_val in self.condition._evaluate__(ctx, parent=self):
                if self.condition._is_false_:
                    continue
                # Keep only the non-universal variables from the condition bindings
                filtered = {
                    k: v
                    for k, v in condition_val.items()
                    if k in self.condition_unique_variable_ids
                }
                current.append(filtered)

            # If the condition yields no satisfying bindings for this universal value, the universal fails
            if not current:
                self.solution_set = []
                break

            if var_val_index == 0:
                # seed with all satisfying non-universal bindings
                self.solution_set = current
            else:
                # Intersect with previously accumulated satisfying bindings
                current_set = {tuple(sorted(d.items())) for d in current}
                self.solution_set = [
                    d
                    for d in self.solution_set
                    if tuple(sorted(d.items())) in current_set
                ]

            var_val_index += 1

            # Early exit if the intersection is empty
            if not self.solution_set:
                break

        # Yield the remaining bindings (non-universal) merged with the incoming sources
        for sol in self.solution_set or []:
            out = copy(sol)
            out.update(sources)
            yield out


@dataclass(eq=False)
class Exists(BinaryOperator):
    """
    An existential checker that checks if a condition holds for any value of the variable given, the benefit
    of this is that this short circuits the condition and returns True if the condition holds for any value without
    getting all the condition values that hold for one specific value of the variable.
    """

    @property
    def _name_(self) -> str:
        return self.__class__.__name__

    @property
    def variable(self):
        return self.left

    @variable.setter
    def variable(self, value):
        self.left = value

    @property
    def condition(self):
        return self.right

    @condition.setter
    def condition(self, value):
        self.right = value

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        self._eval_parent_ = parent
        for var_val in self.variable._evaluate__(sources, parent=self):
            ctx = {**sources, **var_val}

            # Evaluate the condition under this particular universal value
            for condition_val in self.condition._evaluate__(ctx, parent=self):
                if self.condition._is_false_:
                    continue
                condition_val = {**ctx, **condition_val}
                yield condition_val
                break


@dataclass(eq=False)
class Comparator(BinaryOperator):
    """
    A symbolic equality check that can be used to compare symbolic variables.
    """

    left: CanBehaveLikeAVariable
    right: CanBehaveLikeAVariable
    operation: Callable[[Any, Any], bool]
    _invert__: bool = field(init=False, default=False)
    operation_name_map: ClassVar[Dict[Any, str]] = {
        operator.eq: "==",
        operator.ne: "!=",
        operator.lt: "<",
        operator.le: "<=",
        operator.gt: ">",
        operator.ge: ">=",
    }

    @property
    def _invert_(self):
        return self._invert__

    @_invert_.setter
    def _invert_(self, value):
        if value == self._invert__:
            return
        self._invert__ = value
        prev_operation = self.operation
        match self.operation:
            case operator.lt:
                self.operation = operator.ge if self._invert_ else self.operation
            case operator.gt:
                self.operation = operator.le if self._invert_ else self.operation
            case operator.le:
                self.operation = operator.gt if self._invert_ else self.operation
            case operator.ge:
                self.operation = operator.lt if self._invert_ else self.operation
            case operator.eq:
                self.operation = operator.ne if self._invert_ else self.operation
            case operator.ne:
                self.operation = operator.eq if self._invert_ else self.operation
            case operator.contains:

                def not_contains(a, b):
                    return not operator.contains(a, b)

                self.operation = not_contains if self._invert_ else self.operation
            case _:
                raise ValueError(f"Unsupported operation: {self.operation.__name__}")
        self._node_.name = self._node_.name.replace(
            prev_operation.__name__, self.operation.__name__
        )

    @property
    def _name_(self):
        if self.operation in self.operation_name_map:
            return self.operation_name_map[self.operation]
        return self.operation.__name__

    def _reset_only_my_cache_(self) -> None:
        super()._reset_only_my_cache_()
        self._cache_.clear()

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Compares the left and right symbolic variables using the "operation".

        :param sources: Dictionary of symbolic variable id to a value of that variable, the left and right values
        will retrieve values from sources if they exist, otherwise will directly retrieve them from the original
        sources.
        :return: Yields a HashedIterable mapping a symbolic variable id to a value of that variable, it will contain
         only two values, the left and right symbolic values.
        """
        sources = sources or {}
        self._eval_parent_ = parent
        self._yield_when_false_ = yield_when_false

        if self._id_ in sources:
            yield sources
            return

        if is_caching_enabled() and self._cache_.check(sources):
            yield from self.yield_final_output_from_cache(sources)
            return

        first_operand, second_operand = self.get_first_second_operands(sources)

        yield from filter(
            self.apply_operation,
            (
                second_val
                for first_val in first_operand._evaluate__(sources, parent=self)
                for second_val in second_operand._evaluate__(first_val, parent=self)
            ),
        )

    def apply_operation(self, operand_values: Dict[int, HashedValue]) -> bool:
        res = self.operation(
            operand_values[self.left._id_].value, operand_values[self.right._id_].value
        )
        self._is_false_ = not res
        if res or self._yield_when_false_:
            operand_values[self._id_] = HashedValue(res)
            self.update_cache(operand_values)
            return True
        return False

    def get_first_second_operands(
        self, sources: Dict[int, HashedValue]
    ) -> Tuple[SymbolicExpression, SymbolicExpression]:
        if sources and any(
            v.value._var_._id_ in sources for v in self.right._unique_variables_
        ):
            return self.right, self.left
        else:
            return self.left, self.right

    @property
    def _plot_color_(self) -> ColorLegend:
        return ColorLegend("Comparator", "#ff7f0e")


@dataclass(eq=False)
class LogicalOperator(BinaryOperator, ABC):
    """
    A symbolic operation that can be used to combine multiple symbolic expressions.
    """

    right_cache: IndexedCache = field(default_factory=IndexedCache, init=False)

    def __post_init__(self):
        super().__post_init__()
        right_vars = self.right._unique_variables_.filter(
            lambda v: not isinstance(v, Literal)
        )
        self.right_cache.keys = [v.id_ for v in right_vars]

    @property
    def _name_(self):
        return self.__class__.__name__

    @property
    def _plot_color_(self) -> ColorLegend:
        return ColorLegend("LogicalOperator", "#2ca02c")


@dataclass(eq=False, repr=False)
class AND(LogicalOperator):
    """
    A symbolic AND operation that can be used to combine multiple symbolic expressions.
    """

    def _reset_only_my_cache_(self) -> None:
        super()._reset_only_my_cache_()
        self.right_cache.clear()

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        # init an empty source if none is provided
        sources = sources or {}
        self._eval_parent_ = parent
        left_values = self.left._evaluate__(
            sources, yield_when_false=yield_when_false, parent=self
        )
        for left_value in left_values:

            left_value.update(sources)

            if self.left._is_false_:
                self._is_false_ = True
                if yield_when_false and not self._is_duplicate_output_(left_value):
                    yield left_value
            elif self.cache_enabled_and_right_has_values(left_value):
                yield from self.yield_from_right_cache(left_value, yield_when_false)
            else:
                yield from self.evaluate_right(left_value, yield_when_false)

    def yield_from_right_cache(
        self, left_value: Dict[int, HashedValue], yield_when_false: bool
    ) -> Iterable[Dict[int, HashedValue]]:
        for _out in self.yield_final_output_from_cache(left_value, self.right_cache):
            if self._is_false_ and not yield_when_false:
                continue
            yield _out

    def cache_enabled_and_right_has_values(self, left_value: Dict[int, HashedValue]):
        return (
            is_caching_enabled()
            and not in_symbolic_mode(EQLMode.Rule)
            and self.right_cache.cache
            and self.right_cache.check(left_value)
        )

    def evaluate_right(
        self, left_value: Dict[int, HashedValue], yield_when_false: bool
    ):
        # constrain right values by available sources
        right_values = self.right._evaluate__(
            left_value, yield_when_false=yield_when_false, parent=self
        )

        # For the found left value, find all right values,
        # and yield the (left, right) results found.
        for right_value in right_values:
            output = copy(right_value)
            output.update(left_value)
            self._is_false_ = self.right._is_false_
            self.update_cache(right_value, self.right_cache)
            yield output


@dataclass(eq=False)
class OR(LogicalOperator, ABC):
    """
    A symbolic single choice operation that can be used to choose between multiple symbolic expressions.
    """

    @lru_cache(maxsize=None)
    def _projection_(self, when_true: Optional[bool] = True) -> HashedIterable[int]:
        """
        Return the projection for OR operators.

        Includes variables from both operands symmetrically to ensure non-empty dedup keys.
        """
        projection = HashedIterable()
        # Include variables from both left and right operands symmetrically
        projection.update(self.left._unique_variables_)
        projection.update(self.right._unique_variables_)
        if when_true or (when_true is None):
            for conclusion in self.left._conclusion_:
                projection.update(conclusion._unique_variables_)
            for conclusion in self.right._conclusion_:
                projection.update(conclusion._unique_variables_)
        if self._parent_:
            projection.update(self._parent_._projection_(when_true))
        return projection


@dataclass(eq=False)
class Union(OR):
    left_cache: IndexedCache = field(default_factory=IndexedCache, init=False)
    left_evaluated: bool = field(default=False, init=False)
    right_evaluated: bool = field(default=False, init=False)

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        # init an empty source if none is provided
        sources = sources or {}
        self._eval_parent_ = parent
        if is_caching_enabled() and self._cache_.check(sources):
            yield from self.yield_final_output_from_cache(sources)
            return

        # constrain left values by available sources
        left_values = self.left._evaluate__(
            sources, yield_when_false=yield_when_false, parent=self
        )

        for left_value in left_values:
            output = copy(sources)
            output.update(left_value)
            self.left_evaluated = True
            if self.left._is_false_ and yield_when_false:
                yield from self.evaluate_right(output, yield_when_false)
                continue
            if self._is_duplicate_output_(output):
                continue
            self.update_cache(output, self._cache_)
            yield output
        self.left_evaluated = False
        yield from self.evaluate_right(sources, yield_when_false)

    def evaluate_right(
        self, sources: Optional[Dict[int, HashedValue]], yield_when_false: bool
    ) -> Iterable[Dict[int, HashedValue]]:
        # For the found left value, find all right values,
        # and yield the (left, right) results found.

        right_values = self.right._evaluate__(
            sources, yield_when_false=yield_when_false, parent=self
        )

        for right_value in right_values:
            sources.update(right_value)
            if yield_when_false and self.left_evaluated:
                self._is_false_ = self.left._is_false_ and self.right._is_false_
            else:
                self._is_false_ = False
            if not self._is_false_ and self._is_duplicate_output_(sources):
                continue
            self.right_evaluated = True
            self.update_cache(sources, self._cache_)
            yield sources

        self.right_evaluated = False


@dataclass(eq=False)
class ElseIf(OR):
    """
    A symbolic single choice operation that can be used to choose between multiple symbolic expressions.
    """

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
        parent: Optional[SymbolicExpression] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Constrain the symbolic expression based on the indices of the operands.
        This method overrides the base class method to handle ElseIf logic.
        """
        # init an empty source if none is provided
        sources = sources or {}
        self._eval_parent_ = parent

        # constrain left values by available sources
        # Force yield_when_false=True for the left branch to preserve else-if semantics
        left_values = self.left._evaluate__(sources, yield_when_false=True, parent=self)
        any_left = False
        for left_value in left_values:
            any_left = True
            left_value.update(sources)
            if self.left._is_false_:
                if is_caching_enabled() and self.right_cache.check(left_value):
                    yield from self.yield_final_output_from_cache(
                        left_value, self.right_cache
                    )
                    continue
                right_values = self.right._evaluate__(
                    left_value, yield_when_false=yield_when_false, parent=self
                )
                for right_value in right_values:
                    self._is_false_ = self.right._is_false_
                    output = copy(left_value)
                    output.update(right_value)
                    if self._is_false_ and not yield_when_false:
                        continue
                    if not self._is_false_ and self._is_duplicate_output_(output):
                        continue
                    self.update_cache(right_value, self.right_cache)
                    yield output
            else:
                self._is_false_ = False
                yield left_value
        # If left produced no values at all, evaluate right against sources
        if not any_left:
            right_values = self.right._evaluate__(
                sources, yield_when_false=yield_when_false, parent=self
            )
            for right_value in right_values:
                self._is_false_ = self.right._is_false_
                if self._is_false_ and not yield_when_false:
                    continue
                self.update_cache(right_value, self.right_cache)
                yield right_value


def Not(operand: Any) -> SymbolicExpression:
    """
    A symbolic NOT operation that can be used to negate symbolic expressions.
    """
    if not isinstance(operand, SymbolicExpression):
        operand = Literal(operand)
    if isinstance(operand, ResultQuantifier):
        raise NotImplementedError(
            f"Symbolic NOT operations on {ResultQuantifier} operands "
            f"are not allowed, you can negate the conditions or {QueryObjectDescriptor}"
            f" instead as negating quantifiers is most likely not what you want"
            f" as it is ambiguous."
        )
    elif isinstance(operand, Entity):
        operand = operand.__class__(Not(operand._child_), operand.selected_variables)
    elif isinstance(operand, SetOf):
        operand = operand.__class__(Not(operand._child_), operand.selected_variables)
    elif isinstance(operand, AND):
        operand = ElseIf(Not(operand.left), Not(operand.right))
    elif isinstance(operand, OR):
        operand = AND(Not(operand.left), Not(operand.right))
    else:
        operand._invert_ = True
    return operand


OperatorOptimizer = Callable[[SymbolicExpression, SymbolicExpression], LogicalOperator]


def chained_logic(
    operator: TypingUnion[Type[LogicalOperator], OperatorOptimizer], *conditions
):
    """
    A chian of logic operation over multiple conditions, e.g. cond1 | cond2 | cond3.

    :param operator: The symbolic operator to apply between the conditions.
    :param conditions: The conditions to be chained.
    """
    prev_operation = None
    for condition in conditions:
        if prev_operation is None:
            prev_operation = condition
            continue
        prev_operation = operator(prev_operation, condition)
    return prev_operation


@contextmanager
def rule_mode(query: Optional[SymbolicExpression] = None):
    """
    Wrapper around symbolic construction mode to easily enable rule mode
    """
    # delegate to symbolic_mode
    with symbolic_mode(query, EQLMode.Rule) as ctx:
        yield ctx


@contextmanager
def symbolic_mode(
    query: Optional[SymbolicExpression] = None, mode: EQLMode = EQLMode.Query
):
    """
    Context manager to temporarily enable symbolic construction mode.

    Within the context, calling classes decorated with ``@symbol`` produces
    symbolic Variables instead of real instances.

    :param query: Optional symbolic expression to also enter/exit as a context.
    """
    prev_mode = _symbolic_mode.get()
    try:
        if query is not None:
            query.__enter__(in_rule_mode=True)
        _set_symbolic_mode(mode)
        yield SymbolicExpression._current_parent_()
    finally:
        if query is not None:
            query.__exit__()
        _set_symbolic_mode(prev_mode)


def properties_to_expression_tree(
    var: CanBehaveLikeAVariable, properties: Dict[str, Any]
) -> Tuple[SymbolicExpression, List[SymbolicExpression]]:
    """
    Convert properties of a variable to a symbolic expression.
    """
    with symbolic_mode():
        conditions = [getattr(var, k) == v for k, v in properties.items()]
        expression = None
        if len(conditions) == 1:
            expression = conditions[0]
        elif len(conditions) > 1:
            expression = chained_logic(AND, *conditions)
    return expression, [op.left for op in conditions]


def _optimize_or(left: SymbolicExpression, right: SymbolicExpression) -> OR:
    with symbolic_mode(mode=None):
        left_vars = left._unique_variables_.filter(
            lambda v: not isinstance(v.value, Literal)
        )
        right_vars = right._unique_variables_.filter(
            lambda v: not isinstance(v.value, Literal)
        )
        if set(left_vars.unwrapped_values) == set(right_vars.unwrapped_values):
            return ElseIf(left, right)
        else:
            return Union(left, right)
