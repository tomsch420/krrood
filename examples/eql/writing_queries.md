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

# Writing Queries

EQL can be well-used to answer symbolic questions through querying.


Whenever you write a query you have to use the `with symbolic_mode()` context manager.

This context manager is different from plain python in the sense that it doesn't evaluate what you write directly but
treats your statements as something that will be evaluated later (lazily).
Queries typically compare attributes of variables where the assignments of the 
variables don't exist yet, hence an immediate evaluation would cause failures, as demonstrated below.

```{note}
The symbolic mode is something that is explicitly entered. Whenever this is not entered you are in the non-symbolic mode
which just is ordinary python behavior.
```

Frameworks like SQLAlchemy, as an Object-Relational Mapper (ORM), use metaprogramming techniques 
(specifically, class and attribute interception/rewriting) to manage database interactions and object state, 
which introduces performance overhead and requires developer awareness of the framework's internal mechanisms when 
designing application classes.

EQL's metaprogramming effects are context-bound; it only intercepts class creation (via `__new__`) and attribute 
access (via `getattr`) when a class is defined or accessed within the with `symbolic_mode()` context manager.

This approach ensures that your class definitions remain pure and decoupled from the query mechanism 
outside the explicit symbolic context. Consequently, your classes can focus exclusively on their domain logic, 
leading to better adherence to the [Single Responsibility Principle](https://realpython.com/solid-principles-python/#single-responsibility-principle-srp).

Here is a query that does work due to the symbolic mode:

```{code-cell} ipython3
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

```{code-cell} ipython3
try:
    query = an(
        entity(
            body := let(Body, domain=world.bodies), body.name.startswith("B"),
        )
    )
except AttributeError as e:
    print(e)

```


