# krrood/entity_query_language/diagram_introspection.py
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dc_fields
from typing import List, Type

from ..class_diagrams.attribute_introspector import (
    AttributeIntrospector,
    DiscoveredAttribute,
)


@dataclass
class DescriptorAwareIntrospector(AttributeIntrospector):
    """Discover dataclass fields plus EQL descriptor-backed attributes.

    Public attributes that implement the descriptor protocol (`__get__` and `__set__`)
    and expose an `attr_name` are mapped to their hidden backing dataclass field,
    but are presented under the public attribute name.
    """

    def discover(self, owner_cls: Type) -> List[DiscoveredAttribute]:
        # Index all dataclass fields by name
        all_dc_fields = {f.name: f for f in dc_fields(owner_cls)}

        discovered: list[DiscoveredAttribute] = []

        # 1) Normal public dataclass fields
        for f in all_dc_fields.values():
            if not f.name.startswith("_"):
                discovered.append(DiscoveredAttribute(public_name=f.name, field=f))

        # 2) Descriptor-backed attributes via duck typing
        for public_name in dir(owner_cls):
            if public_name.startswith("_"):
                continue
            attr = getattr(owner_cls, public_name)
            has_descriptor_protocol = hasattr(attr, "__get__") and hasattr(
                attr, "__set__"
            )
            backing_name = getattr(attr, "attr_name", None)
            if not (has_descriptor_protocol and isinstance(backing_name, str)):
                continue

            backing_field = all_dc_fields.get(backing_name)
            if backing_field is None:
                # Hidden field not present as a dataclass field; skip defensively
                continue

            discovered.append(
                DiscoveredAttribute(public_name=public_name, field=backing_field)
            )

        return discovered
