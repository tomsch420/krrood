from dataclasses import fields

from krrood.class_diagrams import ClassDiagram
from ..dataset.cyclic_imports import PoseAnnotation
from krrood.class_diagrams.class_diagram import WrappedClass

from ..dataset.example_classes import Pose


def test_unfinished_type_field_info():

    diagram = ClassDiagram([Pose, PoseAnnotation])

    wrapped_cls = diagram.get_wrapped_class(PoseAnnotation)
    f = [f for f in wrapped_cls.fields if f.field.name == "pose"][0]
    assert f.contained_type is Pose
