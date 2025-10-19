import os
from pathlib import Path

from krrood.experiments import lubm_with_predicates
from krrood.experiments.owl_instances_loader import load_instances


def test_load_owl_instances():

    folder_path = Path("..", "resources", "instances")
    files = [f.name for f in folder_path.iterdir() if f.is_file()]
    for file in files:
        load_instances(
            os.path.join(folder_path, file),
            model_module=lubm_with_predicates,
        )
