---
jupyter:
  jupytext:
    text_representation:
      extension: .md
      format_name: markdown
      format_version: '1.3'
      jupytext_version: 1.18.1
  kernelspec:
    display_name: Python 3
    language: python
    name: python3
---

# Writing Queries

EQL can be well-used to answer symbolic questions through querying.
Whenever you write a query you have to use the `with symbolic_mode()` context manager.
This is due to that case that you want to access attributes of variables where the assignments of the variables don't exist yet.

Frameworks like SQLAlchemy don't have this problem but have sever costs at other places.
SQLAlchemy, for instance, hijacks creation and attribute selection of classes always, and you have to be aware of that when designing your classes.
This also comes at a cost of performance.

EQL only hijacks your `getattr` and `__new__` method when you use the `with symbolic_mode()` context manager.
This means that you can design your classes without worrying about querying the classes which in turn leads to better alignment with the [Single Responsibility Principle](https://realpython.com/solid-principles-python/#single-responsibility-principle-srp).

Here is a query that does work due to the symbolic mode:

```python
from dataclasses import dataclass

from typing_extensions import List

from krrood.entity_query_language.entity import entity, an, let, symbolic_mode, Symbol


@dataclass
class Body(Symbol):
    name: str


@dataclass
class World:
    id_: int
    bodies: List[Body]


world = World(1, [Body("Body1"), Body("Body2")])

with symbolic_mode():
    query = an(
        entity(
            body := let(Body, domain=world.bodies), body.name.startswith("B"),
        )
    )
print(*query.evaluate(), sep="\n")

```

This query doesn't work due to the lack of symbolic mode:

```python
try:
    query = an(
        entity(
            body := let(Body, domain=world.bodies), body.name.startswith("B"),
        )
    )
except AttributeError as e:
    print(e)

```


