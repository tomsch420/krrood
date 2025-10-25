from __future__ import annotations

"""
EQL-to-Python compiler.

This module provides a small compiler that translates an EQL query graph
(ResultQuantifier and its subtree) into an equivalent, efficient Python
generator function. The produced code:

- Iterates concrete instances directly from the internal cache
  (mirrors how Variables get their domain), including subclasses.
- Lowers Flatten/Attribute chains into nested for-loops and assignments.
- Lowers basic predicates and comparators into native Python if-conditions.

Scope
-----
The compiler focuses on the most common EQL constructs used in LUBM queries:

- ResultQuantifier over Entity or SetOf
- Variable domains
- Attribute access and Flatten
- Comparators (==, !=, <, <=, >, >=, "in")
- Predicates, with a fast-path for HasType which compiles to isinstance()

For other user-defined Predicates, it falls back to constructing the predicate
class and calling it in Python. This keeps the interface general while keeping
critical paths fast.
"""

from dataclasses import dataclass, field
import builtins
import keyword
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union, Set


class CodegenError(Exception):
    """
    Raised when the EQL-to-Python code generation encounters an unrecoverable
    situation. The current compiler strives to avoid raising this exception by
    falling back to generic code paths, but it exists to make the interface
    harder to misuse and future-proof against unsupported constructs.
    """
    pass


@dataclass(frozen=True)
class PrecomputeFilter:
    """
    Describes a simple equality filter for precomputation.

    :ivar path: Attribute path starting from a variable (e.g., ("person", "uri")).
    :ivar value: Constant value to compare to for early pruning.
    """

    path: Tuple[str, ...]
    value: object


@dataclass
class PrecomputeEntry:
    """
    Holds planned precomputations for an independent variable.

    :ivar var: The variable for which to precompute data.
    :ivar attr_paths: A set of attribute paths whose items should be materialized
                      into membership sets for faster "in" checks.
    :ivar filters: A list of literal equality filters to prune the variable's domain
                   during precomputation.
    """

    var: 'Variable'
    attr_paths: Set[Tuple[str, ...]] = field(default_factory=set)
    filters: List[PrecomputeFilter] = field(default_factory=list)

from .cache_data import get_cache_keys_for_class_, yield_class_values_from_cache
from .predicate import Predicate, HasType, Symbol
from .symbolic import (
    Attribute,
    CanBehaveLikeAVariable,
    Comparator,
    DomainMapping,
    Flatten,
    QueryObjectDescriptor,
    ResultQuantifier,
    SetOf,
    Variable,
    Literal,
)


@dataclass
class CompiledQuery:
    """
    Holds the generated Python source and the compiled function.

    :ivar source: The generated Python source code as a string.
    :ivar function: A zero-argument callable that returns a generator over results.
    """

    source: str
    function: Callable[[], Iterable]


@dataclass
class _Env:
    """
    Compilation environment that tracks bindings and names.

    :ivar names: Mapping from expression identity to bound Python variable name.
    :ivar used_names: Set of already used variable names to preserve uniqueness.
    :ivar lines: Accumulated source code lines.
    :ivar indent: Current indentation level.
    :ivar tmp_counter: Counter for generating temporary variable names.
    """

    names: Dict[int, str] = field(default_factory=dict)
    used_names: Set[str] = field(default_factory=set)
    lines: List[str] = field(default_factory=list)
    indent: int = 0
    tmp_counter: int = 0

    def add(self, line: str) -> None:
        self.lines.append("    " * self.indent + line)

    def new_tmp(self, base: str = "tmp") -> str:
        while True:
            name = f"{base}_{self.tmp_counter}"
            self.tmp_counter += 1
            if name not in self.used_names:
                self.used_names.add(name)
                return name

    @staticmethod
    def _to_snake(name: str) -> str:
        out = []
        prev_lower = False
        for ch in name:
            if ch.isupper() and prev_lower:
                out.append('_')
            out.append(ch.lower())
            prev_lower = ch.islower()
        return ''.join(out)

    def bind_name_for(self, node: CanBehaveLikeAVariable, suggested: Optional[str]) -> str:
        node_id = id(node)
        if node_id in self.names:
            return self.names[node_id]
        base_raw = (suggested or getattr(getattr(node, "_name__", None), "strip", lambda: "")()).strip() or node.__class__.__name__.lower()
        base_raw = base_raw.replace(".", "_")
        base = self._to_snake(base_raw)
        # Avoid Python keywords and builtins like 'str', 'list', etc.
        if keyword.iskeyword(base) or base in dir(builtins):
            base = f"{base}_value"
        name = base
        idx = 1
        while name in self.used_names or not name.isidentifier() or keyword.iskeyword(name) or name in dir(builtins):
            name = f"{base}_{idx}"
            idx += 1
        self.used_names.add(name)
        self.names[node_id] = name
        return name


