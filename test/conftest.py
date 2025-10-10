import pytest

from krrood.entity_query_language.symbolic import Variable
from test_eql.conf.world.handles_and_containers import (
    World as HandlesAndContainersWorld,
)
from test_eql.conf.world.doors_and_drawers import World as DoorsAndDrawersWorld
from dataset.semantic_world_like_classes import *


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
