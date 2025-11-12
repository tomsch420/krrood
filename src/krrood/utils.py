from __future__ import annotations

from functools import lru_cache
from typing import Optional, Set

from typing_extensions import TypeVar, Type, List

T = TypeVar("T")


# @lru_cache(maxsize=None)
def recursive_subclasses(
    cls: Type[T], all_subclasses: Optional[Set] = None
) -> List[Type[T]]:
    """
    :param cls: The class.
    :return: A list of the classes subclasses without the class itself.
    """
    if all_subclasses is None:
        all_subclasses = set()
    for subclass in cls.__subclasses__():
        all_subclasses.add(subclass)
        recursive_subclasses(subclass, all_subclasses)
    return list(all_subclasses)
