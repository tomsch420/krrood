from dataclasses import dataclass

import owlready2


@dataclass
class DatasetConverter:
    world: owlready2.World

    @property
    def ontology(self):
        return self.world.get_ontology(
            "http://swat.cse.lehigh.edu/onto/univ-bench.owl#"
        )

    def convert(self):
        university = self.ontology.University.instances()[0]
        # get all departments of this university

        departments_in_university = list(
            self.ontology.search(
                is_a=self.ontology.Department, subOrganizationOf=university
            )
        )
        print(departments_in_university)
