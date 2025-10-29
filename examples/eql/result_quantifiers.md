---
jupytext:
  text_representation:
    extension: .md
    format_name: myst
    format_version: 0.13
    jupytext_version: 1.16.4
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

# Result Quantifiers

In EQL, there are two result quantifiers: `the` and `an`.

`the` is used to fetch a single solution and assert that there is exactly one solution. This behaves like [one](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Result.one) in SQLAlchemy.

`an` is used to fetch all solutions. This creates an iterator which lazily evaluates the query. This behaves like [all](https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Result.all) in SQLAlchemy.

Let's start with an example of a working query that requires exactly one result.

```{code-cell} ipython3
from dataclasses import dataclass

from typing_extensions import List

from krrood.entity_query_language.entity import entity, let, the, Symbol, symbolic_mode, an
from krrood.entity_query_language.failures import MultipleSolutionFound


@dataclass
class Body(Symbol):
    name: str


@dataclass
class World(Symbol):
    id_: int
    bodies: List[Body]


world = World(1, [Body("Body1"), Body("Body2")])

with symbolic_mode():
    query = the(entity(body := let(Body, domain=world.bodies),
                       body.name.endswith("1")))
print(query.evaluate())
```

If there are multiple results, we get an informative exception.

```{code-cell} ipython3
with symbolic_mode():
    query = the(entity(body := let(Body, domain=world.bodies)))

try:
    query.evaluate()
except MultipleSolutionFound as e:
    print(e)
```

We can also get all results using `an`.

```{code-cell} ipython3
with symbolic_mode():
    query = an(entity(body := let(Body, domain=None)))

print(*query.evaluate(), sep="\n")
```
