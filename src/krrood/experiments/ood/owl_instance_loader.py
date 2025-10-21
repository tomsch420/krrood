from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

import tqdm

from .lubm import (
    University,
    Department,
    Course,
    GraduateCourse,
    ResearchGroup,
    Person,
    Publication,
    FullProfessor,
    AssociateProfessor,
    AssistantProfessor,
    Lecturer,
    Professor,
    Student,
    TeachingAssistant,
    ResearchAssistant,
)


@dataclass
class _SparqlClient:
    """
    Minimal SPARQL client abstraction.

    Executes SELECT queries against either an in-memory rdflib Graph or a
    SPARQL HTTP endpoint via SPARQLWrapper.
    """

    graph: Optional[Any] = None
    endpoint: Optional[str] = None

    def select(self, query: str) -> List[Dict[str, str]]:
        """
        Execute a SPARQL SELECT query and return rows as dictionaries with string values.
        """
        if self.graph is not None:
            results = self.graph.query(query)
            rows: List[Dict[str, str]] = []
            for row in results:
                as_dict = row.asdict()
                rows.append({str(k): str(v) for k, v in as_dict.items()})
            return rows

        if self.endpoint is not None:
            from SPARQLWrapper import SPARQLWrapper, JSON  # type: ignore

            sparql = SPARQLWrapper(self.endpoint)
            sparql.setQuery(query)
            sparql.setReturnFormat(JSON)
            results = sparql.query().convert()
            rows: List[Dict[str, str]] = []
            for b in results.get("results", {}).get("bindings", []):
                row: Dict[str, str] = {}
                for k, v in b.items():
                    row[k] = v.get("value")
                rows.append(row)
            return rows

        return []


class DatasetConversionConfigurationError(Exception):
    """Raised when the dataset conversion is misconfigured.

    Currently unused to preserve backward compatibility: the converter
    returns an empty result if no SPARQL source is configured.
    """


