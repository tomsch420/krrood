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

# Logical Operators

EQL supports a bunch of logical operators, namely `and`, `or`, `else if`, `for_all` and `not`.
When you want to use these, you have to rely on the operators imported from EQL.entity, since the python operators cannot be overloaded to the extent that EQL requires.

```python
from dataclasses import dataclass

from typing_extensions import List

from krrood.entity_query_language.entity import entity, an, or_, symbolic_mode, Symbol, let, not_, and_


@dataclass
class Body(Symbol):
    name: str


@dataclass
class World:
    id_: int
    bodies: List[Body]


world = World(1, [Body("Container1"), Body("Container2"),
                  Body("Handle1"), Body("Handle2")])
```

This way of writing `and`, `or` is exactly like constructing a tree which allows for the user to write in the same
structure as how the computation is done internally. Take note that whenever conditions are used in a query without an explicit logical operator, `and` is assumed.

```python
with symbolic_mode():
    body = let(type_=Body, domain=world.bodies)
    query = an(entity(body,
                      or_(body.name.startswith("C"), body.name.endswith("1")),
                      or_(body.name.startswith("H"), body.name.endswith("1"))
                      )
               )
print(*query.evaluate(), sep="\n")
```

Negation is important and tricky. EQL tries to optimize the query when negation is used, which greatly lowers wait time
to first response. This is done by avoiding evaluating all possibilities to evaluation the negation.

```python
with symbolic_mode():
    query = an(entity(body := let(type_=Body, domain=world.bodies),
                      not_(or_(body.name.startswith("C"), body.name.endswith("1")),
                           )
                      )
               )
print(*query.evaluate(), sep="\n")
```

Take note that queries involving negations atre actually transformed into a simplified one under the hood.

```python
print(type(query._child_._child_))
print(query._child_._child_.left._invert_)
print(query._child_._child_.right._invert_)
```

EQL also optimizes what you mean by or_. Sometimes, it is more beneficial to treat the or statement as an `ElseIf` statement.
- `ElseIf` (else-if semantics) is used when both sides of `or_` reference the exact same set of non-literal symbolic variables; the right side is evaluated only if the left side is false for the current bindings.
- `Or` (union semantics) is used when the sides reference different variable sets (one introduces variables the other does not); both sides are evaluated and their solutions are unioned.

In other words: same variables → `ElseIf`; different variables → `Or` (Union).

An example for a query that gets optimized to `ElseIf` is

```python

with symbolic_mode():
    query_elseif = an(
        entity(
            body := let(type_=Body, domain=world.bodies),
            or_(
                body.name.startswith("C"),  # left uses {body}
                body.name.endswith("1"),  # right uses {body}
            ),
        )
    )

print(type(query_elseif._child_._child_))

```

And here is one where an actual union is performed.

```python
with symbolic_mode():
    body = let(type_=Body, domain=world.bodies)
    other = let(type_=Body, domain=world.bodies)
    query_union = an(
        entity(
            body,
            or_(
                body.name.startswith("C"),
                # Introduces `other`, so the variable sets differ → treated as Union
                and_(body.name == other.name, other.name.endswith("2")),
            ),
        )
    )
print(type(query_union._child_._child_))
```
