from dataclasses import dataclass, field
from typing_extensions import Set

from krrood.entity_query_language.property_descriptor import Thing, PropertyDescriptor
from krrood.entity_query_language.attribute_introspector import (
    DescriptorAwareIntrospector,
)
from krrood.class_diagrams.class_diagram import ClassDiagram


@dataclass(eq=False)
class A(Thing):
    pass


@dataclass(eq=False)
class B(Thing):
    rel: Set[A] = field(default_factory=PropertyDescriptor)


def test_descriptor_aware_introspector():
    cd = ClassDiagram(classes=[A, B], introspector=DescriptorAwareIntrospector())
    labels = {str(a) for a in cd.associations}
    assert "has-rel" in labels
