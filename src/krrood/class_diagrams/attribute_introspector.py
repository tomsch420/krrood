from __future__ import annotations

from dataclasses import dataclass, Field
from abc import ABC, abstractmethod
from dataclasses import dataclass
from dataclasses import fields as dc_fields

from typing_extensions import Dict, Iterable, List, Type, Optional


@dataclass
class DiscoveredAttribute:
    """Attribute discovered on a class.

    - `public_name` is how users refer to it (e.g., "advisor").
    - `field` is the hidden or public dataclass `Field` that stores values.
    """

    field: Field
    public_name: Optional[str] = None

    def __post_init__(self):
        if self.public_name is None:
            self.public_name = self.field.name

    def __hash__(self) -> int:
        return hash(self.field)


@dataclass
class AttributeIntrospector(ABC):
    """Strategy that discovers class attributes for diagramming.

    Implementations return the set of dataclass-backed attributes that
    should appear on a class diagram, including their public names.
    """

    @abstractmethod
    def discover(self, owner_cls: Type) -> List[DiscoveredAttribute]:
        """Return discovered attributes for `owner_cls`.

        The `field` of each result must be a dataclass `Field` belonging to
        `owner_cls`, while `public_name` is how it should be addressed and displayed.
        """
        raise NotImplementedError


@dataclass
class DataclassOnlyIntrospector(AttributeIntrospector):
    """Discover only public dataclass fields (no leading underscore)."""

    def discover(self, owner_cls: Type) -> List[DiscoveredAttribute]:
        result: List[DiscoveredAttribute] = []
        for f in dc_fields(owner_cls):
            if not f.name.startswith("_"):
                result.append(DiscoveredAttribute(public_name=f.name, field=f))
        return result
