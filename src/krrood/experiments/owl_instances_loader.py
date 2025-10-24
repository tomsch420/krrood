from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import fields, is_dataclass
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type, Union

import rdflib
from rdflib import RDF, RDFS, URIRef, Literal

from ..class_diagrams.utils import get_generic_type_param
from ..class_diagrams.class_diagram import Association

# Import PropertyDescriptor to correctly detect descriptor class attributes
from ..entity_query_language.property_descriptor import PropertyDescriptor

# from .lubm_with_predicates import *
from ..entity_query_language.symbol_graph import SymbolGraph
from ..ormatic.utils import classes_of_module


class OwlInstancesRegistry:
    """Registry of instances created from an OWL/RDF instances file.

    Provides access to instances per Python model class and tracks URIRef to instance mapping.
    """

    def __init__(self) -> None:
        self._by_uri: Dict[URIRef, List[Any]] = defaultdict(list)
        self._by_class: Dict[Type, List[Any]] = {}

    def get_or_create_for(self, uri: URIRef, factory: Type, *args, **kwargs) -> Any:
        instances = self.resolve(uri)
        if (instances is None) or (
            not any(isinstance(inst, factory) for inst in instances)
        ):
            kwargs["uri"] = str(uri)
            inst = factory(*args, **kwargs)

            # Fill a best-effort human-readable name if available
            # local = local_name(uri)
            local = str(uri)
            if hasattr(inst, "uri") and getattr(inst, "uri") is None:
                setattr(inst, "uri", local)
            self._by_uri[uri].append(inst)
            self._by_class.setdefault(factory, []).append(inst)
        else:
            inst = [i for i in instances if isinstance(i, factory)][0]
        return inst

    def get(self, cls: Type) -> List[Any]:
        return list(self._by_class.get(cls, []))

    def resolve(self, uri: URIRef) -> Optional[Any]:
        return self._by_uri.get(uri)


def local_name(uri: Union[str, URIRef]) -> str:
    s = str(uri)
    if "#" in s:
        return s.rsplit("#", 1)[1]
    return s.rstrip("/").rsplit("/", 1)[-1]


