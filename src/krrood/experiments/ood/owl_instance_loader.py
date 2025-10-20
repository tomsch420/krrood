from dataclasses import dataclass, field
from typing import Dict, List, Any

import owlready2
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
class DatasetConverter:
    """
    Converts an OWLReady2 world containing LUBM instances into in-memory
    Python dataclasses defined in lubm.py.

    The converter preserves the organizational structure (Universities,
    Departments, ResearchGroups), roles (Professors, Lecturers, Students),
    and relationships (advisor, courses taught/taken, heads of departments,
    sub-organization links, publications, and degrees) so the generated
    objects behave similarly to the original OWL dataset.
    """

    world: owlready2.World

    # Internal caches to ensure 1:1 mapping between OWL instances and Python objects
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

    @property
    def ontology(self):
        """
        Returns the Univ-Bench ontology loaded in the world.
        """
        return self.world.get_ontology(
            "http://swat.cse.lehigh.edu/onto/univ-bench.owl#"
        )

    def _local_name(self, entity) -> str:
        """
        Returns the local name of an OWL entity.
        """
        return entity.name

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
        # Use the OWL individual's name as title; year unknown in LUBM base
        pub = Publication(title=self._local_name(p), year=0)
        self._pub_map[p] = pub
        return pub

    def _get_or_create_course(self, c, dept: Department) -> Course:
        if c in self._course_map:
            return self._course_map[c]
        # Determine if this course is a GraduateCourse
        is_grad = False
        try:
            # Owlready2 allows isinstance checks against ontology classes
            is_grad = isinstance(c, self.ontology.GraduateCourse)
        except Exception:
            is_grad = False
        if is_grad:
            py_c = GraduateCourse(name=self._local_name(c), department=dept)
        else:
            py_c = Course(name=self._local_name(c), department=dept)
        self._course_map[c] = py_c
        # Also add to department lists if not already present
        if isinstance(py_c, GraduateCourse):
            if py_c not in dept.graduate_courses:
                dept.graduate_courses.append(py_c)
        else:
            if py_c not in dept.undergraduate_courses:
                dept.undergraduate_courses.append(py_c)
        return py_c

    def _build_person(self, individual) -> Person:
        # Owlready2 individuals often have technical names; we store them as first_name
        # and leave last_name empty to keep interfaces consistent.
        return Person(first_name=self._local_name(individual), last_name="")

    def _create_faculty(
        self, cls, individual, dept: Department
    ) -> Professor | Lecturer:
        person = self._build_person(individual)
        # Degrees (for faculty we expect all to be present in LUBM instances)
        ug = None
        ms = None
        dr = None
        if individual.undergraduateDegreeFrom:
            ug = self._get_or_create_university(individual.undergraduateDegreeFrom[0])
        if individual.mastersDegreeFrom:
            ms = self._get_or_create_university(individual.mastersDegreeFrom[0])
        if individual.doctoralDegreeFrom:
            dr = self._get_or_create_university(individual.doctoralDegreeFrom[0])

        # Fallbacks: if any degree missing, reuse available university or department's university
        base_uni = dept.university
        ug = ug or base_uni
        ms = ms or base_uni
        dr = dr or base_uni

        role = cls(
            person=person,
            undergraduate_degree_from=ug,
            masters_degree_from=ms,
            doctoral_degree_from=dr,
            department=dept,
        )

        # Publications authored by this faculty member
        authored = list(
            self.ontology.search(
                is_a=self.ontology.Publication, publicationAuthor=individual
            )
        )
        for pub in authored:
            role.publications.append(self._get_or_create_publication(pub))

        # Courses taught by this faculty member
        for c in individual.teacherOf:
            py_c = self._get_or_create_course(c, dept)
            # Assign to correct list (grad or undergrad)
            if isinstance(py_c, GraduateCourse):
                role.teaches_graduate_courses.append(py_c)
            else:
                role.teaches_courses.append(py_c)

        return role

    def _ensure_department_faculty(self, dept_owl, dept_py: Department):
        # Full professors
        fulls = list(
            self.ontology.search(is_a=self.ontology.FullProfessor, worksFor=dept_owl)
        )
        dept_py.full_professors = [
            self._create_faculty(FullProfessor, f, dept_py) for f in fulls
        ]

        # Associate professors
        associates = list(
            self.ontology.search(
                is_a=self.ontology.AssociateProfessor, worksFor=dept_owl
            )
        )
        dept_py.associate_professors = [
            self._create_faculty(AssociateProfessor, a, dept_py) for a in associates
        ]

        # Assistant professors
        assistants = list(
            self.ontology.search(
                is_a=self.ontology.AssistantProfessor, worksFor=dept_owl
            )
        )
        dept_py.assistant_professors = [
            self._create_faculty(AssistantProfessor, a, dept_py) for a in assistants
        ]

        # Lecturers
        lecturers = list(
            self.ontology.search(is_a=self.ontology.Lecturer, worksFor=dept_owl)
        )
        dept_py.lecturers = [
            self._create_faculty(Lecturer, l, dept_py) for l in lecturers
        ]

        # Cache professor roles for advisor linking
        for p in dept_py.all_professors:
            self._prof_map[p.person.first_name] = p  # key by local name string
        for l in dept_py.lecturers:
            self._lect_map[l.person.first_name] = l

        # Department head (a FullProfessor with headOf relation)
        heads = list(
            self.ontology.search(is_a=self.ontology.FullProfessor, headOf=dept_owl)
        )
        if heads:
            head_local = self._local_name(heads[0])
            # Map back to created FullProfessor by person local name
            for fp in dept_py.full_professors:
                if fp.person.first_name == head_local:
                    dept_py.head = fp
                    break

    def _ensure_department_research_groups(self, dept_owl, dept_py: Department):
        groups = list(
            self.ontology.search(
                is_a=self.ontology.ResearchGroup, subOrganizationOf=dept_owl
            )
        )
        for g in groups:
            dept_py.research_groups.append(
                ResearchGroup(name=self._local_name(g), lead=None, department=dept_py)
            )

    def _create_or_get_course_for_student(
        self, course_owl, dept_py: Department
    ) -> Course:
        return self._get_or_create_course(course_owl, dept_py)

    def _create_student(self, s_owl, dept_py: Department, is_graduate: bool) -> Student:
        person = self._build_person(s_owl)
        undergrad_uni = None
        if is_graduate and s_owl.undergraduateDegreeFrom:
            undergrad_uni = self._get_or_create_university(
                s_owl.undergraduateDegreeFrom[0]
            )

        student = Student(
            person=person,
            department=dept_py,
            advisor=None,
            undergraduate_degree_from=undergrad_uni,
        )

        # Advisor (if present)
        if s_owl.advisor:
            # The advisor individual may be any Professor subclass
            advisor_ind = s_owl.advisor[0]
            advisor_local = self._local_name(advisor_ind)
            advisor = self._prof_map.get(advisor_local)
            if advisor:
                student.advisor = advisor
                advisor.advised_students.append(student)

        # Courses taken
        for c in s_owl.takesCourse:
            py_c = self._create_or_get_course_for_student(c, dept_py)
            if isinstance(py_c, GraduateCourse):
                student.takes_graduate_courses.append(py_c)
            else:
                student.takes_courses.append(py_c)

        # Publications authored by the student (treated as co-authored publications)
        authored = list(
            self.ontology.search(
                is_a=self.ontology.Publication, publicationAuthor=s_owl
            )
        )
        for pub in authored:
            student.co_authored_publications.append(
                self._get_or_create_publication(pub)
            )

        return student

    def _ensure_department_students(self, dept_owl, dept_py: Department):
        # Graduate students
        grads = list(
            self.ontology.search(is_a=self.ontology.GraduateStudent, memberOf=dept_owl)
        )
        # Undergraduates
        undergrads = list(
            self.ontology.search(
                is_a=self.ontology.UndergraduateStudent, memberOf=dept_owl
            )
        )

        created_students: List[Student] = []
        for gs in grads:
            st = self._create_student(gs, dept_py, is_graduate=True)
            created_students.append(st)
            self._student_map[self._local_name(gs)] = st
        for us in undergrads:
            st = self._create_student(us, dept_py, is_graduate=False)
            created_students.append(st)
            self._student_map[self._local_name(us)] = st

        dept_py.students = created_students

        # Teaching assistants linked to courses of this department
        tas = list(self.ontology.search(is_a=self.ontology.TeachingAssistant))
        for ta in tas:
            if not ta.teachingAssistantOf:
                continue
            course_ind = ta.teachingAssistantOf[0]
            # Only consider if the course belongs to this department
            py_course = self._course_map.get(course_ind)
            if py_course and py_course.department is dept_py:
                st = self._student_map.get(self._local_name(ta))
                if st:
                    _ = TeachingAssistant(
                        graduate_student=st, course_assistant_for=py_course
                    )

        # Research assistants linked to research groups of this department
        ras = list(self.ontology.search(is_a=self.ontology.ResearchAssistant))
        for ra in ras:
            if not ra.worksFor:
                continue
            org = ra.worksFor[0]
            # Only consider if worksFor is a ResearchGroup under this department
            belong_groups = [
                g for g in dept_py.research_groups if self._local_name(org) == g.name
            ]
            if belong_groups:
                st = self._student_map.get(self._local_name(ra))
                if st:
                    _ = ResearchAssistant(graduate_student=st)

    def convert(self) -> List[University]:
        """
        Converts the world into a list of Universities with populated structure.
        """
        onto = self.ontology

        # Create Python University objects for all OWL University individuals
        for u in onto.University.instances():
            self._get_or_create_university(u)

        # For each University, construct its departments and nested structures
        for u_owl, u_py in tqdm.tqdm(list(self._uni_map.items())):
            # Departments that are subOrganizationOf this University
            dept_owls = list(onto.search(is_a=onto.Department, subOrganizationOf=u_owl))
            for d in dept_owls:
                dept_py = self._get_or_create_department(d, u_py)

                # Ensure research groups (subOrganizationOf Department)
                self._ensure_department_research_groups(d, dept_py)

                # Ensure faculty for this department
                self._ensure_department_faculty(d, dept_py)

                # Students and their relationships
                self._ensure_department_students(d, dept_py)

                # Courses might already be partially discovered via faculty/student links;
                # nothing further required here as _get_or_create_course attaches them to the department.

                # Finally, add the department to the University if not present
                if dept_py not in u_py.departments:
                    u_py.departments.append(dept_py)

        # Return all universities (some may have no departments; still valid as degree sources)
        return list(self._uni_map.values())