class _Codegen:
    """
    Core compiler that turns a ResultQuantifier EQL tree into Python code.
    """

    def __init__(self, q: ResultQuantifier):
        self.q = q
        self.env = _Env()
        # Mapping for precomputed membership sets: (var_id, attr_path_tuple) -> set_var_name
        self._precomputed_sets: Dict[Tuple[int, Tuple[str, ...]], str] = {}
        # Condition nodes that were consumed during precomputation and must not be emitted again
        self._consumed_conditions: Set[int] = set()

    def compile(self) -> CompiledQuery:
        env = self.env
        env.add("# Auto-generated from EQL query graph")
        env.add("from typing import Iterable")
        env.add("from krrood.entity_query_language.symbolic import Variable")
        env.add(
            "from krrood.entity_query_language.cache_data import get_cache_keys_for_class_, yield_class_values_from_cache"
        )
        env.add("from krrood.entity_query_language.predicate import HasType")
        # Import model classes used in LUBM experiments to ensure class names are available
        env.add("from krrood.experiments.lubm_with_predicates import *")
        env.add("")
        env.add("def _iterate_instances(cls):")
        env.indent += 1
        env.add("cache = Variable._cache_")
        env.add("keys = get_cache_keys_for_class_(cache, cls)")
        env.add("for t in keys:")
        env.indent += 1
        env.add("for _, hv in cache[t].retrieve(from_index=False):")
        env.indent += 1
        env.add("yield hv.value")
        env.indent -= 1
        env.indent -= 1
        env.indent -= 1
        env.add("")
        env.add("def compiled_query() -> Iterable:")
        env.indent += 1
        # A set used to deduplicate SetOf outputs when necessary
        env.add("_seen = set()")
        self._emit_body(self.q._child_)
        env.indent -= 1
        source = "\n".join(env.lines)
        scope: Dict[str, object] = {}
        # Provide model classes referenced in the query into the scope
        for cls in self._referenced_classes():
            scope[cls.__name__] = cls
        exec(source, scope, scope)
        return CompiledQuery(source=source, function=scope["compiled_query"]) 

    def _referenced_classes(self) -> List[type]:
        """
        Collect Python classes referenced by the compiled code so we can
        inject them into the exec scope. This includes:
        - Variable types used as domains
        - Classes used in isinstance checks (e.g., HasType.types_)
        - Predicate classes used in fallback emission
        """
        classes: Dict[str, type] = {}

        # All Variable instances in the query
        try:
            variables = self.q._all_variable_instances_
        except Exception:
            variables = []
        for v in variables:
            t = getattr(v, "_type_", None)
            if isinstance(t, type):
                classes[t.__name__] = t

        # Traverse conditions to find predicate and type references
        visited: set[int] = set()
        def visit(node):
            if node is None:
                return
            nid = id(node)
            if nid in visited:
                return
            visited.add(nid)
            # If node is a Variable of a Predicate class, include that class
            if isinstance(node, Variable):
                t = getattr(node, "_type_", None)
                if isinstance(t, type):
                    classes[t.__name__] = t
                # Inspect kwargs for type references (e.g., HasType.types_)
                for val in getattr(node, "_kwargs_", {}).values():
                    if isinstance(val, type):
                        classes[val.__name__] = val
            # Recurse children when available
            for ch in getattr(node, "_children_", []) or []:
                visit(ch)
            # Domain mappings and attributes: descend to child
            if hasattr(node, "_child_"):
                visit(getattr(node, "_child_"))
        visit(self.q._child_)
        return list(classes.values())

    def _collect_hoistable_variables(self, cond, selected: List[CanBehaveLikeAVariable]) -> List[Variable]:
        """
        Collect variables that appear only in the condition tree and are independent
        of the selected base variables. Those variables can be bound (and any loops
        for them emitted) once outside the main selected-variable loops.
        NOTE: This helper is retained for reference but not used to emit loops directly.
        """
        # Roots of selected expressions (e.g., x in set_of((x, ...), ...))
        selected_roots = {id(v) for v in self._selected_base_variables(selected)}
        hoist: List[Variable] = []
        seen_vars: Set[int] = set()
        visited: Set[int] = set()

        def maybe_add(var: Variable):
            # Only non-predicate symbol variables that are not already selected roots
            t = getattr(var, "_type_", None)
            if not (isinstance(t, type) and issubclass(t, Symbol)):
                return
            if issubclass(t, Predicate) or getattr(var, "_predicate_type_", None) is not None:
                return
            if id(var) in selected_roots:
                return
            if id(var) in seen_vars:
                return
            seen_vars.add(id(var))
            hoist.append(var)

        def visit(node):
            if node is None:
                return
            nid = id(node)
            if nid in visited:
                return
            visited.add(nid)
            # Explicitly handle Comparator to traverse left/right
            if isinstance(node, Comparator):
                visit(node.left)
                visit(node.right)
                return
            if isinstance(node, Variable):
                maybe_add(node)
                # Traverse into kwargs to find nested expressions
                for val in getattr(node, "_kwargs_", {}).values():
                    if isinstance(val, CanBehaveLikeAVariable):
                        visit(val)
                return
            # Recurse generic children
            for ch in getattr(node, "_children_", []) or []:
                visit(ch)
            if hasattr(node, "_child_"):
                visit(getattr(node, "_child_"))

        visit(cond)
        return hoist

    def _extract_var_and_attr_path(self, expr: CanBehaveLikeAVariable) -> Optional[Tuple[Variable, Tuple[str, ...]]]:
        """
        If the expression is an Attribute chain rooted at a Variable (possibly wrapped),
        return (var, attr_path). Unwrap wrappers like ResultQuantifier (the/an) and
        DomainMapping to reach the base Variable.
        Otherwise return None.
        """
        path: List[str] = []
        node = expr
        # Collect attribute names while walking up
        while isinstance(node, Attribute):
            path.append(node._attr_name_)
            node = node._child_
        # Unwrap common wrappers to reach the base variable
        unwrapped_once = True
        while unwrapped_once:
            unwrapped_once = False
            if isinstance(node, ResultQuantifier):
                desc = node._child_
                try:
                    selected = getattr(desc, "selected_variables", None) or []
                    if selected:
                        node = selected[0]
                        unwrapped_once = True
                        continue
                except Exception:
                    pass
            # Unwrap query descriptors like Entity/SetOf to reach their selected variables
            from .symbolic import QueryObjectDescriptor
            if isinstance(node, QueryObjectDescriptor):
                selected = getattr(node, "selected_variables", None) or []
                if selected:
                    node = selected[0]
                    unwrapped_once = True
                    continue
            if isinstance(node, DomainMapping):
                node = node._child_
                unwrapped_once = True
                continue
        if isinstance(node, Variable):
            path.reverse()
            return node, tuple(path)
        return None

    def _is_independent_symbol_var(self, var: Variable, selected: List[CanBehaveLikeAVariable]) -> bool:
        roots = {id(v) for v in self._selected_base_variables(selected)}
        if id(var) in roots:
            return False
        t = getattr(var, "_type_", None)
        return isinstance(t, type) and issubclass(t, Symbol) and not issubclass(t, Predicate) and getattr(var, "_predicate_type_", None) is None

    def _plan_precomputations(self, cond, selected: List[CanBehaveLikeAVariable]):
        """
        Analyze the condition tree and plan precomputations for independent variables.

        Returns a mapping from variable identity to a PrecomputeEntry with:
        - attr_paths to materialize into membership sets
        - literal equality filters to prune the variable's domain during precompute

        We deliberately avoid any side effects here other than marking conditions
        as consumed when they are fully subsumed by the precomputation plan.
        """
        plan: Dict[int, PrecomputeEntry] = {}
        visited: Set[int] = set()

        def ensure_entry(v: Variable) -> PrecomputeEntry:
            vid = id(v)
            if vid not in plan:
                plan[vid] = PrecomputeEntry(var=v)
                try:
                    for k, val in (getattr(v, "_kwargs_", {}) or {}).items():
                        if not isinstance(val, CanBehaveLikeAVariable):
                            plan[vid].filters.append(PrecomputeFilter((k,), val))
                except Exception:
                    pass
            return plan[vid]

        def visit(node):
            if node is None:
                return
            nid = id(node)
            if nid in visited:
                return
            visited.add(nid)
            if isinstance(node, Comparator):
                op = node._name_
                if op == "contains":
                    res = self._extract_var_and_attr_path(node.left) if isinstance(node.left, CanBehaveLikeAVariable) else None
                    if res is not None:
                        var, path = res
                        if self._is_independent_symbol_var(var, selected):
                            entry = ensure_entry(var)
                            entry.attr_paths.add(path)
                            self._gather_literal_filters_for_var(node.left, var, entry)
                    visit(node.right)
                    return
                if op == "==":
                    left_res = self._extract_var_and_attr_path(node.left) if isinstance(node.left, CanBehaveLikeAVariable) else None
                    right_is_lit = not isinstance(node.right, CanBehaveLikeAVariable) or isinstance(node.right, Literal)
                    right_val = node.right._domain_source_.domain[0] if isinstance(node.right, Literal) else node.right
                    if left_res is None and isinstance(node.right, CanBehaveLikeAVariable):
                        right_res = self._extract_var_and_attr_path(node.right)
                        left_is_lit = not isinstance(node.left, CanBehaveLikeAVariable)
                        if right_res is not None and left_is_lit:
                            left_val = node.left
                            var, path = right_res
                            if self._is_independent_symbol_var(var, selected):
                                ensure_entry(var).filters.append(PrecomputeFilter(path, left_val))
                                self._consumed_conditions.add(nid)
                            return
                    if left_res is not None and right_is_lit:
                        var, path = left_res
                        if self._is_independent_symbol_var(var, selected):
                            ensure_entry(var).filters.append(PrecomputeFilter(path, right_val))
                            self._consumed_conditions.add(nid)
                        return
                visit(node.left)
                visit(node.right)
                return
            for ch in getattr(node, "_children_", []) or []:
                visit(ch)
            if hasattr(node, "_child_"):
                visit(getattr(node, "_child_"))
            if isinstance(node, Variable):
                for val in getattr(node, "_kwargs_", {}).values():
                    if isinstance(val, CanBehaveLikeAVariable):
                        visit(val)

        visit(cond)
        return plan

    def _gather_literal_filters_for_var(self, subtree, target_var: 'Variable', entry: PrecomputeEntry) -> None:
        """Collect literal equality filters under subtree for the given variable."""
        def walk(n):
            if n is None:
                return
            if isinstance(n, Comparator) and n._name_ == "==":
                lres = self._extract_var_and_attr_path(n.left) if isinstance(n.left, CanBehaveLikeAVariable) else None
                rres = self._extract_var_and_attr_path(n.right) if isinstance(n.right, CanBehaveLikeAVariable) else None
                var_cls = getattr(target_var, "_type_", None)
                if isinstance(n.right, Literal):
                    right_is_lit = True
                    right_val = n.right._domain_source_.domain[0]
                else:
                    right_is_lit = not isinstance(n.right, CanBehaveLikeAVariable)
                    right_val = n.right
                if isinstance(n.left, Literal):
                    left_is_lit = True
                    left_val = n.left._domain_source_.domain[0]
                else:
                    left_is_lit = not isinstance(n.left, CanBehaveLikeAVariable)
                    left_val = n.left
                if lres is not None and getattr(lres[0], "_type_", None) is var_cls and right_is_lit:
                    entry.filters.append(PrecomputeFilter(lres[1], right_val))
                    self._consumed_conditions.add(id(n))
                    return
                if rres is not None and getattr(rres[0], "_type_", None) is var_cls and left_is_lit:
                    entry.filters.append(PrecomputeFilter(rres[1], left_val))
                    self._consumed_conditions.add(id(n))
                    return
            for ch in getattr(n, "_children_", []) or []:
                walk(ch)
            if hasattr(n, "_child_"):
                walk(getattr(n, "_child_"))
        walk(subtree)

    def _emit_precomputations(self, plan: Dict[int, PrecomputeEntry]) -> None:
        """Emit Python code for precomputations according to the plan."""
        for entry in plan.values():
            var: Variable = entry.var
            if not entry.attr_paths:
                continue
            cls = getattr(var, "_type_", None)
            if not (isinstance(cls, type) and issubclass(cls, Symbol)):
                continue
            set_names = self._allocate_precompute_sets(var, entry.attr_paths)
            var_tmp = self._begin_domain_loop(var, cls)
            unique_filters = self._dedupe_precompute_filters(entry.filters)
            self._emit_filter_checks(var_tmp, unique_filters)
            for path, set_name in set_names.items():
                self._emit_collect_items_into_set(var_tmp, path, set_name)
            self.env.indent -= 1

    def _allocate_precompute_sets(self, var: 'Variable', paths: Set[Tuple[str, ...]]) -> Dict[Tuple[str, ...], str]:
        """Allocate set variables for each attribute path and register them."""
        set_names: Dict[Tuple[str, ...], str] = {}
        for path in paths:
            set_name = self.env.new_tmp("pre_set")
            self.env.add(f"{set_name} = set()")
            set_names[path] = set_name
            self._precomputed_sets[(id(var), path)] = set_name
        return set_names

    def _begin_domain_loop(self, var: 'Variable', cls: type) -> str:
        """Begin a loop over all instances of the variable's class and return loop var name."""
        base_raw = (getattr(var, "_name__", None) or var.__class__.__name__).replace(".", "_")
        base = self.env._to_snake(base_raw)
        var_tmp = self.env.new_tmp(base)
        self.env.add(f"for {var_tmp} in _iterate_instances({cls.__name__}):")
        self.env.indent += 1
        return var_tmp

    def _dedupe_precompute_filters(self, filters: List[PrecomputeFilter]) -> List[PrecomputeFilter]:
        """Remove duplicate filters while preserving order."""
        unique: List[PrecomputeFilter] = []
        seen: Set[Tuple[Tuple[str, ...], object]] = set()
        for f in filters:
            try:
                key = (f.path, f.value)
                hash(key)
            except Exception:
                key = (f.path, repr(f.value))  # type: ignore[assignment]
            if key in seen:
                continue
            seen.add(key)  # type: ignore[arg-type]
            unique.append(f)
        return unique

    def _emit_filter_checks(self, var_tmp: str, filters: List[PrecomputeFilter]) -> None:
        """Emit early-continue checks for precompute filters."""
        for f in filters:
            attr_expr = var_tmp
            for a in f.path:
                attr_expr = f"{attr_expr}.{a}"
            const_repr = repr(f.value)
            self.env.add(f"if ({attr_expr}) != ({const_repr}):")
            self.env.indent += 1
            self.env.add("continue")
            self.env.indent -= 1

    def _emit_collect_items_into_set(self, var_tmp: str, path: Tuple[str, ...], set_name: str) -> None:
        """Emit a loop that collects items from the given attribute path into the set."""
        items_expr = var_tmp
        for a in path:
            items_expr = f"{items_expr}.{a}"
        tmp_iter = self.env.new_tmp("_iter")
        item_tmp = self.env.new_tmp("item")
        self.env.add(f"{tmp_iter} = {items_expr}")
        self.env.add(f"{tmp_iter} = {tmp_iter} if hasattr({tmp_iter}, '__iter__') and not isinstance({tmp_iter}, (str, bytes)) else [{tmp_iter}]")
        self.env.add(f"for {item_tmp} in {tmp_iter}:")
        self.env.indent += 1
        self.env.add(f"{set_name}.add({item_tmp})")
        self.env.indent -= 1

    def _emit_body(self, descriptor: QueryObjectDescriptor) -> None:
        """
        Emit loops, conditions, and the final yield for the given descriptor.
        """
        selected = descriptor.selected_variables
        self._emit_plan_and_precompute(descriptor, selected)
        self._emit_bind_selected(selected)
        if descriptor._child_ is not None:
            self._emit_condition(descriptor._child_)
        self._emit_yield(descriptor, selected)

    def _emit_plan_and_precompute(self, descriptor: QueryObjectDescriptor, selected: List[CanBehaveLikeAVariable]) -> None:
        """Plan and emit precomputations, and create outer loops for base variables."""
        plan = self._plan_precomputations(descriptor._child_, selected)
        self._emit_precomputations(plan)
        for var in self._selected_base_variables(selected):
            self._bind(var)

    def _emit_bind_selected(self, selected: List[CanBehaveLikeAVariable]) -> None:
        """Bind selected expressions inside existing loops."""
        for sv in selected:
            self._bind(sv)

    def _emit_yield(self, descriptor: QueryObjectDescriptor, selected: List[CanBehaveLikeAVariable]) -> None:
        """Emit the appropriate yield depending on descriptor type."""
        if isinstance(descriptor, SetOf):
            items = ", ".join(self.env.names[id(v)] for v in selected)
            dm_names = [self.env.names[id(v)] for v in selected if isinstance(v, DomainMapping)]
            if dm_names:
                cond = " and ".join(dm_names)
                self.env.add(f"if not ({cond}):")
                self.env.indent += 1
                self.env.add("continue")
                self.env.indent -= 1
            key_var = self.env.new_tmp("key")
            self.env.add(f"{key_var} = ({items},)")
            self.env.add(f"if {key_var} in _seen:")
            self.env.indent += 1
            self.env.add("continue")
            self.env.indent -= 1
            self.env.add(f"_seen.add({key_var})")
            self.env.add(f"yield {key_var}")
        else:
            if selected:
                self.env.add(f"yield {self.env.names[id(selected[0])]}")
            else:
                self.env.add("yield None")

    def _selected_base_variables(self, selected: List[CanBehaveLikeAVariable]) -> List[Variable]:
        # Collect base Variables from selected expressions only (ignore conditions)
        roots: List[Variable] = []
        seen: Set[int] = set()
        def visit(expr: Optional[CanBehaveLikeAVariable]):
            if expr is None:
                return
            node = expr
            while isinstance(node, DomainMapping):
                node = node._child_
            if isinstance(node, Variable):
                # Exclude predicate variables
                cls = getattr(node, "_type_", None)
                if isinstance(cls, type) and not issubclass(cls, Predicate) and getattr(node, "_predicate_type_", None) is None:
                    if id(node) not in seen:
                        seen.add(id(node))
                        roots.append(node)
        for s in selected:
            visit(s)
        return roots

    def _bind(self, expr: CanBehaveLikeAVariable, suggested: Optional[str] = None) -> str:
        """Bind an expression to a Python variable name in the current scope."""
        node_id = id(expr)
        if node_id in self.env.names:
            return self.env.names[node_id]
        if isinstance(expr, Variable):
            return self._bind_variable(expr)
        if isinstance(expr, ResultQuantifier):
            return self._bind_result_quantifier(expr)
        if isinstance(expr, Attribute):
            return self._bind_attribute(expr)
        if isinstance(expr, Flatten):
            return self._bind_flatten(expr)
        if isinstance(expr, DomainMapping):
            return self._bind_domain_mapping(expr)
        return self._bind_constant(expr)

    def _bind_variable(self, expr: 'Variable') -> str:
        """Bind a Variable, emitting outer iteration when needed."""
        name = self.env.bind_name_for(expr, getattr(expr, "_name__", None))
        cls = expr._type_
        if isinstance(cls, type) and issubclass(cls, Symbol):
            self.env.add(f"for {name} in _iterate_instances({cls.__name__}):")
            self.env.indent += 1
            return name
        # Non-Symbol: try to bind from domain or iterate constants
        try:
            dom = getattr(expr, "_domain_source_", None)
            if dom is not None and hasattr(dom, "domain"):
                raw_vals = list(dom.domain)
                vals = [getattr(v, "value", v) for v in raw_vals]
                if len(vals) == 1:
                    self.env.add(f"{name} = {repr(vals[0])}")
                    return name
                if len(vals) > 1:
                    lst = ", ".join(repr(v) for v in vals)
                    self.env.add(f"for {name} in [{lst}]:")
                    self.env.indent += 1
                    return name
        except Exception:
            pass
        self.env.add(f"{name} = {repr(getattr(expr, '_name__', name))}")
        return name

    def _bind_result_quantifier(self, expr: 'ResultQuantifier') -> str:
        """Bind a ResultQuantifier by binding its selected variables and conditions."""
        descriptor = expr._child_
        for var in self._selected_base_variables(descriptor.selected_variables):
            self._bind(var)
        for sv in descriptor.selected_variables:
            self._bind(sv)
        if descriptor._child_ is not None:
            self._emit_condition(descriptor._child_)
        if descriptor.selected_variables:
            return self.env.names[id(descriptor.selected_variables[0])]
        name = self.env.new_tmp("val")
        self.env.add(f"{name} = None")
        return name

    def _bind_attribute(self, expr: 'Attribute') -> str:
        """Bind an Attribute by binding its parent and assigning the access."""
        parent_name = self._bind(expr._child_, None)
        name = self.env.bind_name_for(expr, f"{parent_name}_{expr._attr_name_}")
        self.env.add(f"{name} = {parent_name}.{expr._attr_name_}")
        return name

    def _bind_flatten(self, expr: 'Flatten') -> str:
        """Bind a Flatten by emitting a for-loop over the parent value."""
        parent_name = self._bind(expr._child_, None)
        name = self.env.bind_name_for(expr, self.env.new_tmp("flat"))
        tmp_iter = self.env.new_tmp("_iter")
        self.env.add(f"{tmp_iter} = {parent_name}")
        self.env.add(f"{tmp_iter} = {tmp_iter} if hasattr({tmp_iter}, '__iter__') and not isinstance({tmp_iter}, (str, bytes)) else [{tmp_iter}]")
        self.env.add(f"for {name} in {tmp_iter}:")
        self.env.indent += 1
        return name

    def _bind_domain_mapping(self, expr: 'DomainMapping') -> str:
        """Bind a DomainMapping by binding its child and assigning the value."""
        parent_name = self._bind(expr._child_, None)
        name = self.env.bind_name_for(expr, self.env.new_tmp("map"))
        self.env.add(f"{name} = {parent_name}")
        return name

    def _bind_constant(self, expr: object) -> str:
        """Bind a literal or constant expression via direct assignment."""
        name = self.env.bind_name_for(expr, self.env.new_tmp("val"))
        self.env.add(f"{name} = {repr(expr)}")
        return name

    def _emit_condition(self, cond) -> None:
        """Emit Python conditions for a condition node, delegating to helpers."""
        if cond is None or id(cond) in self._consumed_conditions:
            return
        if cond.__class__.__name__ == 'AND':
            self._emit_condition_and(cond)
            return
        if isinstance(cond, Comparator):
            self._emit_condition_comparator(cond)
            return
        if self._is_predicate_node(cond):
            self._emit_condition_predicate(cond)
            return
        if isinstance(cond, QueryObjectDescriptor):
            self._emit_condition_descriptor(cond)
            return
        self._emit_condition_truthy(cond)

    def _emit_condition_and(self, cond) -> None:
        """Emit a chain of conditions for an AND node."""
        for ch in cond._children_:
            self._emit_condition(ch)

    def _emit_condition_comparator(self, cond: 'Comparator') -> None:
        """Emit a comparator condition with contains optimization when possible."""
        if id(cond) in self._consumed_conditions:
            return
        op = cond._name_
        if op == "contains" and self._emit_contains_optimized(cond):
            return
        _, left_expr = self._compile_value(cond.left)
        _, right_expr = self._compile_value(cond.right)
        expr = f"({right_expr}) in ({left_expr})" if op == "contains" else f"({left_expr}) {op} ({right_expr})"
        self.env.add(f"if {expr}:")
        self.env.indent += 1

    def _emit_contains_optimized(self, cond: 'Comparator') -> bool:
        """Try to emit an optimized contains using a precomputed membership set."""
        if not isinstance(cond.left, CanBehaveLikeAVariable):
            return False
        res = self._extract_var_and_attr_path(cond.left)
        if res is None:
            return False
        var, path = res
        key = (id(var), path)
        if key not in self._precomputed_sets:
            return False
        _, right_expr = self._compile_value(cond.right)
        set_name = self._precomputed_sets[key]
        self.env.add(f"if ({right_expr}) in {set_name}:")
        self.env.indent += 1
        return True

    def _is_predicate_node(self, node) -> bool:
        """Return True if node is a predicate Variable."""
        return isinstance(node, CanBehaveLikeAVariable) and isinstance(getattr(node, "_type_", None), type) and issubclass(node._type_, Predicate)

    def _emit_condition_predicate(self, cond) -> None:
        """Emit predicate evaluation, using isinstance fast path for HasType."""
        kwargs = cond._kwargs_
        if issubclass(cond._type_, HasType) and 'variable' in kwargs and 'types_' in kwargs:
            _, var_expr = self._compile_value(kwargs['variable'])
            type_cls = kwargs['types_']
            self.env.add(f"if isinstance({var_expr}, {type_cls.__name__}):")
            self.env.indent += 1
            return
        bound_pairs = []
        for k, v in cond._kwargs_.items():
            _, ve = self._compile_value(v)
            bound_pairs.append(f"{k}={ve}")
        call_expr = f"{cond._type_.__name__}({', '.join(bound_pairs)})()"
        self.env.add(f"if {call_expr}:")
        self.env.indent += 1

    def _emit_condition_descriptor(self, cond: 'QueryObjectDescriptor') -> None:
        """Emit an any() check for a nested descriptor condition."""
        inner_fn = self.env.new_tmp("_inner_any")
        self.env.add(f"def {inner_fn}():")
        self.env.indent += 1
        self._emit_body(cond)
        self.env.indent -= 1
        self.env.add(f"if any({inner_fn}()):")
        self.env.indent += 1

    def _emit_condition_truthy(self, cond) -> None:
        """Fallback: evaluate truthiness of a compiled value."""
        _, expr = self._compile_value(cond)
        self.env.add(f"if {expr}:")
        self.env.indent += 1

    def _compile_value(self, expr: Union[CanBehaveLikeAVariable, object]) -> Tuple[str, str]:
        # Returns (name, python_expression) for expr; ensures necessary loops/assignments emitted
        if isinstance(expr, CanBehaveLikeAVariable):
            # If expr includes a Flatten, ensure loop is emitted by binding
            name = self._bind(expr)
            # For simple attribute/variable, we can reference the bound name
            # For Attribute chains, the bound name already points to the value
            return name, name
        # Literal value
        return None, repr(expr)


def compile_to_python(query: ResultQuantifier) -> CompiledQuery:
    """
    Compile an EQL query graph to a Python generator function.

    :param query: The EQL ResultQuantifier to compile.
    :return: CompiledQuery with the generated source and a ready-to-call function.
    """
    return _Codegen(query).compile()
