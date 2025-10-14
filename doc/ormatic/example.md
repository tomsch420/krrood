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
from dataclasses import is_dataclass
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
all_classes = set(classes_of_module(example_classes))
all_classes |= set(classes_of_module(semantic_world_like_classes))
all_classes = {c for c in all_classes if is_dataclass(c)}
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
You can now use the interface to assert and retrieve facts from the database.
```python
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

from dataset.example_classes import *
from dataset.sqlalchemy_interface import *
from krrood.ormatic.dao import (
    to_dao
)
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
session = Session(engine)

k1 = KinematicChain("a")
k2 = KinematicChain("b")
torso = Torso("t", [k1, k2])
torso_dao = TorsoDAO.to_dao(torso)

session.add(torso_dao)
session.commit()

queried_torso = session.scalars(select(TorsoDAO)).one()
assert queried_torso == torso_dao
```