def to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and (not name[i - 1].isupper()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def to_pascal(name: str) -> str:
    parts = []
    cur = []
    for ch in name:
        if ch == "_":
            if cur:
                parts.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return "".join(p.capitalize() for p in parts)


def _collect_model_metadata(model_module) -> Tuple[
    Dict[str, Type],  # class name -> class type
    Dict[str, Type],  # descriptor base name -> descriptor class
    Dict[Type, Dict[str, str]],  # class -> predicate(local snake) -> attribute name
    Dict[Type, Dict[Type, str]],  # class -> descriptor class -> attribute name
]:
    class_by_name: Dict[str, Type] = {}
    descriptor_by_name: Dict[str, Type] = {}
    field_by_predicate_local: Dict[Type, Dict[str, str]] = {}
    field_by_descriptor: Dict[Type, Dict[Type, str]] = {}

    # Collect model classes (dataclasses used to represent OWL classes)
    for attr_name in dir(model_module):
        obj = getattr(model_module, attr_name)
        if isinstance(obj, type) and is_dataclass(obj):
            class_by_name[attr_name] = obj
        # Collect descriptor classes available in the module for quick lookup by name
        if isinstance(obj, type):
            try:
                if (
                    issubclass(obj, PropertyDescriptor)
                    and obj is not PropertyDescriptor
                ):
                    descriptor_by_name[obj.__name__] = obj
            except TypeError:
                # obj is not a class we can check issubclass on
                pass

    # For each model class, map predicate local names to attribute names and descriptors to attributes
    for _, cls in list(class_by_name.items()):
        pred_map: Dict[str, str] = {}
        desc_map: Dict[Type, str] = {}

        # Descriptors are class attributes, not dataclass fields. Iterate attributes and
        # pick those that are instances of PropertyDescriptor (including subclasses).
        for attr in dir(cls):
            if attr.startswith("_"):
                continue
            val = getattr(cls, attr)
            if isinstance(val, PropertyDescriptor):
                # Map snake local predicate name to the class attribute name
                pred_map.setdefault(attr, attr)
                # Map descriptor class to attribute name for inverse lookups
                desc_map[type(val)] = attr

        field_by_predicate_local[cls] = pred_map
        field_by_descriptor[cls] = desc_map

    return (
        class_by_name,
        descriptor_by_name,
        field_by_predicate_local,
        field_by_descriptor,
    )


def _get_python_class_for_rdf_class(
    class_by_name: Dict[str, Type], rdf_class: URIRef
) -> Optional[Type]:
    name = local_name(rdf_class)
    # Expect PascalCase names in model equal to RDF local name
    return class_by_name.get(name)


def _coerce_literal(val: Literal, target_type: Optional[Type]) -> Any:
    if target_type is None:
        return val.toPython()
    try:
        # Unwrap Optional[T]
        origin = getattr(target_type, "__origin__", None)
        if origin is Union:
            args = [
                a for a in getattr(target_type, "__args__", ()) if a is not type(None)
            ]  # noqa: E721
            if args:
                target_type = args[0]
        if target_type in (str, int, float, bool):
            return target_type(val.toPython())
    except Exception:
        pass
    return val.toPython()


def load_multi_file_instances(
    owl_paths: Iterable[str], model_module: Union[str, ModuleType]
) -> OwlInstancesRegistry:
    """Load OWL/RDF instances into the provided generated Python model module."""
    if isinstance(model_module, str):
        model_module = __import__(model_module, fromlist=["*"])
    combined_registry = OwlInstancesRegistry()
    SymbolGraph().clear()
    symbol_graph = SymbolGraph.build(classes=classes_of_module(model_module))
    for path in owl_paths:
        load_instances(
            path, model_module, symbol_graph=symbol_graph, registry=combined_registry
        )
    return combined_registry


def load_instances(
    owl_path: str,
    model_module: Union[str, ModuleType],
    symbol_graph: Optional[SymbolGraph] = None,
    registry: Optional[OwlInstancesRegistry] = None,
) -> OwlInstancesRegistry:
    """Load OWL/RDF instances into the provided generated Python model module.

    This function is generic and can be reused with other OWL instance files that
    correspond to the given model module.
    """
    if isinstance(model_module, str):
        model_module = __import__(model_module, fromlist=["*"])
    if not symbol_graph:
        SymbolGraph().clear()
        symbol_graph = SymbolGraph.build(classes=classes_of_module(model_module))
    g = rdflib.Graph()
    g.parse(owl_path)

    (
        class_by_name,
        descriptor_by_name,
        field_by_predicate_local,
        field_by_descriptor,
    ) = _collect_model_metadata(model_module)
    if registry is None:
        registry = OwlInstancesRegistry()

    # First, create all instances that have an explicit rdf:type matching our model
    for s, _, o_class in g.triples((None, RDF.type, None)):
        if not isinstance(s, URIRef):
            continue
        py_cls = _get_python_class_for_rdf_class(class_by_name, o_class)
        if py_cls is None:
            continue
        existing_roles = registry.resolve(s)
        kwargs = {}
        if existing_roles:
            for er in existing_roles:
                (
                    assoc1,
                    assoc2,
                ) = symbol_graph.type_graph.get_common_role_taker_associations(
                    type(er), py_cls
                )
                if assoc1 and assoc2:
                    if assoc2.field.public_name in kwargs:
                        continue
                    kwargs[assoc2.field.public_name] = getattr(
                        er, assoc1.field.public_name
                    )
        role_taker_association = (
            symbol_graph.type_graph.get_role_taker_associations_of_cls(py_cls)
        )
        if role_taker_association:
            role_taker_field = role_taker_association.field
            # assumes role takers are not themselves roles (In general this is not true)
            if role_taker_field.public_name in kwargs:
                continue
            kwargs[role_taker_field.public_name] = role_taker_association.target.clazz()
        registry.get_or_create_for(s, py_cls, **kwargs)

    # Helper to ensure object instance exists by looking up its type dynamically
    def ensure_instance(uri: URIRef) -> Optional[List[Any]]:
        inst = registry.resolve(uri)
        if inst is not None:
            return inst
        # Try to infer class from rdf:type triples
        for _, _, o_class in g.triples((uri, RDF.type, None)):
            py_cls = _get_python_class_for_rdf_class(class_by_name, o_class)
            if py_cls is not None:
                return [registry.get_or_create_for(uri, py_cls)]
        return None

    # For convenience: map property local name to descriptor base class (if exists)
    def descriptor_base_for(pred_local: str) -> Optional[Type]:
        return descriptor_by_name.get(to_pascal(pred_local))

    # Assign properties
    for s, p, o in g:
        if p == RDF.type:
            continue
        if not isinstance(s, URIRef):
            continue
        subj = registry.resolve(s)
        if subj is None:
            # Subject without explicit type known to model; try infer
            subj = ensure_instance(s)
            if subj is None:
                continue
        subj = subj[0]
        pred_local = local_name(p)
        snake = to_snake(pred_local)
        subj_cls = type(subj)
        # Determine the appropriate field name on the subject
        field_name = field_by_predicate_local.get(subj_cls, {}).get(snake)
        if not field_name:
            if snake in [f.name for f in fields(subj_cls)]:
                field_name = snake

        role_taker_val = symbol_graph.get_role_takers_of_instance(subj)

        if isinstance(o, Literal):
            if field_name and hasattr(subj, field_name):
                # Coerce to field annotated type
                try:
                    ftypes = {f.name: f.type for f in fields(subj_cls)}
                except TypeError:
                    ftypes = {}
                coerced = _coerce_literal(o, ftypes.get(field_name))
                setattr(subj, field_name, coerced)
            elif role_taker_val and hasattr(role_taker_val, snake):
                setattr(role_taker_val, snake, o)
            # else: ignore literals not present in model
            continue

        # Object property
        obj_roles = ensure_instance(o) if isinstance(o, URIRef) else None
        if obj_roles is not None:
            obj = obj_roles[0]
        if field_name and hasattr(subj, field_name):
            subj_wrapped_cls = symbol_graph.type_graph.get_wrapped_class(subj_cls)
            subj_wrapped_field = subj_wrapped_cls._wrapped_field_name_map_.get(
                field_name
            )
            req_obj_type = subj_wrapped_field.type_endpoint
            matched_obj = None
            for obj_role in obj_roles:
                if issubclass(type(obj_role), req_obj_type):
                    matched_obj = obj_role
                    break
            if not matched_obj:
                role_taker_assoc = (
                    symbol_graph.type_graph.get_role_taker_associations_of_cls(
                        type(obj_roles[0])
                    )
                )
                if role_taker_assoc:
                    if role_taker_assoc.target.clazz is req_obj_type:
                        matched_obj = getattr(
                            obj_roles[0], role_taker_assoc.field.public_name
                        )
            if not matched_obj:
                raise ValueError(f"Could not assign {obj} to {subj} ({p})")
            obj = matched_obj
            lst = getattr(subj, field_name, None)
            if isinstance(lst, set) and obj is not None:
                lst.add(obj)
                continue

        if role_taker_val and hasattr(role_taker_val, snake):
            lst = getattr(role_taker_val, snake)
            if isinstance(lst, set) and obj is not None:
                lst.add(obj)
                continue

        base_desc = descriptor_base_for(snake)

        if base_desc is not None:
            possible_roles = list(base_desc.domain_types)
            if len(possible_roles) == 1:
                new_role_class = possible_roles[0]
            else:
                o_type = type(obj)
                wrapped_field_types = {}
                chosen_role = None
                for pr in possible_roles:
                    try:
                        pr_wrapped_field = getattr(pr, snake)
                    except AttributeError:
                        continue
                    range_types = tuple(pr_wrapped_field.range_type)
                    if issubclass(o_type, range_types):
                        wrapped_field_types[pr] = range_types
                # choose the nearest wrapped field type
                if wrapped_field_types:
                    chosen_role = min(
                        wrapped_field_types.keys(),
                        key=lambda k: min(
                            len(vi.__mro__) for vi in wrapped_field_types[k]
                        ),
                    )
                if chosen_role is None:
                    raise ValueError(
                        f"Could not determine role for {obj} ({o_type}) and predicate {p} ({base_desc})"
                    )
                new_role_class = chosen_role

            existing_roles = registry.resolve(s)
            new_role = None
            for er in existing_roles:
                if type(er) is new_role_class:
                    new_role = er
                    break
            if new_role is None:
                type_graph = symbol_graph.type_graph
                kwargs = {}
                assoc1, assoc2 = type_graph.get_common_role_taker_associations(
                    subj_cls, new_role_class
                )
                if assoc1 and assoc2:
                    kwargs[assoc2.field.public_name] = getattr(
                        subj, assoc1.field.public_name
                    )

                new_role = registry.get_or_create_for(
                    subj.uri, new_role_class, **kwargs
                )
            if hasattr(new_role, snake):
                lst = getattr(new_role, snake)
                if isinstance(lst, set) and obj is not None:
                    lst.add(obj)
                    continue

        raise ValueError(f"Could not assign {obj} to {subj} ({p})")

        # Try inverse assignment if direct field does not exist on subject
        if base_desc is not None and obj is not None:
            # Find inverse_of on the base descriptor class (attribute may be missing)
            inverse = getattr(base_desc, "inverse_of", None)
            if inverse is not None:
                obj_cls = type(obj)
                inv_field = field_by_descriptor.get(obj_cls, {}).get(inverse)
                if inv_field and hasattr(obj, inv_field):
                    lst = getattr(obj, inv_field, None)
                    if isinstance(lst, list):
                        lst.append(subj)
                        continue
        # Fallback: if both sides have a list field with the same snake name, try assign on subject
        if (
            field_name
            and hasattr(subj, field_name)
            and isinstance(getattr(subj, field_name), set)
            and obj is not None
        ):
            getattr(subj, field_name).add(obj)

    return registry
