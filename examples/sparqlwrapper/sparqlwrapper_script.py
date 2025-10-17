from SPARQLWrapper import SPARQLWrapper, JSON

# -------------------------
# SPARQL endpoint variable
# -------------------------
SPARQL_API = "http://sorin-MS-7E06:7200/repositories/15files"  # change to your endpoint


def run_query(query):
    """Helper to execute a SPARQL query and print results."""
    sparql = SPARQLWrapper(SPARQL_API)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    for result in results["results"]["bindings"]:
        print({k: v["value"] for k, v in result.items()})
    return results


# -------------------------
# Query 1
# -------------------------
def query_graduate_students():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:GraduateStudent .
  ?X ub:takesCourse <http://www.Department0.University0.edu/GraduateCourse0>
}
"""
    return run_query(query)


# -------------------------
# Query 2
# -------------------------
def query_students_universities_departments():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y ?Z
WHERE {
  ?X rdf:type ub:GraduateStudent .
  ?Y rdf:type ub:University .
  ?Z rdf:type ub:Department .
  ?X ub:memberOf ?Z .
  ?Z ub:subOrganizationOf ?Y .
  ?X ub:undergraduateDegreeFrom ?Y
}
"""
    return run_query(query)


# -------------------------
# Query 3
# -------------------------
def query_publications_by_assistant_professor():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:Publication .
  ?X ub:publicationAuthor <http://www.Department0.University0.edu/AssistantProfessor0>
}
"""
    return run_query(query)


# -------------------------
# Query 4
# -------------------------
def query_professor_info():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y1 ?Y2 ?Y3
WHERE {
  ?X rdf:type ub:Professor .
  ?X ub:worksFor <http://www.Department0.University0.edu> .
  ?X ub:name ?Y1 .
  ?X ub:emailAddress ?Y2 .
  ?X ub:telephone ?Y3
}
"""
    return run_query(query)


# -------------------------
# Query 5
# -------------------------
def query_persons_in_department0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:Person .
  ?X ub:memberOf <http://www.Department0.University0.edu>
}
"""
    return run_query(query)


# -------------------------
# Query 6
# -------------------------
def query_all_students():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X WHERE { ?X rdf:type ub:Student }
"""
    return run_query(query)


# -------------------------
# Query 7
# -------------------------
def query_students_taught_by_associate_professor0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y
WHERE {
  ?X rdf:type ub:Student .
  ?Y rdf:type ub:Course .
  ?X ub:takesCourse ?Y .
  <http://www.Department0.University0.edu/AssociateProfessor0> ub:teacherOf ?Y
}
"""
    return run_query(query)


# -------------------------
# Query 8
# -------------------------
def query_students_email_in_university0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y ?Z
WHERE {
  ?X rdf:type ub:Student .
  ?Y rdf:type ub:Department .
  ?X ub:memberOf ?Y .
  ?Y ub:subOrganizationOf <http://www.University0.edu> .
  ?X ub:emailAddress ?Z
}
"""
    return run_query(query)


# -------------------------
# Query 9
# -------------------------
def query_students_with_advisors_and_courses():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y ?Z
WHERE {
  ?X rdf:type ub:Student .
  ?Y rdf:type ub:Faculty .
  ?Z rdf:type ub:Course .
  ?X ub:advisor ?Y .
  ?Y ub:teacherOf ?Z .
  ?X ub:takesCourse ?Z
}
"""
    return run_query(query)


# -------------------------
# Query 10
# -------------------------
def query_students_in_graduatecourse0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:Student .
  ?X ub:takesCourse <http://www.Department0.University0.edu/GraduateCourse0>
}
"""
    return run_query(query)


# -------------------------
# Query 11
# -------------------------
def query_research_groups_university0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:ResearchGroup .
  ?X ub:subOrganizationOf <http://www.University0.edu>
}
"""
    return run_query(query)


# -------------------------
# Query 12
# -------------------------
def query_chairs_and_departments():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X ?Y
WHERE {
  ?X rdf:type ub:Chair .
  ?Y rdf:type ub:Department .
  ?X ub:worksFor ?Y .
  ?Y ub:subOrganizationOf <http://www.University0.edu>
}
"""
    return run_query(query)


# -------------------------
# Query 13
# -------------------------
def query_alumni_of_university0():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE {
  ?X rdf:type ub:Person .
  <http://www.University0.edu> ub:hasAlumnus ?X
}
"""
    return run_query(query)


# -------------------------
# Query 14
# -------------------------
def query_undergraduate_students():
    query = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>
SELECT ?X
WHERE { ?X rdf:type ub:UndergraduateStudent }
"""
    return run_query(query)


# -------------------------
# Pipeline
# -------------------------
def run_pipeline():
    print("=== Running all SPARQL queries ===")
    query_graduate_students()
    query_students_universities_departments()
    query_publications_by_assistant_professor()
    query_professor_info()
    query_persons_in_department0()
    query_all_students()
    query_students_taught_by_associate_professor0()
    query_students_email_in_university0()
    query_students_with_advisors_and_courses()
    query_students_in_graduatecourse0()
    query_research_groups_university0()
    query_chairs_and_departments()
    query_alumni_of_university0()
    query_undergraduate_students()


if __name__ == "__main__":
    run_pipeline()
