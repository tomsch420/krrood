from __future__ import annotations


from dataclasses import dataclass, field
from typing import List, Optional, Type
import random
import uuid

from .lubm import (
    University,
    Student,
    FacultyMember,
    Person,
    Publication,
    TFacultyRole,
    FullProfessor,
    AssociateProfessor,
    AssistantProfessor,
    Lecturer,
    Department,
    Course,
    GraduateCourse,
    ResearchGroup,
    Professor,
    TeachingAssistant,
    ResearchAssistant,
    DepartmentName,
    UniversityName,
    FirstName,
    LastName,
    Gender,
    PublicationAdjective,
    PublicationNoun,
)


@dataclass
class Range:
    min: float
    max: float


@dataclass
class GeneratorConfiguration:
    """Configuration for customizing the LUBM data generator.

    Controls all parameters for generating university benchmark data according
    to the LUBM specification, including faculty counts, student ratios,
    course assignments, and publication counts.
    """

    universities: Range = field(default_factory=lambda: Range(1, 15))
    """
    The min/max number of universities.
    """

    departments: Range = field(default_factory=lambda: Range(15, 25))
    """
    The min/max number of departments per university.
    These departments all belong to the same university.
    """

    full_professors: Range = field(default_factory=lambda: Range(7, 10))
    """
    The min/max number of full professors per department.
    One of these professors is the head of the department.
    """

    associate_professors: Range = field(default_factory=lambda: Range(10, 14))
    """
    The min/max number of associate_professors per department.
    """

    assistant_professors: Range = field(default_factory=lambda: Range(8, 11))
    """
    The min/max number of assistant_professors per department.
    """

    lecturers: Range = field(default_factory=lambda: Range(5, 7))
    """
    The min/max number of lecturers per department.
    """

    research_groups: Range = field(default_factory=lambda: Range(10, 20))
    """
    The min/max number of research groups per department.
    """

    probability_graduate_student_is_teaching_assistant: Range = field(
        default_factory=lambda: Range(1 / 5, 1 / 4)
    )
    """
    The min/max probability that a graduate student is a teaching assistant.
    """

    probability_graduate_student_is_research_assistant: Range = field(
        default_factory=lambda: Range(1 / 4, 1 / 3)
    )
    """
    The probability that a graduate student is a research assistant.
    """

    # Unified configuration to control undergrad degree source for graduate students
    probability_grad_undergrad_same_university: float = 0.5
    """
    Probability that a graduate student has their undergraduate degree from the same university that their department belongs to.
    If 0.0, degrees are never sourced from main universities (external only). If > 0.0, main
    universities are allowed and this value is the probability of picking the current university.
    Value should be between 0.0 and 1.0.
    """

    seed: Optional[int] = None
    """
    A seed for the random number generator.
    """


