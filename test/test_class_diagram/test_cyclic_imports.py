from dataclasses import fields

from dataset.cyclic_imports import PoseAnnotation
from krrood.class_diagrams.class_diagram import WrappedClass

from dataset.example_classes import Pose


def test_unfinished_type_field_info():

    wrapped_cls = WrappedClass(PoseAnnotation)
    f = [f for f in wrapped_cls.fields if f.field.name == "pose"][0]
    assert f.contained_type is Pose
