# Generating an ORMatic Interface

A typical workflow for generating an ORMatic interface consists of three steps:

1) Identify candidate classes
- Choose the dataclasses that represent your persistent domain.
- Optionally include explicit mapping classes (see Alternative Mapping below).
- Optionally provide custom type mappings (see Custom and Complex Field Types below).


2) Create the interface
After identifying the persistent part of your domain,
I recommend creating a script that generates the interface.
The script for generating the test ORM for KRROOD looks like this:


```python
import os
from enum import Enum

from sqlalchemy.types import TypeDecorator

from dataset import example_classes, semantic_world_like_classes
from dataset.example_classes import (
    PhysicalObject,
    NotMappedParent,
    ChildNotMapped,
    ConceptType,
)
from krrood.class_diagrams.class_diagram import ClassDiagram
from krrood.ormatic.ormatic import ORMatic
from krrood.ormatic.utils import classes_of_module, recursive_subclasses
from krrood.ormatic.dao import AlternativeMapping, DataAccessObject


# get all classes in the dataset modules
all_classes = set(classes_of_module(example_classes))
all_classes |= set(classes_of_module(semantic_world_like_classes))

# remove classes that are not dataclasses
all_classes -= set(recursive_subclasses(DataAccessObject))
all_classes -= set(recursive_subclasses(Enum))
all_classes -= set(recursive_subclasses(TypeDecorator))
all_classes -= set(recursive_subclasses(AlternativeMapping))
all_classes -= set(recursive_subclasses(PhysicalObject)) | {PhysicalObject}
all_classes -= {NotMappedParent, ChildNotMapped}

# sort the classes to ensure consistent ordering in the generated file
class_diagram = ClassDiagram(
    list(sorted(all_classes, key=lambda c: c.__name__, reverse=True))
)

instance = ORMatic(
    class_dependency_graph=class_diagram,
    type_mappings={
        PhysicalObject: ConceptType,
    },
    alternative_mappings=recursive_subclasses(AlternativeMapping),
)

instance.make_all_tables()

file_path = os.path.join(
    os.path.dirname(__file__), "dataset", "sqlalchemy_interface.py"
)

with open(file_path, "w") as f:
    instance.to_sqlalchemy_file(f)
```

3) Use the generated interface
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from your_package.sqlalchemy_interface import Base, SomeDAO

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
session = Session(engine)

# Domain object → DAO → persist
obj = SomeDomainClass(...)
dao = SomeDAODAO.to_dao(obj)
session.add(dao)
session.commit()

# Query and reconstruct
row = session.query(SomeDAO).first()
reconstructed = row.from_dao()
```

### Working With the DAO API
- `to_dao(obj)`: Convert a dataclass instance into its DAO counterpart, recursively converting nested dataclasses and collections.
- `from_dao()`: Convert a loaded DAO instance back into the original dataclass (including nested parts and collections).
- `to_dao` raises `NoDAOFoundError` if a class is not mapped. This is a design safeguard: only persist what you explicitly included in the input set.

### Relationships and Collections
- One-to-one: A nested dataclass field becomes a relationship with a foreign key column.
- One-to-many: A field typed as `List[T]` (or similar) becomes a relationship to `TDAO` with a foreign key on the child table.
- Many-to-many: ORMatic recognizes certain symmetric collection references and emits an association table to model many-to-many.
- Self-references: Dataclasses containing fields of their own type are supported, including parent-child trees and cyclic links.
- Backreferences: The generator configures both sides so that `dao.child.parent is dao_parent` works, and `from_dao()` restores the backreference in the reconstructed dataclass.

Guidelines for collections:
- Collections must not be optional and must not be nested collections of collections.
- Use a default factory for empty collections when the field may be “absent.”

### Inheritance and Polymorphism
- Joined-table inheritance is generated for class hierarchies.
- You can query for a base `*DAO` and get derived DAO rows thanks to polymorphic configuration.
- Only the first base class participates in polymorphic identity when using multiple inheritance.

Examples from tests:
- A `Position5DDAO` row appears in `select(PositionDAO)` results, and the set of “data columns” includes all inherited dimensions.

### Custom and Complex Field Types
- Enums: Fields typed as `Enum` are stored using SQLAlchemy’s `Enum` type. Reconstruction yields the original enum.
- User types: Field types that are not builtin scalars can be mapped through:
  - A nested dataclass mapping (preferred), or
  - A type decorator registered in `Base.type_mappings`, which tells ORMatic/SQLAlchemy how to persist the value.

### Alternative Mapping (Explicit Control)
If a dataclass does not fit the standard rules or requires a more specialized schema, define an explicit mapping by subclassing the relevant mapping base (see tests for `AlternativeMapping` usage) and include that mapping in the class set you pass to ORMatic. This lets you:
- Override column names or shapes
- Introduce association tables explicitly
- Adapt legacy schemas without changing your domain dataclasses

When both an implicit dataclass mapping and an explicit mapping exist, the explicit mapping takes precedence for that class.

### Error Handling and Diagnostics
- `NoDAOFoundError`: Raised when you try to `to_dao` a type that was not included in the generated interface. Fix by adding the dataclass (or its mapping) to the class set given to `ORMatic(...)`.
- Type errors during generation: Ensure fields adhere to the assumptions (no union beyond `Optional[T]`, no optional collections, no nested iterables).
- Polymorphic queries: In some versions of SQLAlchemy or certain inheritance layouts, querying base classes may require careful configuration. If a base query does not surface derived rows as expected, query the concrete DAO classes directly.

### Using Entity Query Language (EQL) With ORMatic
ORMatic can translate high-level EQL expressions into SQLAlchemy `select(...)` statements.

- Install and import `entity_query_language`.
- Build expressions over variables that carry the underlying Python type.
- Use `eql_to_sql(expr)` to get a SQLAlchemy statement and execute it with your session.

Example:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, configure_mappers

from entity_query_language.entity import let
from entity_query_language import or_, in_

from classes.example_classes import Position
from classes.sqlalchemy_interface import Base, PositionDAO

from ormatic.eql_interface import eql_to_sql

configure_mappers()
engine = create_engine('sqlite:///:memory:')
session = Session(engine)
Base.metadata.create_all(engine)

# Insert sample data
session.add_all([
    PositionDAO.to_dao(Position(1, 2, 3)),
    PositionDAO.to_dao(Position(1, 2, 4)),
    PositionDAO.to_dao(Position(2, 9, 10)),
])
session.commit()

# Build an EQL expression
position = let(type_=Position, domain=[Position(0, 0, 0)])  # domain is irrelevant for translation
expr = position.z > 3

# Translate and execute
stmt = eql_to_sql(expr)
rows = session.scalars(stmt).all()  # → PositionDAO rows with z > 3

# More complex logic
expr2 = or_(position.z == 4, position.x == 2)
stmt2 = eql_to_sql(expr2)
rows2 = session.scalars(stmt2).all()

# Membership
expr3 = in_(position.x, [1, 7])
stmt3 = eql_to_sql(expr3)
rows3 = session.scalars(stmt3).all()
```

