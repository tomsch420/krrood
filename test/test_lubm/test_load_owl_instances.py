import os

from krrood.experiments import lubm_with_predicates
from krrood.experiments.owl_instances_loader import load_instances


def test_load_owl_instances():

    instances_path = os.path.join("..", "resources", "lubm_instances.owl")
    load_instances(
        instances_path,
        model_module=lubm_with_predicates,
    )
