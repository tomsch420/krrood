import os
from dataclasses import is_dataclass
from enum import Enum

from krrood.class_diagrams.class_diagram import ClassDiagram
from krrood.entity_query_language import Predicate, HasType
from krrood.entity_query_language.predicate import HasTypes
from krrood.ormatic.ormatic import ORMatic
from krrood.ormatic.utils import classes_of_module, recursive_subclasses
from krrood.ormatic.dao import AlternativeMapping, DataAccessObject
import krrood.entity_query_language.orm.model
import krrood.entity_query_language.symbol_graph


# get all classes in the dataset modules
Predicate.build_symbol_graph()
symbol_graph = Predicate.symbol_graph
all_classes = {c.clazz for c in symbol_graph._type_graph.wrapped_classes}
all_classes |= {am.original_class() for am in recursive_subclasses(AlternativeMapping)}
all_classes |= set(classes_of_module(krrood.entity_query_language.symbol_graph))

# remove classes that don't need persistence
all_classes -= {HasType, HasTypes}
# remove classes that are not dataclasses
all_classes = {c for c in all_classes if is_dataclass(c)}

print(all_classes)
# sort the classes to ensure consistent ordering in the generated file
class_diagram = ClassDiagram(
    list(sorted(all_classes, key=lambda c: c.__name__, reverse=True))
)

instance = ORMatic(
    class_dependency_graph=class_diagram,
    alternative_mappings=recursive_subclasses(AlternativeMapping),
)

instance.make_all_tables()

file_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "src",
    "krrood",
    "entity_query_language",
    "orm",
    "ormatic_interface.py",
)

with open(file_path, "w") as f:
    instance.to_sqlalchemy_file(f)
