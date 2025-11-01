from ..dataset.example_classes import VectorsWithProperty
from krrood.entity_query_language.symbolic import symbolic_mode, From
from krrood.entity_query_language.entity import (
    flatten,
    entity,
    an,
    not_,
    in_,
    concatenate,
    the,
    for_all,
    let,
)
from ..dataset.semantic_world_like_classes import View, Drawer, Container, Cabinet


# Make a simple View-like container with an iterable attribute `drawers` to be flattened
class CabinetLike(View):
    def __init__(self, drawers, world):
        super().__init__(world=world)
        self.drawers = list(drawers)


def test_flatten_iterable_attribute(handles_and_containers_world):
    world = handles_and_containers_world

    with symbolic_mode():
        views = let(Cabinet, world.views)
        drawers = flatten(views.drawers)
        query = an(entity(drawers))

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 3
    assert {row.handle.name for row in results} == {"Handle1", "Handle2", "Handle3"}


def test_flatten_iterable_attribute_and_use_not_equal(handles_and_containers_world):
    world = handles_and_containers_world

    with symbolic_mode():
        cabinets = let(Cabinet, world.views)
        drawer_1 = an(entity(d := let(Drawer, world.views), d.handle.name == "Handle1"))
        drawers = flatten(cabinets.drawers)
        query = an(entity(drawers, drawer_1 != drawers))

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 2
    assert {row.handle.name for row in results} == {"Handle2", "Handle3"}


def test_concatenate(handles_and_containers_world):
    world = handles_and_containers_world

    with symbolic_mode():
        cabinets = let(Cabinet, world.views)
        my_drawers = an(
            entity(d := let(Drawer, world.views), d.handle.name == "Handle1")
        )
        drawers = concatenate(cabinets.drawers)
        query = an(entity(my_drawers, not_(in_(my_drawers, drawers))))

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 0

    with symbolic_mode():
        cabinets = let(Cabinet, world.views)
        my_drawers = an(
            entity(d := let(Drawer, world.views), d.handle.name == "Handle1")
        )
        drawers = concatenate(cabinets.drawers)
        query = an(entity(my_drawers, in_(my_drawers, drawers)))

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 1
    assert results[0].handle.name == "Handle1"


def test_for_all(handles_and_containers_world):
    world = handles_and_containers_world

    with symbolic_mode():
        cabinets = let(Cabinet, world.views)
        the_cabinet_container = the(
            entity(c := let(Container, world.bodies), c.name == "Container2")
        )
        query = an(
            entity(
                the_cabinet_container,
                for_all(
                    cabinets.container, the_cabinet_container == cabinets.container
                ),
            )
        )

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 1
    assert results[0].name == "Container2"

    with symbolic_mode():
        cabinets = let(Cabinet, world.views)
        the_cabinet_container = the(
            entity(c := let(Container, world.bodies), c.name == "Container2")
        )
        query = an(
            entity(
                the_cabinet_container,
                for_all(
                    cabinets.container, the_cabinet_container != cabinets.container
                ),
            )
        )

    results = list(query.evaluate())

    # We should get one row for each drawer and the parent view preserved
    assert len(results) == 0


def test_property_selection():
    """
    Test that properties can be selected from entities in a query.
    """
    with symbolic_mode():
        q = an(entity(v := let(VectorsWithProperty, None), v.vectors[0].x == 1))
