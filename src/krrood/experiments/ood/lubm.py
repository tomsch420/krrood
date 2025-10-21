from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TypeVar, Iterable, Any

from krrood.entity_query_language.predicate import Symbol, Predicate, predicate

# Type variable for the base role
TFacultyRole = TypeVar("TFacultyRole", bound="FacultyMember")
TStudentRole = TypeVar("TStudentRole", bound="Student")
TProfessorRole = TypeVar("TProfessorRole", bound="Professor")


@predicate
def exists(value: Iterable[Symbol]) -> bool:
    return any(value)


# --- Enums for data pools ---


class DepartmentName(Enum):
    """Canonical department names used across the generator."""

    COMPUTER_SCIENCE = "Computer Science"
    PHYSICS = "Physics"
    CHEMISTRY = "Chemistry"
    MATHEMATICS = "Mathematics"
    BIOLOGY = "Biology"
    LITERATURE = "Literature"
    HISTORY = "History"
    ENGINEERING = "Engineering"


class UniversityName(Enum):
    """Sample university names used to simulate external degrees."""

    STATE_UNIVERSITY = "State University"
    POLYTECHNIC_INSTITUTE = "Polytechnic Institute"
    METROPOLITAN_COLLEGE = "Metropolitan College"
    GLOBAL_RESEARCH_HUB = "Global Research Hub"
    TECH_UNIVERSITY = "Tech University"


class FirstName(Enum):
    """Sample first names for synthetic persons."""

    ALEX = "Alex"
    BEN = "Ben"
    CARA = "Cara"
    DEV = "Dev"
    EVE = "Eve"
    FINN = "Finn"
    GIA = "Gia"
    HAL = "Hal"
    IVY = "Ivy"
    JAKE = "Jake"


class LastName(Enum):
    """Sample last names for synthetic persons."""

    SMITH = "Smith"
    JONES = "Jones"
    LEE = "Lee"
    CHEN = "Chen"
    GUPTA = "Gupta"
    ALI = "Ali"
    CRUZ = "Cruz"
    SILVA = "Silva"
    SCHMIDT = "Schmidt"
    KIM = "Kim"


class Gender(Enum):
    """Gender values for synthetic persons."""

    MALE = "Male"
    FEMALE = "Female"


class PublicationAdjective(Enum):
    """Adjectives used in generated publication titles."""

    ADVANCED = "Advanced"
    NOVEL = "Novel"
    STATISTICAL = "Statistical"
    QUANTUM = "Quantum"
    DEEP = "Deep"


class PublicationNoun(Enum):
    """Nouns used in generated publication titles."""

    ALGORITHM = "Algorithm"
    ANALYSIS = "Analysis"
    SIMULATION = "Simulation"
    THEORY = "Theory"
    MODEL = "Model"


# --- Core Entities ---


@dataclass
class Organization(Symbol):
    """Base class for organizational units."""

    name: str


@dataclass
class Publication(Symbol):
    """Represents a research publication."""

    title: str
    year: int


@dataclass
class Course(Symbol):
    """Represents an undergraduate course."""

    name: str
    department: Optional[Department] = field(default=None, repr=False)  # TODO remove


@dataclass
class GraduateCourse(Course):
    """Represents a graduate-level course."""

    pass


@dataclass
class ResearchGroup(Organization):
    """Represents a sub-organization for research within a Department."""

    lead: Optional[Professor] = field(default=None)
    department: Optional[Department] = field(default=None, repr=False)


# --- Person & Base Roles (Composition) ---


@dataclass
class Person(Symbol):
    """Base entity representing an individual."""

    first_name: str
    last_name: str
    gender: str = "Unknown"  # Simplified gender for generation


@dataclass
class FacultyMember(Symbol):
    """
    Base role for academic staff. Composed with a Person entity.
    This separation allows a Person to hold multiple, distinct roles (SRP).
    """

    person: Person
    undergraduate_degree_from: "University" = field(repr=False)  # TODO move to person
    masters_degree_from: "University" = field(repr=False)  # TODO move to person
    doctoral_degree_from: "University" = field(repr=False)  # TODO move to person
    publications: List[Publication] = field(
        default_factory=list, repr=False
    )  # TODO move to author
    teaches_courses: List[Course] = field(default_factory=list, repr=False)  # move to
    teaches_graduate_courses: List[GraduateCourse] = field(
        default_factory=list, repr=False
    )
    department: Optional["Department"] = field(default=None, repr=False)


