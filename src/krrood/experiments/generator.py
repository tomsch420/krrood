from dataclasses import dataclass
from typing import Optional, Tuple


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

    universities: Range = Range(1, 15)
    """
    The min/max number of universities.
    """

    departments: Range = Range(15, 25)
    """
    The min/max number of departments per university.
    These departments all belong to the same university.
    """

    full_professors: Range = Range(7, 10)
    """
    The min/max number of full professors per department.
    One of these professors is the head of the department.
    """

    associate_professors: Range = Range(10, 14)
    """
    The min/max number of associate_professors per department.
    """

    assistant_professors: Range = Range(8, 11)
    """
    The min/max number of assistant_professors per department.
    """

    lecturers: Range = Range(5, 7)
    """
    The min/max number of lecturers per department.
    """

    research_groups: Range = Range(10, 20)
    """
    The min/max number of research groups per department.
    """

    probability_graduate_student_is_teaching_assistant = Range(1 / 5, 1 / 4)
    """
    The min/max probability that a graduate student is a teaching assistant.
    """

    probability_graduate_student_is_research_assistant = Range(1 / 4, 1 / 3)
    """
    The probability that a graduate student is a research assistant.
    """

    seed: Optional[int] = None
    """
    A seed for the random number generator.
    """


@dataclass
class Generator:
    """
    Generate a dataset of university benchmark data.
    """

    configuration: GeneratorConfiguration
