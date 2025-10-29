import logging
import os
from dataclasses import is_dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers

import krrood.entity_query_language.orm.model
import krrood.entity_query_language.symbol_graph
from krrood.class_diagrams.class_diagram import ClassDiagram
from krrood.entity_query_language.predicate import (
    HasTypes,
    HasType,
)
from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.ormatic.dao import AlternativeMapping
from krrood.ormatic.ormatic import ORMatic
from krrood.ormatic.utils import classes_of_module
from krrood.ormatic.utils import drop_database
from krrood.utils import recursive_subclasses
from .dataset.example_classes import (
    PhysicalObject,
    NotMappedParent,
    ChildNotMapped,
    ConceptType,
)
from .dataset.semantic_world_like_classes import *
from .test_eql.conf.world.doors_and_drawers import DoorsAndDrawersWorld
from .test_eql.conf.world.handles_and_containers import (
    HandlesAndContainersWorld,
)


def generate_sqlalchemy_interface():
    """
    Generate the SQLAlchemy interface file before tests run.

    This ensures the file exists before any imports attempt to use it,
    solving test isolation issues when running all tests.
    """

    # build the symbol graph
    symbol_graph = SymbolGraph()

    # collect all classes
    all_classes = {c.clazz for c in symbol_graph._class_diagram.wrapped_classes}
    all_classes |= {
        am.original_class() for am in recursive_subclasses(AlternativeMapping)
    }
    all_classes |= set(classes_of_module(krrood.entity_query_language.symbol_graph))
    all_classes |= {Symbol}

    # remove classes that don't need persistence
    all_classes -= {HasType, HasTypes}
    # remove classes that are not dataclasses
    all_classes = {c for c in all_classes if is_dataclass(c)}
    all_classes -= set(recursive_subclasses(PhysicalObject)) | {PhysicalObject}
    all_classes -= {NotMappedParent, ChildNotMapped}
    class_diagram = ClassDiagram(
        list(sorted(all_classes, key=lambda c: c.__name__, reverse=True))
    )

    instance = ORMatic(
        class_dependency_graph=class_diagram,
        type_mappings={
            PhysicalObject: ConceptType,
        },
        alternative_mappings=recursive_subclasses(AlternativeMapping),
    )

    instance.make_all_tables()

    file_path = os.path.join(
        os.path.dirname(__file__), "dataset", "sqlalchemy_interface.py"
    )

    with open(file_path, "w") as f:
        instance.to_sqlalchemy_file(f)

    return instance


def pytest_configure(config):
    """
    Generate sqlalchemy_interface.py before test collection.

    This hook runs before pytest collects tests and imports modules,
    ensuring the generated file exists before any module-level imports.
    """
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("numpy").setLevel(logging.WARNING)


def pytest_sessionstart(session):
    try:
        ...  # generate_sqlalchemy_interface()
    except Exception as e:
        import warnings

        warnings.warn(
            f"Failed to generate sqlalchemy_interface.py: {e}. "
            "Tests may fail if the file doesn't exist.",
            RuntimeWarning,
        )


from .dataset.sqlalchemy_interface import *


@pytest.fixture
def handles_and_containers_world() -> World:
    world = HandlesAndContainersWorld().create()
    return world


@pytest.fixture
def doors_and_drawers_world() -> World:
    world = DoorsAndDrawersWorld().create()
    SymbolGraph()
    return world


@pytest.fixture(autouse=True)
def cleanup_after_test():
    # Setup: runs before each test
    SymbolGraph()
    yield
    SymbolGraph().clear()


@pytest.fixture(scope="session")
def engine():
    configure_mappers()
    engine = create_engine("sqlite:///:memory:")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session(engine):
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def database(engine, session):
    Base.metadata.create_all(engine)
    yield
    drop_database(engine)