@dataclass
class Author(Symbol):
    person: Person
    publications: List[Publication] = field(default_factory=list)


@dataclass
class Professor(FacultyMember):
    """
    Role for professors (Full, Assoc, Asst). Inherits FacultyMember attributes.
    This intermediate role holds the advising relationship common to professors.
    """

    advised_students: List["Student"] = field(default_factory=list, repr=False)

    @property
    def advises_students(self) -> List["Student"]:
        """All students advised by this professor."""
        return self.advised_students

    @property
    def advises_graduate_students(self) -> List["Student"]:
        """Backwards-compatible view: students with graduate-course participation."""
        return [s for s in self.advised_students if s.takes_graduate_courses]

    @property
    def advises_undergraduate_students(self) -> List["Student"]:
        """Backwards-compatible view: students with undergraduate-course participation."""
        return [s for s in self.advised_students if s.takes_courses]


# --- Specific Faculty Ranks (Type Markers) ---


@dataclass
class FullProfessor(Professor):
    pass


@dataclass
class AssociateProfessor(Professor):
    pass


@dataclass
class AssistantProfessor(Professor):
    pass


@dataclass
class Lecturer(FacultyMember):
    """Lecturers do not advise students according to the rules."""

    pass


# --- Student Roles ---


@dataclass
class Student(Symbol):
    """Base role for all students. Composed with a Person entity.

    Unifies undergraduate and graduate student attributes.
    """

    person: Person
    department: Optional[Department] = field(default=None)
    advisor: Optional["Professor"] = field(default=None)
    # Unified attributes
    takes_courses: List["Course"] = field(default_factory=list)
    takes_graduate_courses: List["GraduateCourse"] = field(default_factory=list)
    undergraduate_degree_from: Optional["University"] = None
    co_authored_publications: List["Publication"] = field(default_factory=list)

    @property
    def takes_any_graduate_courses(self) -> bool:
        return len(self.takes_graduate_courses) > 0

    @property
    def takes_any_undergraduate_courses(self) -> bool:
        return len(self.takes_courses) > 0


# --- Ancillary Roles (Composition on GraduateStudent) ---


@dataclass
class TeachingAssistant(Symbol):
    """A specific temporary role for Students (historically graduate students)."""

    graduate_student: Student
    course_assistant_for: Course


@dataclass
class ResearchAssistant(Symbol):
    """A specific temporary role for Students (historically graduate students)."""

    graduate_student: Student


# --- Structural Units ---


@dataclass
class Department(Organization):
    """
    Sub-organization of a University. Holds references to all its members,
    courses, and groups (Aggregation).
    """

    university: Optional[University] = field(default=None)
    head: Optional[FullProfessor] = field(default=None)  # Head is one FullProfessor

    # Collections of all individuals (type-hinted for clarity)
    full_professors: List[FullProfessor] = field(default_factory=list)
    associate_professors: List[AssociateProfessor] = field(default_factory=list)
    assistant_professors: List[AssistantProfessor] = field(default_factory=list)
    lecturers: List[Lecturer] = field(default_factory=list)
    students: List[Student] = field(default_factory=list)

    # Collections of other entities
    research_groups: List[ResearchGroup] = field(default_factory=list)
    undergraduate_courses: List[Course] = field(default_factory=list)
    graduate_courses: List[GraduateCourse] = field(default_factory=list)

    @property
    def undergraduate_students(self) -> List[Student]:
        """Backwards-compatible view of undergraduates (takes undergrad courses)."""
        return [s for s in self.students if s.takes_courses]

    @property
    def graduate_students(self) -> List[Student]:
        """Backwards-compatible view of graduates (takes graduate courses)."""
        return [s for s in self.students if s.takes_graduate_courses]

    @property
    def all_faculty(self) -> List[FacultyMember]:
        """Convenience property for all academic staff."""
        return (
            self.full_professors
            + self.associate_professors
            + self.assistant_professors
            + self.lecturers
        )

    @property
    def all_professors(self) -> List[Professor]:
        """Convenience property for all professors (advisor pool)."""
        return (
            self.full_professors + self.associate_professors + self.assistant_professors
        )

    @property
    def courses(self) -> List[Course]:
        """Convenience property for all courses."""
        return self.graduate_courses + self.undergraduate_courses


@dataclass
class University(Organization):
    """Top-level organization."""

    departments: List[Department] = field(default_factory=list)
