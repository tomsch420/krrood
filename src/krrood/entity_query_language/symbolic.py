from __future__ import annotations

from collections import UserDict, defaultdict
from contextlib import contextmanager
from copy import copy

from . import logger
from .enums import EQLMode, PredicateType
from .rxnode import RWXNode, ColorLegend
from .symbol_graph import SymbolGraph
from ..class_diagrams import Relation
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
from dataclasses import dataclass, field, fields
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
)
from typing_extensions import List, Tuple, Callable


from .cache_data import (
    cache_enter_count,
    cache_search_count,
    cache_match_count,
    is_caching_enabled,
    SeenSet,
    IndexedCache,
    get_cache_keys_for_class_,
    yield_class_values_from_cache,
)
from .failures import MultipleSolutionFound, NoSolutionFound
from .utils import IDGenerator, is_iterable, generate_combinations
from .hashed_data import HashedValue, HashedIterable, T, HV_TRUE, HV_FALSE

if TYPE_CHECKING:
    from .conclusion import Conclusion

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
    _seen_parent_values_: Dict[bool, SeenSet] = field(
        default_factory=lambda: {True: SeenSet(), False: SeenSet()},
        init=False,
        repr=False,
    )
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
        self._seen_parent_values_ = {True: SeenSet(), False: SeenSet()}
        # Also reset per-parent duplicate tracking and runtime eval parent to ensure reevaluation works
        self._seen_parent_values_by_parent_ = {}
        self._eval_parent_ = None

    @abstractmethod
    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Evaluate the symbolic expression and set the operands indices.
        This method should be implemented by subclasses.
        """
        pass

    def _add_conclusion_(self, conclusion: Conclusion):
        self._conclusion_.add(conclusion)

    @lru_cache(maxsize=None)
    def _required_variables_from_child_(
        self, child: Optional[SymbolicExpression] = None, when_true: bool = True
    ):
        if self._parent_:
            vars = self._parent_._required_variables_from_child_(
                self, when_true=when_true
            )
        else:
            vars = HashedIterable()
        if when_true or (when_true is None):
            for child in self._children_:
                for conc in child._conclusion_:
                    vars.update(conc._unique_variables_)
        return vars

    @property
    def _conclusions_of_all_descendants_(self) -> List[Conclusion]:
        return [conc for child in self._descendants_ for conc in child._conclusion_]

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
    def _all_node_names_(self) -> List[str]:
        return [node._node_.name for node in self._all_nodes_]

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
        required_vars = self._parent_._required_variables_from_child_(
            self, when_true=not self._is_false_
        )
        if not required_vars:
            return False
        required_output = {k: v for k, v in output.items() if k in required_vars}
        if not required_output:
            return False
        # Use a per-parent seen set to avoid suppressing outputs across different parent contexts
        parent_id = self._parent_._id_
        seen_by_truth = self._seen_parent_values_by_parent_.setdefault(
            parent_id, {True: SeenSet(), False: SeenSet()}
        )
        seen_set = seen_by_truth[not self._is_false_]
        if seen_set.check(required_output):
            return True
        else:
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
    _path_: List[Relation] = field(init=False, default_factory=list)
    """
    The path of the variable in the symbol graph as a sequence of relation instances.
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
        return self._type_

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
        self._var_ = self._child_._var_

    @cached_property
    def _type_(self):
        if self._var_:
            return self._var_._type_
        else:
            raise ValueError("No type available as _var_ is None")

    @property
    def _name_(self) -> str:
        return f"{self.__class__.__name__}()"

    @abstractmethod
    def evaluate(
        self,
    ) -> TypingUnion[Iterable[T], T, Iterable[Dict[SymbolicExpression[T], T]]]:
        """
        This is the method called by the user to evaluate the full query.
        """
        ...

    @lru_cache(maxsize=None)
    def _required_variables_from_child_(
        self, child: Optional[SymbolicExpression] = None, when_true: bool = True
    ):
        child = self._child_ if child is None else child
        if self._parent_:
            vars = self._parent_._required_variables_from_child_(
                self, when_true=when_true
            )
        else:
            vars = HashedIterable()
        for var in child.selected_variables:
            vars.add(var)
            vars.update(var._unique_variables_)
        if when_true or (when_true is None):
            for conc in child._conclusion_:
                vars.update(conc._unique_variables_)
        return vars

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

    def evaluate(self) -> TypingUnion[Iterable[T], T, UnificationDict]:
        result = self._evaluate_()
        result = self._process_result_(result)
        self._reset_cache_()
        return result

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        v = self._evaluate_(sources, yield_when_false=yield_when_false)
        yield v
        return

    def _evaluate_(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Dict[int, HashedValue]:
        sources = sources or {}
        self._yield_when_false_ = yield_when_false
        self._child_._eval_parent_ = self
        if self._id_ in sources:
            return sources
        sol_gen = self._child_._evaluate__(sources)
        result = None
        for sol in sol_gen:
            if result is None:
                result = sol
                result.update(sources)
            else:
                raise MultipleSolutionFound(result, sol)
        if result is None:
            self._is_false_ = True
        if self._is_false_:
            if self._yield_when_false_:
                result = sources
            else:
                raise NoSolutionFound(self._child_)
        else:
            result[self._id_] = result[self._var_._id_]
        return result


@dataclass(eq=False, repr=False)
class An(ResultQuantifier[T]):
    """Quantifier that yields all matching results one by one."""

    def __post_init__(self):
        super().__post_init__()
        self._node_.wrap_subtree = True

    def evaluate(
        self,
    ) -> Iterable[TypingUnion[T, Dict[TypingUnion[T, SymbolicExpression[T]], T]]]:
        with symbolic_mode(mode=None):
            results = self._evaluate__()
            assert not in_symbolic_mode()
            yield from map(self._process_result_, results)
        self._reset_cache_()

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[T]:
        sources = sources or {}
        if self._id_ in sources:
            if (
                isinstance(self._parent_, LogicalOperator)
                or self is self._conditions_root_
            ):
                if not self._is_false_ or yield_when_false:
                    yield sources
            else:
                yield sources
        else:
            self._child_._eval_parent_ = self
            values = self._child_._evaluate__(
                sources, yield_when_false=yield_when_false
            )
            for value in values:
                self._is_false_ = self._child_._is_false_
                if yield_when_false or not self._is_false_:
                    if self._var_:
                        value[self._id_] = value[self._var_._id_]
                    yield value


@dataclass(eq=False)
class QueryObjectDescriptor(CanBehaveLikeAVariable[T], ABC):
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
    def _required_variables_from_child_(
        self, child: Optional[SymbolicExpression] = None, when_true: bool = True
    ):
        child = self._child_ if not child else child
        required_vars = self._parent_._required_variables_from_child_(
            self, when_true=when_true
        )
        required_vars.update(self.selected_variables)
        for var in self.selected_variables:
            required_vars.update(var._unique_variables_)
        if child and (when_true or (when_true is None)):
            for conc in child._conclusion_:
                required_vars.update(conc._unique_variables_)
        return required_vars

    def _evaluate_(
        self,
        selected_vars: Optional[Iterable[CanBehaveLikeAVariable]] = None,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        if self._id_ in sources:
            yield sources
        if self._child_:
            self._child_._eval_parent_ = self
            child_values = self._child_._evaluate__(
                sources, yield_when_false=yield_when_false
            )
        else:
            child_values = [sources]
        for v in child_values:
            if self._child_:
                self._is_false_ = self._child_._is_false_
            if self._is_false_ and not yield_when_false:
                continue
            if self._child_:
                for conclusion in self._child_._conclusion_:
                    v = conclusion._evaluate__(v)
            self._warn_on_unbound_variables_(v, selected_vars)
            if any(var._id_ not in v for var in selected_vars):
                var_val_gen = {var: var._evaluate__(copy(v)) for var in selected_vars}
                original_v = v
                for sol in generate_combinations(var_val_gen):
                    v = copy(original_v)
                    var_val = {var._id_: sol[var][var._id_] for var in selected_vars}
                    v.update(var_val)
                    yield v
            else:
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

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        self._yield_when_false_ = yield_when_false
        sol_gen = self._evaluate_(
            self.selected_variables, sources, yield_when_false=self._yield_when_false_
        )
        for sol in sol_gen:
            sol.update(sources)
            if self.selected_variables:
                var_val = {
                    var._id_: next(
                        var._evaluate__(sol, yield_when_false=self._yield_when_false_)
                    )[var._id_]
                    for var in self.selected_variables
                    if var._id_ in sol
                }
                sol.update(var_val)
                yield sol
            else:
                yield sol


@dataclass(eq=False)
class Entity(QueryObjectDescriptor[T]):
    """
    A query over a single variable.
    """

    def __post_init__(self):
        self._var_ = self.selected_variable
        super().__post_init__()

    @property
    def selected_variable(self):
        return self.selected_variables[0] if self.selected_variables else None

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[T]:
        self._yield_when_false_ = yield_when_false
        selected_variables = [self.selected_variable] if self.selected_variable else []
        sol_gen = self._evaluate_(
            selected_variables, sources, yield_when_false=self._yield_when_false_
        )
        for sol in sol_gen:
            sol.update(sources)
            if self._yield_when_false_ or not self._is_false_:
                if self.selected_variable:
                    for var_val in self.selected_variable._evaluate__(sol):
                        var_val.update(sol)
                        yield var_val
                else:
                    yield sol


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
    _name__: str
    """
    The name of the variable.
    """
    _type_: Type
    """
    The class that this variable represents.
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
    _cache_: ClassVar[Dict[Type, IndexedCache]] = defaultdict(IndexedCache)
    """
    A mapping from variable type to an indexed cache of all seen inputs and outputs of the variable type. 
    """
    _child_vars_: Optional[Dict[str, SymbolicExpression]] = field(
        default_factory=dict, init=False, repr=False
    )
    """
    A dictionary mapping child variable names to variables, these are from the _kwargs_ dictionary. 
    """
    _kwargs_expression_: Optional[SymbolicExpression] = field(
        default=None, init=False, repr=False
    )
    """
    An expression of the constraints added from the keyword arguments of the variable.
    """
    _evaluating_kwargs_expression_: bool = field(default=False, init=False, repr=False)
    """
    A flag indicating that the kwargs expression is currently being evaluated so do not evaluate them again, and instead
    yield from the domain.
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
            new_domain = None
            if isinstance(domain, HashedIterable):
                self._domain_ = domain
            if isinstance(domain, SymbolicExpression):
                new_domain = (v[domain._id_] for v in domain._evaluate__())
            elif not is_iterable(domain):
                new_domain = [HashedValue(domain)]
            new_domain = new_domain or domain
            self._domain_.set_iterable(new_domain)

    def _update_child_vars_from_kwargs_(self):
        if self._kwargs_:
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
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        A variable either is already bound in sources by other constraints (Symbolic Expressions).,
        or has no domain and will instantiate new values by constructing the type if the type is given,
        or will yield from current domain if exists.
        """
        self._yield_when_false_ = yield_when_false
        sources = sources or {}
        if self._id_ in sources:
            if (
                isinstance(self._parent_, LogicalOperator)
                or self is self._conditions_root_
            ):
                if not self._is_false_ or yield_when_false:
                    yield sources
            else:
                yield sources
        elif self._domain_ and not self._is_inferred_:
            if self._kwargs_expression_ and not self._evaluating_kwargs_expression_:
                # because when kwargs expression exists,
                # it will constrain the domain further to fit the kwargs provided.
                yield from self._evaluate_kwargs_expression_(sources)
            else:
                # If no kwargs expression, or is currently being evaluated then yield from the domain directly,
                # if the kwargs is being evaluated, it will want to take the domain from here and constrain it further.
                yield from self
        elif not self._is_inferred_ and not self._predicate_type_:
            self._update_domain_and_kwargs_expression_()
            yield from self._evaluate__(
                sources, yield_when_false=self._yield_when_false_
            )
        elif self._child_vars_:
            for kwargs in self._generate_combinations_for_child_vars_values_(sources):
                yield from self._yield_from_cache_or_instantiate_new_values_(
                    sources, kwargs
                )

    def _evaluate_kwargs_expression_(
        self, sources: Optional[Dict[int, HashedValue]] = None
    ):
        self._evaluating_kwargs_expression_ = True
        for v in self._kwargs_expression_._evaluate__(
            sources, yield_when_false=self._yield_when_false_
        ):
            if self is self._conditions_root_ or isinstance(
                self._parent_, LogicalOperator
            ):
                self._is_false_ = self._kwargs_expression_._is_false_
                if not self._is_false_ or self._yield_when_false_:
                    yield v
            else:
                yield v
        self._evaluating_kwargs_expression_ = False

    def _update_domain_and_kwargs_expression_(self):
        self._domain_source_ = From(self._cache_values_)
        self._update_domain_(self._domain_source_.domain)
        if self._kwargs_:
            parents = [p for p in self._node_.parents]
            self._kwargs_expression_, attributes = properties_to_expression_tree(
                self, self._child_vars_
            )
            self._kwargs_expression_ = An(Entity(self._kwargs_expression_, [self]))
            self._replace_expression_with_(self._kwargs_expression_, parents)

    def _replace_expression_with_(
        self, new_expression: SymbolicExpression, parents: Optional[List] = None
    ):
        if not parents:
            parents = [
                p
                for p in self._node_.parents
                if new_expression._node_ not in p.ancestors
            ]
        for child in self._node_.children:
            self._node_.remove_child(child)
        for parent in parents:
            new_expression._parent_ = parent.data
            self._node_.remove_parent(parent)
        self._node_.remove()
        self._node_ = new_expression._node_

    def _instantiate_new_values_or_yield_from_cache_(
        self, sources: Optional[Dict[int, HashedValue]] = None
    ) -> Iterable[Dict[int, HashedValue]]:
        # Precompute generators only when we have child vars
        if self._child_vars_:
            for kwargs in self._generate_combinations_for_child_vars_values_(sources):
                yield from self._yield_from_cache_or_instantiate_new_values_(
                    sources, kwargs
                )
        else:
            yield from self._yield_from_cache_or_instantiate_new_values_(sources)

    def _generate_combinations_for_child_vars_values_(
        self, sources: Optional[Dict[int, HashedValue]] = None
    ):
        # Use backtracking generator for early pruning instead of full Cartesian product
        yield from generate_combinations(
            {k: var._evaluate__(sources) for k, var in self._child_vars_.items()}
        )

    def _yield_from_cache_or_instantiate_new_values_(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        kwargs: Dict[str, Dict[int, HashedValue]] = None,
    ):
        kwargs = kwargs or {}
        # Try cache fast-path first when allowed
        retrieved = False
        if not self._is_inferred_ and self._is_indexed_:
            for v in self._search_and_yield_from_cache_(kwargs):
                retrieved = True
                if sources:
                    v.update(sources)
                yield v

        # If nothing retrieved and we are allowed to instantiate
        if (not retrieved) and (self._is_inferred_ or self._predicate_type_):
            yield from self._instantiate_new_values_and_yield_results_(kwargs, sources)

    def _instantiate_new_values_and_yield_results_(
        self,
        kwargs: Dict[str, Dict[int, HashedValue]],
        sources: Optional[Dict[int, HashedValue]] = None,
    ) -> Iterable[Dict[int, HashedValue]]:
        # Build once: unwrapped hashed kwargs for already provided child vars
        bound_kwargs = {k: v[self._child_vars_[k]._id_] for k, v in kwargs.items()}
        # For missing kwargs, evaluate their generators lazily
        unbound_kwargs = {
            k: v._evaluate__(sources)
            for k, v in self._child_vars_.items()
            if k not in bound_kwargs
        }
        if unbound_kwargs:
            yield from self._bind_unbound_kwargs_and_yield_results_(
                kwargs, unbound_kwargs, bound_kwargs
            )
        else:
            if self._predicate_type_ == PredicateType.SubClassOfPredicate:
                # Evaluate predicate directly to boolean without further wrapping
                res_bool = self._type_(
                    **{k: hv.value for k, hv in bound_kwargs.items()}
                )()
                yield from self._process_output_and_update_values_(res_bool, **kwargs)
            else:
                instance = self._type_(
                    **{k: hv.value for k, hv in bound_kwargs.items()}
                )
                yield from self._process_output_and_update_values_(instance, **kwargs)

    def _bind_unbound_kwargs_and_yield_results_(
        self,
        kwargs: Dict[str, Dict[int, HashedValue]],
        unbound_kwargs: Dict[str, Iterable],
        bound_kwargs: Dict[str, HashedValue],
    ):
        for extra_kwargs in generate_combinations(unbound_kwargs):
            # Avoid mutating the shared kwargs dict; work on a shallow copy
            merged_kwargs = dict(kwargs)
            merged_kwargs.update(extra_kwargs)
            # Update unwrapped hashed args from the delta only
            for k, v in extra_kwargs.items():
                bound_kwargs[k] = v[self._child_vars_[k]._id_]
            instance = self._type_(**{k: hv.value for k, hv in bound_kwargs.items()})
            yield from self._process_output_and_update_values_(
                instance, **merged_kwargs
            )

    def _search_and_yield_from_cache_(self, kwargs: Optional[Dict] = None):
        unwrapped_hashed_kwargs = None
        if kwargs and self._is_indexed_:
            unwrapped_hashed_kwargs = {
                k: v[self._child_vars_[k]._id_] for k, v in kwargs.items()
            }
        for _, value in yield_class_values_from_cache(
            self._cache_,
            self._type_,
            unwrapped_hashed_kwargs,
            from_index=self._is_indexed_,
        ):
            yield from self._process_output_and_update_values_(value.value, **kwargs)

    @property
    def _cache_values_(self):
        for _, value in yield_class_values_from_cache(
            self._cache_, self._type_, from_index=self._is_indexed_
        ):
            yield value

    @property
    def _cache_keys_(self) -> List[Type]:
        """
        Get the cache keys for the given class which are its subclasses and itself.
        """
        return get_cache_keys_for_class_(self._cache_, self._type_)

    def _process_output_and_update_values_(
        self, function_output: Any, **kwargs
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Process the output of the predicate/variable and get the results.

        :param function_output: The output of the predicate.
        :param kwargs: The keyword arguments of the predicate/variable.
        :return: The results' dictionary.
        """
        # Compute truth considering inversion
        result_truthy = bool(function_output)
        self._is_false_ = result_truthy if self._invert_ else not result_truthy

        if self._yield_when_false_ or not self._is_false_:
            if isinstance(function_output, HashedValue):
                hv = function_output
            else:
                hv = HashedValue(function_output)

            if not kwargs:
                yield {self._id_: hv}
                return

            # kwargs is a mapping from name -> {var_id: HashedValue};
            # we need a single dict {var_id: HashedValue
            values = {self._id_: hv}
            for d in kwargs.values():
                values.update(d)
            yield values

    @property
    def _name_(self):
        return self._name__

    @classmethod
    def _from_domain_(
        cls, iterable, clazz: Optional[Type] = None, name: Optional[str] = None
    ) -> Variable:
        if not isinstance(iterable, SymbolicExpression) and not is_iterable(iterable):
            iterable = HashedIterable([iterable])
        if not clazz:
            clazz = type(next(iter(iterable)))
        if name is None:
            name = clazz.__name__
        return Variable(name, clazz, _domain_source_=From(iterable))

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


@dataclass(eq=False)
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
        super().__init__(name, type_, _domain_source_=From(data))

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
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        self._yield_when_false_ = yield_when_false
        self._child_._eval_parent_ = self
        if self._id_ in sources:
            yield sources
            return
        child_val = self._child_._evaluate__(
            sources, yield_when_false=self._yield_when_false_
        )
        for child_v in child_val:
            for v in self._apply_mapping_(child_v[self._child_._id_]):
                values = copy(child_v)
                if (not self._invert_ and v.value) or (self._invert_ and not v.value):
                    self._is_false_ = False
                else:
                    self._is_false_ = True
                if self._yield_when_false_ or not self._is_false_:
                    values[self._id_] = v
                    yield values

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
        return SymbolGraph().type_graph.get_wrapped_class(self._type_)

    @cached_property
    def _type_(self):
        if self._child_wrapped_cls_:
            return self._wrapped_field_.type_endpoint
        else:
            return WrappedField(
                WrappedClass(self._child_type_),
                [f for f in fields(self._child_type_) if f.name == self._attr_name_][0],
            ).type_endpoint

    @cached_property
    def _wrapped_field_(self):
        return self._child_wrapped_cls_._wrapped_field_name_map_[self._attr_name_]

    @cached_property
    def _child_wrapped_cls_(self):
        return SymbolGraph().type_graph.get_wrapped_class(self._child_type_)

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
        inner = value.value
        # Treat non-iterables as singletons
        if not is_iterable(inner):
            inner_iter = [inner]
        else:
            inner_iter = inner
        for inner_v in inner_iter:
            yield HashedValue(inner_v)

    @property
    def _name_(self):
        return f"Flatten({self._child_._name_})"


@dataclass(eq=False)
class Concatenate(CanBehaveLikeAVariable[T]):
    _child_: CanBehaveLikeAVariable[T]
    _invert_: bool = field(init=False, default=False)

    def __post_init__(self):
        super().__post_init__()
        self._var_ = self

    def _evaluate__(
        self, sources: Optional[Dict[int, HashedValue]] = None
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}
        if self._id_ in sources:
            yield sources
            return
        all_values = defaultdict(list)
        for child_v in self._child_._evaluate__(sources):
            child_v = copy(child_v)
            for id_, val in child_v.items():
                if id_ == self._child_._id_:
                    child_v_unwrapped = val.value
                    if not is_iterable(child_v_unwrapped):
                        child_v_unwrapped = [child_v_unwrapped]
                    all_values[self._id_].extend(child_v_unwrapped)
                all_values[id_].append(val)
            for s_id, s_val in sources.items():
                all_values[s_id].append(s_val)
        yield {k: HashedValue(v) for k, v in all_values.items()}

    @property
    def _name_(self):
        return f"{self.__class__.__name__}({self._child_._name_})"

    @property
    @lru_cache(maxsize=None)
    def _all_variable_instances_(self) -> List[Variable]:
        return self._child_._all_variable_instances_


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
        entered = False
        for output, is_false in cache.retrieve(variables_sources):
            entered = True
            self._is_false_ = is_false
            cache_match_count.values[self._node_.name] += 1
            if is_false and self._is_duplicate_output_(output):
                continue
            yield output
        if not entered:
            cache_match_count.values[self._node_.name] += 1
        cache_enter_count.values[self._node_.name] = cache.enter_count
        cache_search_count.values[self._node_.name] = cache.search_count

    def yield_from_cache(
        self, variables_sources, cache: IndexedCache
    ) -> Iterable[Tuple[Dict[int, HashedValue], bool]]:
        entered = False
        for output, is_false in cache.retrieve(variables_sources):
            entered = True
            cache_match_count.values[self._node_.name] += 1
            yield output, is_false
        if not entered:
            cache_match_count.values[self._node_.name] += 1
        cache_enter_count.values[self._node_.name] = cache.enter_count
        cache_search_count.values[self._node_.name] = cache.search_count

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
    def _required_variables_from_child_(
        self, child: Optional[SymbolicExpression] = None, when_true: bool = True
    ):
        if not child:
            child = self.left
        required_vars = HashedIterable()
        if child is self.left:
            required_vars.update(self.right._unique_variables_)
        if when_true or (when_true is None):
            for conc in self._conclusion_:
                required_vars.update(conc._unique_variables_)
        if self._parent_:
            required_vars.update(
                self._parent_._required_variables_from_child_(self, when_true)
            )
        return required_vars


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
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}

        # Always reset per evaluation
        self.solution_set = []

        var_val_index = 0

        for var_val in self.variable._evaluate__(sources):
            ctx = {**sources, **var_val}
            current = []

            # Evaluate the condition under this particular universal value
            for condition_val in self.condition._evaluate__(ctx):
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
    ) -> Iterable[Dict[int, HashedValue]]:
        sources = sources or {}

        for var_val in self.variable._evaluate__(sources):
            ctx = {**sources, **var_val}

            # Evaluate the condition under this particular universal value
            for condition_val in self.condition._evaluate__(ctx):
                if self.condition._is_false_:
                    continue
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
        self._yield_when_false_ = yield_when_false

        if self._id_ in sources:
            yield sources
            return

        if is_caching_enabled():
            # Use exact fast-path before coverage check to avoid trie walk when fully bound
            if self._cache_.exact_contains(sources) or self._cache_.check(sources):
                yield from self.yield_final_output_from_cache(sources)
                return

        first_operand, second_operand = self.get_first_second_operands(sources)
        first_operand._eval_parent_ = self
        second_operand._eval_parent_ = self
        operand_value_map = {
            first_operand._id_: HashedValue(False),
            second_operand._id_: HashedValue(False),
        }
        first_values = first_operand._evaluate__(sources)
        for first_value in first_values:
            first_value.update(sources)
            operand_value_map[first_operand._id_] = first_value[first_operand._id_]
            second_values = second_operand._evaluate__(first_value)
            for second_value in second_values:
                operand_value_map[second_operand._id_] = second_value[
                    second_operand._id_
                ]
                res = self.apply_operation(operand_value_map)
                self._is_false_ = not res
                if res or self._yield_when_false_:
                    values = copy(first_value)
                    values.update(second_value)
                    values.update(operand_value_map)
                    values[self._id_] = HashedValue(res)
                    self.update_cache(values)
                    yield values

    def apply_operation(self, operand_values: Dict[int, HashedValue]):
        return self.operation(
            operand_values[self.left._id_].value, operand_values[self.right._id_].value
        )

    def get_first_second_operands(
        self, sources: Dict[int, HashedValue]
    ) -> Tuple[SymbolicExpression, SymbolicExpression]:
        if sources and any(
            v.value._var_._id_ in sources for v in self.right._unique_variables_
        ):
            return self.right, self.left
        else:
            return self.left, self.right

    def get_result_domain(
        self, operand_value_map: Dict[CanBehaveLikeAVariable, HashedValue]
    ) -> HashedIterable:
        left_leaf_value = self.left._var_._domain_[operand_value_map[self.left].id_]
        right_leaf_value = self.right._var_._domain_[operand_value_map[self.right].id_]
        return HashedIterable(
            values={
                self.left._var_._id_: left_leaf_value,
                self.right._var_._id_: right_leaf_value,
            }
        )

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
    ) -> Iterable[Dict[int, HashedValue]]:
        # init an empty source if none is provided
        sources = sources or {}
        self._yield_when_false_ = yield_when_false

        # constrain left values by available sources
        left_prev = self.left._eval_parent_
        self.left._eval_parent_ = self
        try:
            left_values = self.left._evaluate__(
                sources, yield_when_false=self._yield_when_false_
            )
            for left_value in left_values:
                left_value.update(sources)
                if self._yield_when_false_ and self.left._is_false_:
                    self._is_false_ = True
                    if self._is_duplicate_output_(left_value):
                        continue
                    yield left_value
                    continue

                if (
                    is_caching_enabled()
                    and not in_symbolic_mode(EQLMode.Rule)
                    and self.right_cache.cache
                ):
                    # Prefer exact fast-path to avoid trie walk when a complete key tuple is present
                    if self.right_cache.exact_contains(left_value):
                        for _out in self.yield_final_output_from_cache(
                            left_value, self.right_cache
                        ):
                            yield _out
                        continue
                    if self.right_cache.check(left_value):
                        _yielded_any = False
                        for _out in self.yield_final_output_from_cache(
                            left_value, self.right_cache
                        ):
                            _yielded_any = True
                            yield _out
                        if _yielded_any:
                            continue

                # constrain right values by available sources
                right_prev = self.right._eval_parent_
                self.right._eval_parent_ = self
                try:
                    right_values = self.right._evaluate__(
                        left_value, yield_when_false=self._yield_when_false_
                    )

                    # For the found left value, find all right values,
                    # and yield the (left, right) results found.
                    for right_value in right_values:
                        output = copy(right_value)
                        output.update(left_value)
                        self._is_false_ = self.right._is_false_
                        self.update_cache(right_value, self.right_cache)
                        yield output
                finally:
                    self.right._eval_parent_ = right_prev
        finally:
            self.left._eval_parent_ = left_prev


