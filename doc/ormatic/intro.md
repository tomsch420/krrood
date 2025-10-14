# Overview
ORMatic is a subpackage of KRROOD that turns Python dataclasses into a working SQLAlchemy ORM interface. 
It generates a declarative SQLAlchemy model layer (DAO classes) and provides helpers to translate between your domain 
objects and database rows.

- Input: Your existing dataclasses (and optional explicit mappings)
- Output: A declarative SQLAlchemy model file with `Base` and `*DAO` classes, plus runtime helpers (`to_dao`, `from_dao`)
- Bonus: A translator from Entity Query Language (EQL) expressions to SQLAlchemy `select(...)` statements

## Core Assumptions and Modeling Rules
To keep the translation unambiguous and the generated ORM ergonomic, ORMatic relies on a few simple rules:

- Unmapped fields: Any dataclass field whose name begins with `_` is ignored. Use this for purely runtime or derived data that should not be persisted.
- Optional types: The only supported union is `Optional[T]`. For other unions, model a shared superclass and use that type instead.
- Collections: Iterables are never optional and never nested. If you want an “optional list,” use a default factory that returns an empty collection.
- Inheritance and polymorphism:
  - Inheritance is supported and generates proper joined-table inheritance.
  - Only the first base class in a multiple inheritance list is considered for abstract queries (polymorphic identity).
- Type discipline: Use concrete, non-ambiguous annotations on dataclass fields. Prefer value objects and small dataclasses over loose primitives when modeling relationships.

If your dataclasses cannot follow these patterns, two escape hatches exist:

- Alternative Mapping: Provide explicit mapping classes to control how a dataclass is persisted.
- Type Decorator: Supply custom type decorators for special value types.

## What ORMatic Generates
Running ORMatic over a set of classes yields a module containing:

- `Base`: A SQLAlchemy `DeclarativeBase` to bind metadata and a `type_mappings` registry for custom types.
- `*DAO` classes: One per dataclass (and per explicit mapping), each a SQLAlchemy declarative model with:
  - Columns for builtin and custom-typed fields
  - Foreign keys and relationships inferred from nested dataclasses and collections
  - `__mapper_args__` for inheritance and polymorphic configuration
- A generic `DataAccessObject[T]` base that adds:
  - `to_dao(obj: T) -> DAO`: Convert a domain object to its DAO
  - `from_dao(self) -> T`: Reconstruct the original domain object from a DAO row

Internally, ORMatic walks your dataclass graph, identifies scalar fields, one-to-one and one-to-many relations, and many-to-many associations, and then uses a Jinja template to emit a full SQLAlchemy declarative layer that is decoupled from your original code.
