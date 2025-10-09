import os

from krrood.experiments import lubm_with_predicates
from krrood.experiments.helpers import evaluate_eql
from krrood import get_eql_queries
from krrood import load_instances

if __name__ == "__main__":
    # load instances
    _ = load_instances(
        os.path.join("..", "resources", "lubm_instances.owl"), lubm_with_predicates
    )
    evaluate_eql(get_eql_queries())