@dataclass
class UniversityDataGenerator:
    """
    Generates instances of the University model based on the provided constraints.
    Uses simple randomized data generation.
    """

    # --- Simulated Data Pools moved to enums in lubm.py ---

    # Configuration and input parameters
    university_count: Optional[int] = None
    seed: Optional[int] = 42
    config: GeneratorConfiguration = field(default_factory=GeneratorConfiguration)

    # Generated collections
    all_universities: List[University] = field(default_factory=list, init=False)
    all_external_universities: List[University] = field(
        default_factory=list, init=False
    )
    all_faculty: List[FacultyMember] = field(default_factory=list, init=False)
    all_students: List[Student] = field(default_factory=list, init=False)

    # --- Helper Functions for Random Data ---

    def _randint_from_range(self, r: Range) -> int:
        """Returns a random integer within the inclusive range."""
        return random.randint(int(r.min), int(r.max))

    def _random_uniform_from_range(self, r: Range) -> float:
        """Returns a random float within the inclusive range."""
        return random.uniform(float(r.min), float(r.max))

    def _get_random_name(self, gender: str) -> Person:
        """Generates a random Person."""
        first = random.choice(list(FirstName)).value
        last = random.choice(list(LastName)).value
        return Person(first_name=first, last_name=last, gender=gender)

    def _get_random_university(self) -> University:
        """Generates a simple University entity for degree purposes."""
        return University(
            name=f"{random.choice(list(UniversityName)).value} {random.randint(1, 99)}"
        )

    def _get_random_publication(self) -> Publication:
        """Generates a random Publication."""
        title = f"{random.choice(list(PublicationAdjective)).value} {random.choice(list(PublicationNoun)).value} of {uuid.uuid4().hex[:6]}"
        year = random.randint(2000, 2024)
        return Publication(title=title, year=year)

    def _create_degree_universities(self, count: int = 20):
        """Creates external university entities for degree sources."""
        self.all_external_universities = [
            self._get_random_university() for _ in range(count)
        ]

    def _pick_undergrad_university(self, current_university: University) -> University:
        """Selects a university for a graduate student's undergraduate degree.

        Prefers the current university with a configurable probability and,
        otherwise, selects from a pool consisting of external universities and,
        when allowed by probability > 0, main universities as well.
        """
        # Clamp probability to [0.0, 1.0]
        prob = max(
            0.0, min(1.0, self.config.probability_grad_undergrad_same_university)
        )

        # If probability triggers, return the same university
        if prob > 0.0 and random.random() < prob:
            return current_university

        # Build the selection pool
        pool: List[University] = list(self.all_external_universities)
        # If prob == 0.0, we do not allow degrees from main universities
        if prob > 0.0:
            pool.extend(self.all_universities)

        # Fallbacks if pool is empty (should not happen in normal flow)
        if not pool:
            return current_university

        return random.choice(pool)

    # --- Generation Logic ---

    def _generate_publications_for_faculty(self, role: TFacultyRole):
        """Assigns publications based on faculty rank constraints."""

        if isinstance(role, FullProfessor):
            pub_range = (15, 20)
        elif isinstance(role, AssociateProfessor):
            pub_range = (10, 18)
        elif isinstance(role, AssistantProfessor):
            pub_range = (5, 10)
        elif isinstance(role, Lecturer):
            pub_range = (0, 5)
        else:
            return

        num_pubs = random.randint(*pub_range)
        role.publications.extend(
            [self._get_random_publication() for _ in range(num_pubs)]
        )

    def _generate_faculty_member(
        self, role_class: Type[TFacultyRole], dept: Department
    ) -> TFacultyRole:
        """Creates a FacultyMember object with degrees and publications."""
        person = self._get_random_name(random.choice(list(Gender)).value)

        # All degrees must be from a University (randomly selected from external pool)
        ug_univ = random.choice(self.all_external_universities)
        ms_univ = random.choice(self.all_external_universities)
        dr_univ = random.choice(self.all_external_universities)

        # Create the role instance
        faculty_role = role_class(
            person=person,
            undergraduate_degree_from=ug_univ,
            masters_degree_from=ms_univ,
            doctoral_degree_from=dr_univ,
            department=dept,
        )

        # Assign publications
        self._generate_publications_for_faculty(faculty_role)

        self.all_faculty.append(faculty_role)
        return faculty_role

    def _generate_student(self, dept: Department, is_graduate: bool) -> Student:
        """Creates a Student object.

        When is_graduate is True, the student represents a graduate student and
        receives an undergraduate degree source. Otherwise, it represents an
        undergraduate student.
        """
        person = self._get_random_name(random.choice(list(Gender)).value)

        if is_graduate:
            ug_univ = self._pick_undergrad_university(dept.university)
            student = Student(
                person=person, department=dept, undergraduate_degree_from=ug_univ
            )
        else:
            student = Student(person=person, department=dept)

        self.all_students.append(student)
        return student

    def _generate_department(
        self, university: University, dept_name: str
    ) -> Department:
        """Generates a Department and its internal structure."""
        dept = Department(name=dept_name, university=university)

        # 1. Generate Faculty (counts driven by configuration)
        dept.full_professors = [
            self._generate_faculty_member(FullProfessor, dept)
            for _ in range(self._randint_from_range(self.config.full_professors))
        ]
        dept.associate_professors = [
            self._generate_faculty_member(AssociateProfessor, dept)
            for _ in range(self._randint_from_range(self.config.associate_professors))
        ]
        dept.assistant_professors = [
            self._generate_faculty_member(AssistantProfessor, dept)
            for _ in range(self._randint_from_range(self.config.assistant_professors))
        ]
        dept.lecturers = [
            self._generate_faculty_member(Lecturer, dept)
            for _ in range(self._randint_from_range(self.config.lecturers))
        ]

        all_faculty = dept.all_faculty
        all_professors = dept.all_professors

        # 2. Set Department Head
        dept.head = random.choice(dept.full_professors)

        # 3. Calculate Student Counts based on Faculty
        total_faculty = len(all_faculty)

        # UndergraduateStudent : Faculty = 8~14 : 1
        ug_ratio = random.randint(8, 14)
        num_ug = total_faculty * ug_ratio

        # GraduateStudent : Faculty = 3~4 : 1
        grad_ratio = random.randint(3, 4)
        num_grad = total_faculty * grad_ratio

        # 4. Generate Students
        undergrads = [
            self._generate_student(dept, is_graduate=False) for _ in range(num_ug)
        ]
        grads = [
            self._generate_student(dept, is_graduate=True) for _ in range(num_grad)
        ]
        dept.students = undergrads + grads

        # 5. Generate Courses
        num_courses = random.randint(
            10, 15
        )  # Heuristic for a reasonable number of courses
        dept.undergraduate_courses = [
            Course(f"{dept.name} Course {i+1}", dept) for i in range(num_courses)
        ]
        dept.graduate_courses = [
            GraduateCourse(f"{dept.name} Grad Course {i+1}", dept)
            for i in range(random.randint(5, 8))
        ]

        # 6. Generate Research Groups
        num_groups = self._randint_from_range(self.config.research_groups)
        for i in range(num_groups):
            # Lead is a Professor
            lead = random.choice(all_professors)
            group = ResearchGroup(
                name=f"RG {i+1} in {dept.name}", lead=lead, department=dept
            )
            dept.research_groups.append(group)

        # 7. Establish Relationships
        self._establish_faculty_relationships(dept, all_faculty)
        self._establish_student_relationships(dept, all_professors, grads, undergrads)
        self._establish_graduate_student_roles(dept, grads)

        return dept

    def _establish_faculty_relationships(
        self, dept: Department, all_faculty: List[FacultyMember]
    ):
        """Assigns courses to faculty members."""

        courses_pool = dept.undergraduate_courses.copy()
        grad_courses_pool = dept.graduate_courses.copy()

        for faculty in all_faculty:
            # Assign 1-2 Undergraduate Courses (pairwise disjoint requirement met by simple selection)
            num_courses = random.randint(1, 2)
            for _ in range(num_courses):
                if courses_pool:
                    course = random.choice(courses_pool)
                    courses_pool.remove(course)
                    faculty.teaches_courses.append(course)

            # Assign 1-2 Graduate Courses (pairwise disjoint requirement met by simple selection)
            num_grad_courses = random.randint(1, 2)
            for _ in range(num_grad_courses):
                if grad_courses_pool:
                    course = random.choice(grad_courses_pool)
                    grad_courses_pool.remove(course)
                    faculty.teaches_graduate_courses.append(course)

    def _establish_student_relationships(
        self,
        dept: Department,
        all_professors: List[Professor],
        grad_students: List[Student],
        undergrad_students: List[Student],
    ):
        """Assigns advisors and courses to all students."""

        # --- Graduate Student Advisors ---
        # Every graduate-like Student has a Professor as advisor
        for g_student in grad_students:
            advisor = random.choice(all_professors)
            g_student.advisor = advisor
            advisor.advised_students.append(g_student)

            # Every graduate-like Student takes 1-3 GraduateCourses
            num_courses = random.randint(1, 3)
            g_student.takes_graduate_courses.extend(
                random.sample(
                    dept.graduate_courses, min(num_courses, len(dept.graduate_courses))
                )
            )

            # Graduate-like Student co-authors 0-5 Publications with some Professors
            num_co_pubs = random.randint(0, 5)
            # Find all faculty publications
            all_faculty_pubs = [
                pub for prof in all_professors for pub in prof.publications
            ]
            if all_faculty_pubs:
                # Co-author with random selection of existing publications
                g_student.co_authored_publications.extend(
                    random.sample(
                        all_faculty_pubs, min(num_co_pubs, len(all_faculty_pubs))
                    )
                )

        # --- Undergraduate Student Advisors ---
        # 1/5 - 1/4 of the undergraduates have a Professor as their advisor
        ug_advisor_ratio = random.uniform(0.20, 0.25)  # 1/5 to 1/4
        num_advised_ug = int(len(undergrad_students) * ug_advisor_ratio)

        advised_students = random.sample(undergrad_students, num_advised_ug)

        for ug_student in advised_students:
            advisor = random.choice(all_professors)
            ug_student.advisor = advisor
            advisor.advised_students.append(ug_student)

        # Every undergrad takes 2-4 Courses
        for ug_student in undergrad_students:
            num_courses = random.randint(2, 4)
            ug_student.takes_courses.extend(
                random.sample(
                    dept.undergraduate_courses,
                    min(num_courses, len(dept.undergraduate_courses)),
                )
            )

    def _establish_graduate_student_roles(
        self, dept: Department, grad_students: List[Student]
    ):
        """Assigns Teaching Assistant and Research Assistant roles."""

        # 1. Teaching Assistants (TAs)
        # 1/5 - 1/4 of the GraduateStudents are chosen as TA for one Course
        ta_ratio = self._random_uniform_from_range(
            self.config.probability_graduate_student_is_teaching_assistant
        )
        num_tas = int(len(grad_students) * ta_ratio)

        ta_candidates = random.sample(grad_students, min(num_tas, len(grad_students)))

        # Courses the GraduateStudents are TeachingAssistant of are pairwise different
        ta_course_pool = dept.undergraduate_courses.copy()

        teaching_assistants = []
        for g_student in ta_candidates:
            if ta_course_pool:
                course = random.choice(ta_course_pool)
                ta_course_pool.remove(course)  # Ensure pairwise difference
                ta = TeachingAssistant(
                    graduate_student=g_student, course_assistant_for=course
                )
                teaching_assistants.append(ta)

        # 2. Research Assistants (RAs)
        # 1/4 - 1/3 of the GraduateStudents are chosen as ResearchAssistant
        ra_ratio = self._random_uniform_from_range(
            self.config.probability_graduate_student_is_research_assistant
        )
        num_ras = int(len(grad_students) * ra_ratio)

        ra_candidates = random.sample(grad_students, min(num_ras, len(grad_students)))

        research_assistants = []
        for g_student in ra_candidates:
            ra = ResearchAssistant(graduate_student=g_student)
            research_assistants.append(ra)

    def generate(self) -> List[University]:
        print("Generating external universities for degree sources...")
        self._create_degree_universities()

        for i in range(self.university_count):
            univ_name = f"Main University {i+1}"
            university = University(name=univ_name)

            # Departments are subOrganization of the University (count from configuration)
            num_departments = self._randint_from_range(self.config.departments)
            department_names_sample = random.sample(
                [d.value for d in DepartmentName],
                min(num_departments, len(list(DepartmentName))),
            )

            print(
                f"Generating {len(department_names_sample)} departments for {univ_name}..."
            )

            for dept_name in department_names_sample:
                # Add a unique suffix if the name is repeated
                unique_dept_name = f"{dept_name} ({university.name})"
                dept = self._generate_department(university, unique_dept_name)
                university.departments.append(dept)

            self.all_universities.append(university)

        print("\n--- Generation Summary ---")
        print(f"Total Universities (Main): {len(self.all_universities)}")
        print(f"Total Faculty: {len(self.all_faculty)}")
        print(f"Total Students: {len(self.all_students)}")
        print(f"Example Department: {self.all_universities[0].departments[0].name}")
        print(
            f"  - Head: {self.all_universities[0].departments[0].head.person.last_name}"
        )

        return self.all_universities
