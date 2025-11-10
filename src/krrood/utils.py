from __future__ import annotations

from functools import lru_cache
from typing_extensions import TypeVar, Type, List

T = TypeVar("T")


@lru_cache(maxsize=None)
def recursive_subclasses(cls: Type[T]) -> List[Type[T]]:
    """
    :param cls: The class.
    :return: A list of the classes subclasses without the class itself.
    """
    return cls.__subclasses__() + [
        g for s in cls.__subclasses__() for g in recursive_subclasses(s)
    ]
