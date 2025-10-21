import os.path

import pytest
from rdflib import Graph

from krrood.entity_query_language.entity import let, entity, an, contains, set_of
from krrood.entity_query_language.symbolic import symbolic_mode
from krrood.experiments.ood.lubm import Student, University, Department
from krrood.experiments.ood.owl_instance_loader import DatasetConverter


def test_owl_instance_loader():
    SPARQL_API = "http://localhost:7200/repositories/KRROOD"
    converter = DatasetConverter(sparql_endpoint=SPARQL_API)
    converter.convert()

    with symbolic_mode():
        student = let(Student)
        query = an(
            entity(
                student,
            )
        )

    print(len(list(query.evaluate())))