Notes on the EQL translator:
- Variable resolution uses `ormatic.dao.get_dao_class` to map EQL variables to DAO classes.
- Attribute comparisons on a single table are supported, including `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, logical `and`/`or`, and `not`.
- If a variable’s DAO class cannot be found, a specific EQL translation error is raised to help diagnose missing mappings.

### Practical Tips and Best Practices
- Model with dataclasses first. Use small, value-oriented dataclasses, and let ORMatic discover relationships from nesting and lists.
- Keep collections simple. Use `list[T]` or `set[T]` and avoid nested collections.
- Use default factories. When a collection may be empty, define `field(default_factory=list)` or similar.
- Keep Optionals minimal. If a field can be absent, make it `Optional[T]`. For richer alternatives, consider separate subclasses.
- Make inheritance intentional. Put the “queryable” base class first in multiple inheritance to align polymorphic behavior with your expectations.
- Prefer explicit mappings when integrating with an existing database schema that does not match your domain shape.

### Limitations and Known Caveats
- Complex union types beyond `Optional[T]` are not supported. Model alternatives via subtyping.
- Optional or nested collections are not supported.
- Certain polymorphic base queries may require querying concrete DAOs; this depends on your inheritance tree and SQLAlchemy behavior.

### Frequently Asked Questions
- How do I exclude a field? Prefix it with `_`, for example `_cache: dict = field(default_factory=dict)`.
- How do I add a custom type? Register an appropriate SQLAlchemy `TypeDecorator` and include it in the generated `Base.type_mappings`, or wrap the type in its own dataclass and let ORMatic map it as a nested object.
- Can I keep my domain free of SQLAlchemy imports? Yes. The generated file is the only place that depends on SQLAlchemy.
- Can I mix explicit and implicit mappings? Yes. Explicit mappings override inferred ones for the same domain class.

### Troubleshooting Checklist
- Getting `NoDAOFoundError` when persisting: Did you include the class (or its mapping) in the set passed to `ORMatic`? Did you filter out `Enum` and non-dataclass types correctly?
- Collection fields not being created: Verify that the element type is a mapped dataclass and that the collection is not optional.
- Circular references fail to reconstruct: Ensure both ends of the relation are included in the mapping set and that backreferences are dataclass fields (not runtime-only `_` fields).

### Where To Look in the Code
- Template emission: `krrood/ormatic/templates/sqlalchemy_model.py.jinja` controls how DAO classes are spelled out.
- DAO utilities: `krrood/ormatic/dao.py` (and related) provide `DataAccessObject`, `to_dao`, `get_dao_class`, and `NoDAOFoundError`.
- EQL translation: `krrood/ormatic/eql_interface.py` defines the EQL→SQLAlchemy translator and its error types.

### Summary
ORMatic lets you keep writing clean, testable, object-oriented dataclasses while getting a full, type-driven SQLAlchemy layer for persistence and query. Conform to the rules above (or use explicit mappings where needed), generate once, and enjoy `to_dao`/`from_dao` conversions, relationships, inheritance, and optional EQL-driven queries without tangling your domain with persistence concerns.