from dataclasses import dataclass

import owlready2


@dataclass
class DatasetConverter:
    world: owlready2.World

    def convert(self):
        onto = self.world.get_ontology(
            "http://swat.cse.lehigh.edu/onto/univ-bench.owl#"
        )
        university = onto.University.instances()[0]
        print(university)
