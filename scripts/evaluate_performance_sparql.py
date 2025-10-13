from owlready2 import *

from krrood.experiments.helpers import evaluate_sparql
from krrood.experiments.lubm_sparql_queries import sparql_queries

if __name__ == "__main__":

    onto_file = os.path.join("..", "resources", "lubm_instances.owl")
    onto_iri = f"file://{onto_file}"

    print(f"Loading ontology from: {onto_iri}")
    onto = get_ontology(onto_iri).load()

    sync_reasoner_pellet(
        onto, infer_property_values=True, infer_data_property_values=True
    )

    result = evaluate_sparql(onto, sparql_queries)
    print(result)
