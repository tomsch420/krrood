# Example with `exists` and `for_all`

`for_all` and `exists` are used to express universal and existential quantification of a certain condition over
a collection, these iterate over the quantified collection and check the condition. In the case of `exists`,
there need only be one result per inner element to satisfy the condition for each value of the quantified variable. 
While `for_all` requires inner elements to satisfy the condition for all values of the quantified variable.

Below is a minimal, self-contained example that mirrors the behavior tested in the suite.

```python
from dataclasses import dataclass, field
from typing_extensions import List

from krrood.entity_query_language.entity import symbolic_mode, let, not_, in_, entity, an, \
    From, Symbol, for_all, exists


# Minimal dataset for the example
@dataclass
class Body(Symbol):
    name: str


@dataclass
class Handle(Body):
    ...


@dataclass
class Container(Body):
    ...


@dataclass
class View(Symbol):
    world: object = field(default=None, repr=False, kw_only=True)


@dataclass
class Drawer(View):
    handle: Handle
    container: Container


@dataclass
class World(Symbol):
    bodies: List[Body] = field(default_factory=list)
    views: List[View] = field(default_factory=list)


# Build a small world
world = World()
container1 = Container(name="Container1")
container3 = Container(name="Container3")
handle1 = Handle(name="Handle1")
handle3 = Handle(name="Handle3")
world.bodies.extend([container1, container3, handle1, handle3])

# Two drawers
drawer1 = Drawer(handle=handle1, container=container1)
drawer2 = Drawer(handle=handle3, container=container3)


# A simple view-like class with an iterable attribute `drawers`
class CabinetLike(View):
    def __init__(self, drawers):
        super().__init__()
        self.drawers = list(drawers)


cabinet = CabinetLike([drawer1, drawer2])
world.views = [cabinet]
```

## Example 1: Test membership using in_/not_ with nested iterables

```python
with symbolic_mode():
    # A variable ranging over drawers in the world (simulate another source of drawers)
    d = Drawer(From([drawer1, drawer2]))
    views = CabinetLike(From(world.views))
    all_drawers = views.drawers # A nested iterable where there is a list of views each with a list of drawers.
    # Find drawers that are NOT in the list (expect none in this tiny world)
    query2 = an(entity(d, for_all(all_drawers, not_(in_(d, all_drawers)))))

rows2 = list(query2.evaluate())
assert len(rows2) == 0
```

## Example 1: Test membership using in_/not_ with nested iterables

```python
with symbolic_mode():
    d = let(type_=Drawer, domain=[drawer1, drawer2])
    views = let(type_=View, domain=world.views)
    all_drawers = views.drawers
    # Find drawers that exist in all_drawers
    query3 = an(entity(d, exists(all_drawers, in_(d, all_drawers))))

rows3 = list(query3.evaluate())
assert {r.handle.name for r in rows3} == {"Handle1", "Handle3"}
```
