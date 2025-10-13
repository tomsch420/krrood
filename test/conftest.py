import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers

from dataset.semantic_world_like_classes import *
from krrood.entity_query_language.symbolic import Variable
from krrood.ormatic.utils import drop_database
from test_eql.conf.world.doors_and_drawers import World as DoorsAndDrawersWorld
from test_eql.conf.world.handles_and_containers import (
    World as HandlesAndContainersWorld,
)
from dataset.sqlalchemy_interface import *


@pytest.fixture
def handles_and_containers_world() -> World:
    return HandlesAndContainersWorld().create()


@pytest.fixture
def doors_and_drawers_world() -> World:
    return DoorsAndDrawersWorld().create()


@pytest.fixture(autouse=True)
def cleanup_after_test():
    # Setup: runs before each test
    yield
    # Teardown: runs after each test
    for c in Variable._cache_.values():
        c.clear()
    Variable._cache_.clear()


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
