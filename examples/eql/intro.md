# Introduction

The Entity Query Language (EQL) is a relational query language that is pythonic, and intuitive.

The interface side of EQL is inspired by [euROBIN](https://www.eurobin-project.eu/) entity query language white paper.

## Basic Example
An important feature of EQL is that you do not need to do operations like JOIN in SQL, this is performed implicitly.
EQL tries to mirror your intent in a query statement with as little boilerplate code as possible.
For example, attribute access with and equal check to another value is just as you expect:

```python
from dataclasses import dataclass

from typing_extensions import List

from krrood.entity_query_language.entity import entity, an, let, contains, symbolic_mode, Symbol


@dataclass
class Body(Symbol):
    name: str


@dataclass
class World:
    id_: int
    bodies: List[Body]


world = World(1, [Body("Body1"), Body("Body2")])

with symbolic_mode():
    body = let(Body, domain=world.bodies)
    query = an(entity(body, contains(body.name, "2"),
                      body.name.startswith("Body"))
               )
results = list(query.evaluate())
assert len(results) == 1
assert results[0].name == "Body2"
```

where this creates a body variable that gets its values from world.bodies, and filters them to have their att "name"
equal to "Body1".ample shows generic usage of the Ripple Down Rules to classify objects in a propositional setting.

Notice that it is possible to use both provided helper methods by EQL and other methods that are accessible through your
object instance and use them as part of the query conditions.

