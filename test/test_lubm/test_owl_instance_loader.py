import os.path

import owlready2
import pytest

from krrood.experiments.ood.owl_instance_loader import DatasetConverter


@pytest.fixture(scope="session")
def world():
    world = owlready2.World()
    path_to_instances = os.path.join(
        os.path.dirname(__file__), "..", "..", "resources", "instances"
    )

    for filename in os.listdir(path_to_instances)[:1]:
        if filename.endswith(".owl"):
            onto = world.get_ontology(
                f"file://{os.path.join(path_to_instances, filename)}"
            ).load()

    owlready2.sync_reasoner_hermit(world, infer_property_values=True)
    return world


def test_owl_instance_loader(world):
    converter = DatasetConverter(world)
    converter.convert()
