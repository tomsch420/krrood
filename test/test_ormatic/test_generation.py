import os
import pytest

from dataset import example_classes, semantic_world_like_classes
from dataset.example_classes import *
from krrood.class_diagrams.class_diagram import ClassDiagram
from krrood.entity_query_language import alternative
from krrood.ormatic.ormatic import ORMatic
from krrood.ormatic.utils import classes_of_module, recursive_subclasses
from krrood.ormatic.dao import AlternativeMapping, DataAccessObject


def test_generation_process():
    all_classes = set(classes_of_module(example_classes))
    all_classes.update(set(classes_of_module(semantic_world_like_classes)))
    all_classes -= set(recursive_subclasses(DataAccessObject))
    all_classes -= set(recursive_subclasses(Enum))
    all_classes -= set(recursive_subclasses(TypeDecorator))
    all_classes -= set(recursive_subclasses(AlternativeMapping))
    all_classes -= set(recursive_subclasses(PhysicalObject)) | {PhysicalObject}
    all_classes -= {NotMappedParent, ChildNotMapped}

    class_diagram = ClassDiagram(list(all_classes))

    instance = ORMatic(
        class_dependency_graph=class_diagram,
        type_mappings={
            PhysicalObject: ConceptType,
        },
        alternative_mappings=recursive_subclasses(AlternativeMapping),
    )

    alternative_maps = instance.alternatively_maps_relations
    assert (
        len(
            [
                r
                for r in alternative_maps
                if r.source.clazz == TransformationMapped
                and r.target.clazz == Transformation
            ]
        )
        == 1
    )

    instance.make_all_tables()

    file_path = os.path.join(
        os.path.dirname(__file__), "..", "dataset", "sqlalchemy_interface.py"
    )
    # Generate SQLAlchemy declarative mappings
    with open(
        file_path,
        "w",
    ) as f:
        instance.to_sqlalchemy_file(f)
    assert os.path.exists(file_path)