@dataclass(eq=False)
class OR(LogicalOperator, ABC):
    """
    A symbolic single choice operation that can be used to choose between multiple symbolic expressions.
    """

    @lru_cache(maxsize=None)
    def _required_variables_from_child_(
        self,
        child: Optional[SymbolicExpression] = None,
        when_true: Optional[bool] = None,
    ):
        if not child:
            child = self.left
        required_vars = HashedIterable()
        when_false = not when_true if when_true is not None else None
        if child is self.left:
            if when_false or (when_false is None):
                required_vars.update(self.right._unique_variables_)
                when_iam = None
            else:
                when_iam = True
            if self._parent_:
                required_vars.update(
                    self._parent_._required_variables_from_child_(self, when_iam)
                )
            if when_true or (when_true is None):
                for conc in self.left._conclusion_:
                    required_vars.update(conc._unique_variables_)
        elif child is self.right:
            if when_true or (when_true is None):
                for conc in self.right._conclusion_:
                    required_vars.update(conc._unique_variables_)
            if self._parent_:
                required_vars.update(
                    self._parent_._required_variables_from_child_(self, when_true)
                )
        return required_vars


@dataclass(eq=False)
class Union(OR):
    left_cache: IndexedCache = field(default_factory=IndexedCache, init=False)
    left_evaluated: bool = field(default=False, init=False)
    right_evaluated: bool = field(default=False, init=False)

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        # init an empty source if none is provided
        sources = sources or {}
        self._yield_when_false_ = yield_when_false

        if is_caching_enabled() and self._cache_.check(sources):
            yield from self.yield_final_output_from_cache(sources)
            return

        # constrain left values by available sources
        left_prev = self.left._eval_parent_
        self.left._eval_parent_ = self
        try:
            left_values = self.left._evaluate__(
                sources, yield_when_false=self._yield_when_false_
            )

            for left_value in left_values:
                output = copy(sources)
                output.update(left_value)
                self.left_evaluated = True
                if self.left._is_false_:
                    if self._yield_when_false_:
                        yield from self.evaluate_right(output)
                    continue
                if self._is_duplicate_output_(output):
                    continue
                self.update_cache(output, self._cache_)
                yield output
        finally:
            self.left._eval_parent_ = left_prev
        self.left_evaluated = False
        yield from self.evaluate_right(sources)

    def evaluate_right(
        self, sources: Optional[Dict[int, HashedValue]]
    ) -> Iterable[Dict[int, HashedValue]]:
        right_values = self.right._evaluate__(
            sources, yield_when_false=self._yield_when_false_
        )
        # For the found left value, find all right values,
        # and yield the (left, right) results found.
        for right_value in right_values:
            sources.update(right_value)
            if self._yield_when_false_ and self.left_evaluated:
                self._is_false_ = self.left._is_false_ and self.right._is_false_
            else:
                self._is_false_ = False
            if not self._is_false_:
                if self._is_duplicate_output_(sources):
                    continue
            self.right_evaluated = True
            self.update_cache(sources, self._cache_)
            yield sources


