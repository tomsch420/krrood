.. ormatic_generation

Generating an ORMatic Interface
===============================

A typical workflow for generating an ORMatic interface consists of these two steps

Identify candidate classes
--------------------------

- Choose the dataclasses that represent your persistent domain.
- Optionally include explicit mapping classes
- Optionally provide custom type mappings

Create a script generating the interface
----------------------------------------

After identifying the persistent part of your domain, I recommend creating a script that generates the interface.
The script for generating the test ORM interface for KRROOD looks like this:

.. code-block:: python

    import os
    import logging
    from dataclasses import is_dataclass

    import krrood.entity_query_language.orm.model
    import krrood.entity_query_language.symbol_graph
    from krrood.class_diagrams.class_diagram import ClassDiagram
    from krrood.entity_query_language.predicate import Predicate, HasTypes, HasType
    from krrood.entity_query_language.symbolic import Variable
    from krrood.ormatic.dao import AlternativeMapping
    from krrood.ormatic.ormatic import ORMatic
    from krrood.ormatic.utils import classes_of_module, recursive_subclasses
    from krrood.ormatic.utils import drop_database

    from .dataset import example_classes, semantic_world_like_classes
    from .dataset.example_classes import (
        PhysicalObject,
        NotMappedParent,
        ChildNotMapped,
        ConceptType,
    )
    from .dataset.semantic_world_like_classes import *
    from .test_eql.conf.world.doors_and_drawers import World as DoorsAndDrawersWorld
    from .test_eql.conf.world.handles_and_containers import (
        World as HandlesAndContainersWorld,
    )

    # build the symbol graph
    Predicate.build_symbol_graph()
    symbol_graph = Predicate.symbol_graph

    # collect all classes
    all_classes = {c.clazz for c in symbol_graph._type_graph.wrapped_classes}
    all_classes |= {
        am.original_class() for am in recursive_subclasses(AlternativeMapping)
    }
    all_classes |= set(classes_of_module(krrood.entity_query_language.symbol_graph))
    all_classes |= {Symbol}

    # remove classes that don't need persistence
    all_classes -= {HasType, HasTypes}
    # remove classes that are not dataclasses
    all_classes = {c for c in all_classes if is_dataclass(c)}
    all_classes -= set(recursive_subclasses(PhysicalObject)) | {PhysicalObject}
    all_classes -= {NotMappedParent, ChildNotMapped}
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

