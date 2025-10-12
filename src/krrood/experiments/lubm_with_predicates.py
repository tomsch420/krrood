"""
Auto-generated Python classes from OWL ontology
Generated using custom converter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union, Any

from ..entity_query_language.property_descriptor import Thing, PropertyDescriptor


# Property descriptor classes (object properties)
@dataclass(frozen=True)
class Advisor(PropertyDescriptor):
    """is being advised by"""


@dataclass(frozen=True)
class AffiliateOf(PropertyDescriptor):
    """is affiliated with"""


@dataclass(frozen=True)
class AffiliatedOrganizationOf(PropertyDescriptor):
    """is affiliated with"""


@dataclass(frozen=True)
class DegreeFrom(PropertyDescriptor):
    """has a degree from"""


@dataclass(frozen=True)
class HasAlumnus(PropertyDescriptor):
    """has as an alumnus"""
    @property
    def inverse(self):
        # Inverse of degreeFrom
        return DegreeFrom(self.range_value, self.domain_value)


@dataclass(frozen=True)
class ListedCourse(PropertyDescriptor):
    """lists as a course"""


@dataclass(frozen=True)
class Member(PropertyDescriptor):
    """has as a member"""


@dataclass(frozen=True)
class MemberOf(PropertyDescriptor):
    """member of"""
    @property
    def inverse(self):
        # Inverse of member
        return Member(self.range_value, self.domain_value)


@dataclass(frozen=True)
class OrgPublication(PropertyDescriptor):
    """publishes"""


@dataclass(frozen=True)
class PublicationAuthor(PropertyDescriptor):
    """was written by"""


@dataclass(frozen=True)
class PublicationResearch(PropertyDescriptor):
    """is about"""


@dataclass(frozen=True)
class ResearchProject(PropertyDescriptor):
    """has as a research project"""


@dataclass(frozen=True)
class SoftwareDocumentation(PropertyDescriptor):
    """is documented in"""


@dataclass(frozen=True)
class SubOrganizationOf(PropertyDescriptor):
    """is part of"""
    transitive = True


@dataclass(frozen=True)
class TakesCourse(PropertyDescriptor):
    """is taking"""


@dataclass(frozen=True)
class TeacherOf(PropertyDescriptor):
    """teaches"""


@dataclass(frozen=True)
class TeachingAssistantOf(PropertyDescriptor):
    """is a teaching assistant for"""


@dataclass(frozen=True)
class DoctoralDegreeFrom(DegreeFrom):
    """has a doctoral degree from"""


@dataclass(frozen=True)
class MastersDegreeFrom(DegreeFrom):
    """has a masters degree from"""


@dataclass(frozen=True)
class TakesCourseCourse(TakesCourse):
    """is taking"""


@dataclass(frozen=True)
class TakesCourseGraduateCourse(TakesCourse):
    """is taking"""


@dataclass(frozen=True)
class UndergraduateDegreeFrom(DegreeFrom):
    """has an undergraduate degree from"""


@dataclass(frozen=True)
class WorksFor(MemberOf):
    """Works For"""


@dataclass(frozen=True)
class HeadOf(WorksFor):
    """is the head of"""


@dataclass(frozen=True)
class WorksForOrganization(WorksFor):
    """Works For"""


@dataclass(frozen=True)
class WorksForResearchGroup(WorksFor):
    """Works For"""


@dataclass(frozen=True)
class HeadOfCollege(HeadOf):
    """is the head of"""


@dataclass(frozen=True)
class HeadOfDepartment(HeadOf):
    """is the head of"""


@dataclass(frozen=True)
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
    affiliated_organization_of: List[Organization] = AffiliatedOrganizationOf()
    # is affiliated with
    affiliate_of: List[Person] = AffiliateOf()
    # has as a member
    member: List[Person] = Member()
    # publishes
    org_publication: List[Publication] = OrgPublication()
    # is part of
    sub_organization_of: List[Organization] = SubOrganizationOf()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Person(UnivBenchOntology):
    """person"""
    # is being advised by
    advisor: List[Professor] = Advisor()
    # has a degree from
    degree_from: List[University] = DegreeFrom()
    # has a doctoral degree from
    doctoral_degree_from: List[University] = DoctoralDegreeFrom()
    # has a masters degree from
    masters_degree_from: List[University] = MastersDegreeFrom()
    # has an undergraduate degree from
    undergraduate_degree_from: List[University] = UndergraduateDegreeFrom()
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
    publication_author: List[Person] = PublicationAuthor()
    # was written on
    publication_date: Optional[str] = None
    # is about
    publication_research: List[Research] = PublicationResearch()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Schedule(UnivBenchOntology):
    """schedule"""
    # lists as a course
    listed_course: List[Course] = ListedCourse()

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
    head_of: List[Program] = HeadOfProgram()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Employee(Person):
    """Employee"""
    # Works For
    works_for: List[Organization] = WorksForOrganization()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class GraduateStudent(Person):
    """graduate student"""
    # is taking
    takes_course: List[GraduateCourse] = TakesCourseGraduateCourse()

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
    works_for: List[ResearchGroup] = WorksForResearchGroup()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class ResearchGroup(Organization):
    """research group"""
    # has as a research project
    research_project: List[Research] = ResearchProject()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Software(Publication):
    """software program"""
    # is documented in
    software_documentation: List[Publication] = SoftwareDocumentation()
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
    takes_course: List[Course] = TakesCourseCourse()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class TeachingAssistant(Person):
    """university teaching assistant"""
    # is a teaching assistant for
    teaching_assistant_of: List[Course] = TeachingAssistantOf()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class University(Organization):
    """university"""
    # has as an alumnus
    has_alumnus: List[Person] = HasAlumnus()

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
    teacher_of: List[Course] = TeacherOf()

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
    head_of: List[Department] = HeadOfDepartment()

    def __hash__(self):
        return hash(id(self))


@dataclass(eq=False)
class Dean(Professor):
    """dean"""
    # is the head of
    head_of: List[College] = HeadOfCollege()

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


