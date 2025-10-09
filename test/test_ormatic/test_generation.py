import os
import unittest

from sqlalchemy.orm import registry, Session

from dataset import example_classes, semantic_world_like_classes
from dataset.example_classes import *
from krrood.ormatic.ormatic import ORMatic
from krrood.ormatic.utils import classes_of_module, recursive_subclasses
from krrood.ormatic.dao import AlternativeMapping, DataAccessObject


class SQLAlchemyGenerationTestCase(unittest.TestCase):
    session: Session
    mapper_registry: registry
    ormatic_instance: ORMatic

    @classmethod
    def setUpClass(cls):
        # Logger configuration is now handled in ormatic/__init__.py
        # Note: Default log level is INFO, was DEBUG here
        all_classes = set(classes_of_module(example_classes))
        all_classes.update(set(classes_of_module(semantic_world_like_classes)))
        all_classes -= set(recursive_subclasses(DataAccessObject))
        all_classes -= set(recursive_subclasses(Enum))
        all_classes -= set(recursive_subclasses(TypeDecorator))
        all_classes -= {
            mapping.original_class()
            for mapping in all_classes
            if issubclass(mapping, AlternativeMapping)
        }
        all_classes -= set(recursive_subclasses(PhysicalObject)) | {PhysicalObject}
        all_classes -= {NotMappedParent, ChildNotMapped}

        cls.ormatic_instance = ORMatic(
            list(sorted(all_classes, key=lambda c: c.__name__)),
            {
                PhysicalObject: ConceptType,
            },
        )

        # Generate SQLAlchemy declarative mappings
        with open(
            os.path.join(
                os.path.dirname(__file__), "..", "dataset", "sqlalchemy_interface.py"
            ),
            "w",
        ) as f:
            cls.ormatic_instance.to_sqlalchemy_file(f)

    def test_file_generation(self):
        # Check that the file was created
        file_path = os.path.join(
            os.path.dirname(__file__), "..", "dataset", "sqlalchemy_interface.py"
        )
        self.assertTrue(os.path.exists(file_path))


if __name__ == "__main__":
    unittest.main()