@dataclass(eq=False)
class ElseIf(OR):
    """
    A symbolic single choice operation that can be used to choose between multiple symbolic expressions.
    """

    def _evaluate__(
        self,
        sources: Optional[Dict[int, HashedValue]] = None,
        yield_when_false: bool = False,
    ) -> Iterable[Dict[int, HashedValue]]:
        """
        Constrain the symbolic expression based on the indices of the operands.
        This method overrides the base class method to handle ElseIf logic.
        """
        # init an empty source if none is provided
        sources = sources or {}
        self._yield_when_false_ = yield_when_false

        # constrain left values by available sources
        left_prev = self.left._eval_parent_
        self.left._eval_parent_ = self
        try:
            # Force yield_when_false=True for the left branch to preserve else-if semantics
            left_values = self.left._evaluate__(sources, yield_when_false=True)
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
                    right_prev = self.right._eval_parent_
                    self.right._eval_parent_ = self
                    try:
                        right_values = self.right._evaluate__(
                            left_value, yield_when_false=self._yield_when_false_
                        )
                        for right_value in right_values:
                            self._is_false_ = self.right._is_false_
                            output = copy(left_value)
                            output.update(right_value)
                            if self._is_false_ and not self._yield_when_false_:
                                continue
                            if not self._is_false_:
                                if self._is_duplicate_output_(output):
                                    continue
                            self.update_cache(right_value, self.right_cache)
                            yield output
                    finally:
                        self.right._eval_parent_ = right_prev
                else:
                    self._is_false_ = False
                    yield left_value
            # If left produced no values at all, evaluate right against sources
            if not any_left:
                right_prev = self.right._eval_parent_
                self.right._eval_parent_ = self
                try:
                    right_values = self.right._evaluate__(
                        sources, yield_when_false=self._yield_when_false_
                    )
                    for right_value in right_values:
                        self._is_false_ = self.right._is_false_
                        if self._is_false_ and not self._yield_when_false_:
                            continue
                        self.update_cache(right_value, self.right_cache)
                        yield right_value
                finally:
                    self.right._eval_parent_ = right_prev
        finally:
            self.left._eval_parent_ = left_prev


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