@dataclass
class DatasetConverter:
    """
    Converts LUBM instances into in-memory Python dataclasses defined in
    lubm.py using SPARQL only (no Owlready2 dependency).

    You can either provide a SPARQL HTTP endpoint via ``sparql_endpoint``
    or an in-memory rdflib Graph via ``sparql_graph``. If both are given,
    the in-memory graph takes precedence.
    """

    sparql_graph: Optional[Any] = None
    sparql_endpoint: Optional[str] = None

    # Internal caches to ensure 1:1 mapping between source instances and Python objects

    # Internal caches to ensure 1:1 mapping between source instances and Python objects
    _uni_map: Dict[Any, University] = field(
        default_factory=dict, init=False, repr=False
    )
    _dept_map: Dict[Any, Department] = field(
        default_factory=dict, init=False, repr=False
    )
    _prof_map: Dict[Any, Professor] = field(
        default_factory=dict, init=False, repr=False
    )
    _lect_map: Dict[Any, Lecturer] = field(default_factory=dict, init=False, repr=False)
    _course_map: Dict[Any, Course] = field(default_factory=dict, init=False, repr=False)
    _pub_map: Dict[Any, Publication] = field(
        default_factory=dict, init=False, repr=False
    )
    _student_map: Dict[Any, Student] = field(
        default_factory=dict, init=False, repr=False
    )
    _client: _SparqlClient = field(init=False, repr=False, default=None)  # type: ignore

    def __post_init__(self) -> None:
        """Initialize internal SPARQL client based on provided configuration."""
        self._client = _SparqlClient(graph=self.sparql_graph, endpoint=self.sparql_endpoint)

    @property
    def _prefix(self) -> str:
        """Common SPARQL prefixes used throughout conversion."""
        return (
            "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
            "PREFIX ub: <http://swat.cse.lehigh.edu/onto/univ-bench.owl#>\n"
        )

    def _local_name(self, entity) -> str:
        """
        Returns the local name of an IRI string (or a named object with ``name``).
        """
        if isinstance(entity, str):
            frag = entity.split("#")[-1]
            return frag.split("/")[-1]
        # Fallback for any object that may carry a name attribute
        return getattr(entity, "name", str(entity))

    # --- Mapping helpers ---

    def _get_or_create_university(self, u) -> University:
        if u in self._uni_map:
            return self._uni_map[u]
        py_u = University(name=self._local_name(u))
        self._uni_map[u] = py_u
        return py_u

    def _get_or_create_department(self, d, py_university: University) -> Department:
        if d in self._dept_map:
            return self._dept_map[d]
        py_d = Department(name=self._local_name(d), university=py_university)
        self._dept_map[d] = py_d
        return py_d

    def _get_or_create_publication(self, p) -> Publication:
        if p in self._pub_map:
            return self._pub_map[p]
        pub = Publication(title=self._local_name(p), year=0)
        self._pub_map[p] = pub
        return pub

    def _build_person(self, individual_iri: str) -> Person:
        return Person(first_name=self._local_name(individual_iri), last_name="")

    # --- SPARQL helpers ---

    def _sparql_select(self, query: str) -> List[Dict[str, str]]:
        """Execute a SPARQL SELECT query via the configured client."""
        return self._client.select(query)

    def _is_graduate_course_via_sparql(self, course_iri: str) -> bool:
        q = (
            self._prefix
            + f"SELECT ?c WHERE {{ ?c rdf:type ub:GraduateCourse . FILTER(?c = <{course_iri}>) }}"
        )
        rows = self._sparql_select(q)
        return len(rows) > 0

    # --- Query builders / assemblers (extracted to reduce complexity) ---

    def _departments_for_university(self, u_iri: str) -> List[str]:
        q = (
            self._prefix
            + f"SELECT ?d WHERE {{ ?d rdf:type ub:Department . ?d ub:subOrganizationOf <{u_iri}> }}"
        )
        return [row["d"] for row in self._sparql_select(q)]

    def _add_research_groups(self, dept_py: Department, d_iri: str) -> None:
        q = (
            self._prefix
            + f"SELECT ?g WHERE {{ ?g rdf:type ub:ResearchGroup . ?g ub:subOrganizationOf <{d_iri}> }}"
        )
        for row in self._sparql_select(q):
            dept_py.research_groups.append(
                ResearchGroup(name=self._local_name(row["g"]), lead=None, department=dept_py)
            )

    def _degree_universities(self, person_iri: str, default_uni: University) -> tuple[University, University, University]:
        q = (
            self._prefix
            + f"SELECT ?ug ?ms ?dr WHERE {{ OPTIONAL {{ <{person_iri}> ub:undergraduateDegreeFrom ?ug }} . OPTIONAL {{ <{person_iri}> ub:mastersDegreeFrom ?ms }} . OPTIONAL {{ <{person_iri}> ub:doctoralDegreeFrom ?dr }} }}"
        )
        rows = self._sparql_select(q)
        ug_py = ms_py = dr_py = None
        if rows:
            ug_iri = rows[0].get("ug")
            ms_iri = rows[0].get("ms")
            dr_iri = rows[0].get("dr")
            if ug_iri:
                ug_py = self._get_or_create_university(ug_iri)
            if ms_iri:
                ms_py = self._get_or_create_university(ms_iri)
            if dr_iri:
                dr_py = self._get_or_create_university(dr_iri)
        return (
            ug_py or default_uni,
            ms_py or default_uni,
            dr_py or default_uni,
        )

    def _course_from_iri(self, c_iri: str, dept_py: Department) -> Course:
        cached = self._course_map.get(c_iri)
        if cached is not None:
            return cached
        is_grad = self._is_graduate_course_via_sparql(c_iri)
        if is_grad:
            course = GraduateCourse(name=self._local_name(c_iri), department=dept_py)
            self._course_map[c_iri] = course
            if course not in dept_py.graduate_courses:
                dept_py.graduate_courses.append(course)  # type: ignore[arg-type]
            return course
        course = Course(name=self._local_name(c_iri), department=dept_py)
        self._course_map[c_iri] = course
        if course not in dept_py.undergraduate_courses:
            dept_py.undergraduate_courses.append(course)
        return course

    def _build_faculty_of_type(self, type_name: str, ctor, d_iri: str, dept_py: Department, u_py: University) -> List[Professor | Lecturer]:
        q = self._prefix + f"SELECT ?x WHERE {{ ?x rdf:type ub:{type_name} . ?x ub:worksFor <{d_iri}> }}"
        roles: List[Professor | Lecturer] = []
        for row in self._sparql_select(q):
            x_iri = row["x"]
            ug_py, ms_py, dr_py = self._degree_universities(x_iri, u_py)
            person = self._build_person(x_iri)
            role = ctor(
                person=person,
                undergraduate_degree_from=ug_py,
                masters_degree_from=ms_py,
                doctoral_degree_from=dr_py,
                department=dept_py,
            )
            # Publications
            pubs_q = self._prefix + f"SELECT ?p WHERE {{ ?p rdf:type ub:Publication . ?p ub:publicationAuthor <{x_iri}> }}"
            for prow in self._sparql_select(pubs_q):
                role.publications.append(self._get_or_create_publication(prow["p"]))
            # Courses taught
            teach_q = self._prefix + f"SELECT ?c WHERE {{ <{x_iri}> ub:teacherOf ?c }}"
            for crow in self._sparql_select(teach_q):
                course = self._course_from_iri(crow["c"], dept_py)
                if isinstance(course, GraduateCourse):
                    role.teaches_graduate_courses.append(course)
                else:
                    role.teaches_courses.append(course)
            roles.append(role)
            if isinstance(role, Professor):
                self._prof_map[x_iri] = role
            if isinstance(role, Lecturer):
                self._lect_map[x_iri] = role
        return roles

    def _assign_department_head(self, dept_py: Department, d_iri: str) -> None:
        q = self._prefix + f"SELECT ?h WHERE {{ ?h rdf:type ub:FullProfessor . ?h ub:headOf <{d_iri}> }}"
        rows = self._sparql_select(q)
        if not rows:
            return
        head_local = self._local_name(rows[0]["h"])
        for fp in dept_py.full_professors:
            if fp.person.first_name == head_local:
                dept_py.head = fp
                break

    def _build_student(self, s_iri: str, is_grad: bool, dept_py: Department) -> Student:
        person = self._build_person(s_iri)
        ug_py_local = None
        if is_grad:
            q = self._prefix + f"SELECT ?ug WHERE {{ <{s_iri}> ub:undergraduateDegreeFrom ?ug }}"
            rows = self._sparql_select(q)
            if rows:
                ug_py_local = self._get_or_create_university(rows[0]["ug"])
        student = Student(
            person=person,
            department=dept_py,
            advisor=None,
            undergraduate_degree_from=ug_py_local,
        )
        # Advisor
        adv_q = self._prefix + f"SELECT ?a WHERE {{ <{s_iri}> ub:advisor ?a }}"
        adv_rows = self._sparql_select(adv_q)
        if adv_rows:
            adv_iri = adv_rows[0]["a"]
            advisor = self._prof_map.get(adv_iri)
            if advisor is not None:
                student.advisor = advisor
                advisor.advised_students.append(student)
        # Courses
        take_q = self._prefix + f"SELECT ?c WHERE {{ <{s_iri}> ub:takesCourse ?c }}"
        for crow in self._sparql_select(take_q):
            course = self._course_from_iri(crow["c"], dept_py)
            if isinstance(course, GraduateCourse):
                student.takes_graduate_courses.append(course)
            else:
                student.takes_courses.append(course)
        # Publications (co-authored)
        pubs_q = self._prefix + f"SELECT ?p WHERE {{ ?p rdf:type ub:Publication . ?p ub:publicationAuthor <{s_iri}> }}"
        for prow in self._sparql_select(pubs_q):
            student.co_authored_publications.append(self._get_or_create_publication(prow["p"]))
        return student

    def _build_students_for_department(self, dept_py: Department, d_iri: str) -> List[Student]:
        students: List[Student] = []
        grad_q = self._prefix + f"SELECT ?s WHERE {{ ?s rdf:type ub:GraduateStudent . ?s ub:memberOf <{d_iri}> }}"
        for row in self._sparql_select(grad_q):
            s_iri = row["s"]
            st = self._build_student(s_iri, True, dept_py)
            students.append(st)
            self._student_map[self._local_name(s_iri)] = st
        ugr_q = self._prefix + f"SELECT ?s WHERE {{ ?s rdf:type ub:UndergraduateStudent . ?s ub:memberOf <{d_iri}> }}"
        for row in self._sparql_select(ugr_q):
            s_iri = row["s"]
            st = self._build_student(s_iri, False, dept_py)
            students.append(st)
            self._student_map[self._local_name(s_iri)] = st
        return students

    def _attach_tas(self, dept_py: Department) -> None:
        q = self._prefix + "SELECT ?ta ?course WHERE { ?ta rdf:type ub:TeachingAssistant . ?ta ub:teachingAssistantOf ?course }"
        for row in self._sparql_select(q):
            course_iri = row["course"]
            course = self._course_map.get(course_iri)
            if course is not None and course.department is dept_py:
                st = self._student_map.get(self._local_name(row["ta"]))
                if st is not None:
                    _ = TeachingAssistant(graduate_student=st, course_assistant_for=course)

    def _attach_ras(self, dept_py: Department) -> None:
        q = self._prefix + "SELECT ?ra ?org WHERE { ?ra rdf:type ub:ResearchAssistant . ?ra ub:worksFor ?org }"
        for row in self._sparql_select(q):
            org_local = self._local_name(row["org"])
            if any(g.name == org_local for g in dept_py.research_groups):
                st = self._student_map.get(self._local_name(row["ra"]))
                if st is not None:
                    _ = ResearchAssistant(graduate_student=st)

    def convert(self) -> List[University]:
        """
        Converts the dataset into a list of Universities with populated structure
        using SPARQL (endpoint or in-memory rdflib graph). Returns an empty list
        if neither a graph nor an endpoint is configured.
        """
        return self._convert_via_sparql()

    def _convert_via_sparql(self) -> List[University]:
        """
        Convert by querying a SPARQL endpoint or rdflib graph using SPARQL.
        This orchestration delegates cohesive tasks to dedicated methods,
        lowering cyclomatic complexity while preserving behavior.
        """
        # 1) Universities
        uni_rows = self._sparql_select(self._prefix + "SELECT ?u WHERE { ?u rdf:type ub:University }")
        for row in uni_rows:
            self._get_or_create_university(row["u"])  # use IRI as key

        # 2) For each university, process departments and nested structure
        for u_iri, u_py in tqdm.tqdm(list(self._uni_map.items())):
            for d_iri in self._departments_for_university(u_iri):
                dept_py = self._get_or_create_department(d_iri, u_py)

                # Research groups
                self._add_research_groups(dept_py, d_iri)

                # Faculty by rank
                dept_py.full_professors = self._build_faculty_of_type("FullProfessor", FullProfessor, d_iri, dept_py, u_py)
                dept_py.associate_professors = self._build_faculty_of_type("AssociateProfessor", AssociateProfessor, d_iri, dept_py, u_py)
                dept_py.assistant_professors = self._build_faculty_of_type("AssistantProfessor", AssistantProfessor, d_iri, dept_py, u_py)
                dept_py.lecturers = self._build_faculty_of_type("Lecturer", Lecturer, d_iri, dept_py, u_py)

                # Department head
                self._assign_department_head(dept_py, d_iri)

                # Students
                dept_py.students = self._build_students_for_department(dept_py, d_iri)

                # Teaching and research assistants
                self._attach_tas(dept_py)
                self._attach_ras(dept_py)

                if dept_py not in u_py.departments:
                    u_py.departments.append(dept_py)

        return list(self._uni_map.values())
