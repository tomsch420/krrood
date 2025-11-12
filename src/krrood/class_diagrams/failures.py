from typing import Type


class ClassIsUnMappedInClassDiagram(Exception):
    """
    Raised when a class is not mapped in the class diagram.
    """

    def __init__(self, class_: Type):
        super().__init__(f"Class {class_} is not mapped in the class diagram")
