"""
Auto-generated Python classes from OWL ontology
Generated using custom converter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union, Any

from ..entity_query_language.predicate import Thing, PropertyDescriptor


# Property descriptor classes (object properties)
@dataclass
class Advisor(PropertyDescriptor):
    """is being advised by"""


@dataclass
class AffiliateOf(PropertyDescriptor):
    """is affiliated with"""


@dataclass
class AffiliatedOrganizationOf(PropertyDescriptor):
    """is affiliated with"""


@dataclass
class DegreeFrom(PropertyDescriptor):
    """has a degree from"""


@dataclass
class HasAlumnus(PropertyDescriptor):
    """has as an alumnus"""
    @property
    def inverse(self):
        # Inverse of degreeFrom
        return DegreeFrom(self.range_value, self.domain_value)


@dataclass
class ListedCourse(PropertyDescriptor):
    """lists as a course"""


@dataclass
class Member(PropertyDescriptor):
    """has as a member"""


@dataclass
class MemberOf(PropertyDescriptor):
    """member of"""
    @property
    def inverse(self):
        # Inverse of member
        return Member(self.range_value, self.domain_value)


@dataclass
class OrgPublication(PropertyDescriptor):
    """publishes"""


@dataclass
class PublicationAuthor(PropertyDescriptor):
    """was written by"""


@dataclass
class PublicationResearch(PropertyDescriptor):
    """is about"""


@dataclass
class ResearchProject(PropertyDescriptor):
    """has as a research project"""


@dataclass
class SoftwareDocumentation(PropertyDescriptor):
    """is documented in"""


@dataclass
class SubOrganizationOf(PropertyDescriptor):
    """is part of"""
    transitive = True


@dataclass
class TakesCourse(PropertyDescriptor):
    """is taking"""


@dataclass
class TeacherOf(PropertyDescriptor):
    """teaches"""


@dataclass
class TeachingAssistantOf(PropertyDescriptor):
    """is a teaching assistant for"""


@dataclass
class DoctoralDegreeFrom(DegreeFrom):
    """has a doctoral degree from"""


@dataclass
class MastersDegreeFrom(DegreeFrom):
    """has a masters degree from"""


@dataclass
class TakesCourseCourse(TakesCourse):
    """is taking"""


@dataclass
class TakesCourseGraduateCourse(TakesCourse):
    """is taking"""


@dataclass
class UndergraduateDegreeFrom(DegreeFrom):
    """has an undergraduate degree from"""


@dataclass
class WorksFor(MemberOf):
    """Works For"""


@dataclass
class HeadOf(WorksFor):
    """is the head of"""


@dataclass
class WorksForOrganization(WorksFor):
    """Works For"""


@dataclass
class WorksForResearchGroup(WorksFor):
    """Works For"""


@dataclass
class HeadOfCollege(HeadOf):
    """is the head of"""


@dataclass
class HeadOfDepartment(HeadOf):
    """is the head of"""


@dataclass
class HeadOfProgram(HeadOf):
    """is the head of"""



# Generated classes
@dataclass(eq=False)
class UnivBenchOntology(Thing):
    """Base class for Univ-bench Ontology"""
    # name
    name: Optional[str] = None
    # office room No.
    office_number: Optional[int] = None
    # is researching
    research_interest: Optional[str] = None

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Organization(UnivBenchOntology):
    """organization"""
    # is affiliated with
    affiliated_organization_of: List[Organization] = field(default_factory=AffiliatedOrganizationOf)
    # is affiliated with
    affiliate_of: List[Person] = field(default_factory=AffiliateOf)
    # has as a member
    member: List[Person] = field(default_factory=Member)
    # publishes
    org_publication: List[Publication] = field(default_factory=OrgPublication)
    # is part of
    sub_organization_of: List[Organization] = field(default_factory=SubOrganizationOf)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Person(UnivBenchOntology):
    """person"""
    # is being advised by
    advisor: List[Professor] = field(default_factory=Advisor)
    # has a degree from
    degree_from: List[University] = field(default_factory=DegreeFrom)
    # has a doctoral degree from
    doctoral_degree_from: List[University] = field(default_factory=DoctoralDegreeFrom)
    # has a masters degree from
    masters_degree_from: List[University] = field(default_factory=MastersDegreeFrom)
    # has an undergraduate degree from
    undergraduate_degree_from: List[University] = field(default_factory=UndergraduateDegreeFrom)
    # is age
    age: Optional[int] = None
    # can be reached at
    email_address: Optional[str] = None
    # telephone number
    telephone: Optional[str] = None
    # title
    title: Optional[str] = None

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Publication(UnivBenchOntology):
    """publication"""
    # was written by
    publication_author: List[Person] = field(default_factory=PublicationAuthor)
    # was written on
    publication_date: Optional[str] = None
    # is about
    publication_research: List[Research] = field(default_factory=PublicationResearch)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Schedule(UnivBenchOntology):
    """schedule"""
    # lists as a course
    listed_course: List[Course] = field(default_factory=ListedCourse)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Work(UnivBenchOntology):
    """Work"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Article(Publication):
    """article"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Book(Publication):
    """book"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class College(Organization):
    """school"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Course(Work):
    """teaching course"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Department(Organization):
    """university department"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Director(Person):
    """director"""
    # is the head of
    head_of: List[Program] = field(default_factory=HeadOfProgram)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Employee(Person):
    """Employee"""
    # Works For
    works_for: List[Organization] = field(default_factory=WorksForOrganization)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class GraduateStudent(Person):
    """graduate student"""
    # is taking
    takes_course: List[GraduateCourse] = field(default_factory=TakesCourseGraduateCourse)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Institute(Organization):
    """institute"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Manual(Publication):
    """manual"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Program(Organization):
    """program"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Research(Work):
    """research work"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class ResearchAssistant(Person):
    """university research assistant"""
    # Works For
    works_for: List[ResearchGroup] = field(default_factory=WorksForResearchGroup)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class ResearchGroup(Organization):
    """research group"""
    # has as a research project
    research_project: List[Research] = field(default_factory=ResearchProject)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Software(Publication):
    """software program"""
    # is documented in
    software_documentation: List[Publication] = field(default_factory=SoftwareDocumentation)
    # is version
    software_version: Optional[str] = None

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Specification(Publication):
    """published specification"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Student(Person):
    """student"""
    # is taking
    takes_course: List[Course] = field(default_factory=TakesCourseCourse)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class TeachingAssistant(Person):
    """university teaching assistant"""
    # is a teaching assistant for
    teaching_assistant_of: List[Course] = field(default_factory=TeachingAssistantOf)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class University(Organization):
    """university"""
    # has as an alumnus
    has_alumnus: List[Person] = field(default_factory=HasAlumnus)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class UnofficialPublication(Publication):
    """unnoficial publication"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class AdministrativeStaff(Employee):
    """administrative staff worker"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class ConferencePaper(Article):
    """conference paper"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Faculty(Employee):
    """faculty member"""
    # teaches
    teacher_of: List[Course] = field(default_factory=TeacherOf)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class GraduateCourse(Course):
    """Graduate Level Courses"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class JournalArticle(Article):
    """journal article"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class TechnicalReport(Article):
    """technical report"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class UndergraduateStudent(Student):
    """undergraduate student"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class ClericalStaff(AdministrativeStaff):
    """clerical staff worker"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Lecturer(Faculty):
    """lecturer"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class PostDoc(Faculty):
    """post doctorate"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Professor(Faculty):
    """professor"""
    # is tenured:
    tenured: Optional[bool] = None

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class SystemsStaff(AdministrativeStaff):
    """systems staff worker"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class AssistantProfessor(Professor):
    """assistant professor"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class AssociateProfessor(Professor):
    """associate professor"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Chair(Professor):
    """chair"""
    # is the head of
    head_of: List[Department] = field(default_factory=HeadOfDepartment)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Dean(Professor):
    """dean"""
    # is the head of
    head_of: List[College] = field(default_factory=HeadOfCollege)

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class FullProfessor(Professor):
    """full professor"""
    ...

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class VisitingProfessor(Professor):
    """visiting professor"""
    ...

    def __hash__(self):
        return hash(id(self))


