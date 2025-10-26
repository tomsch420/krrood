from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Optional, Iterable, Dict, Any, Callable, List, Union

from typing_extensions import TypeVar, ClassVar

from .utils import make_list, ALL

# Pre-create singletons for boolean hashed values to avoid repeated allocations
HV_FALSE = None  # will be initialized after HashedValue class definition
HV_TRUE = None  # will be initialized after HashedValue class definition

T = TypeVar("T")


@dataclass
class HashedValue(Generic[T]):
    # Internal registry for boolean singletons
    _BOOL_SINGLETONS: ClassVar[Dict[bool, "HashedValue"]] = {}

    def __new__(cls, value, id_: Optional[int] = None):
        # If wrapping a HashedValue of a boolean, return the boolean singleton instance
        if (
            id_ is None
            and isinstance(value, HashedValue)
            and isinstance(value.value, bool)
        ):
            existing = cls._BOOL_SINGLETONS.get(value.value)
            if existing is not None:
                return existing
        # Return singletons for booleans when available
        if id_ is None and isinstance(value, bool):
            existing = cls._BOOL_SINGLETONS.get(value)
            if existing is not None:
                return existing
        return super().__new__(cls)

    """
    Value wrapper carrying a stable hash identifier.

    :param value: The wrapped value.
    :param id_: Optional explicit identifier; if omitted, derived from value.
    :ivar value: The wrapped value.
    :ivar id_: The stable identifier used for hashing and equality.
    """

    value: T
    id_: Optional[int] = field(default=None)

    def __post_init__(self) -> None:
        """
        Initialize the identifier from the wrapped value when not provided.
        """
        # Intern common immutable values to avoid reallocation on hot paths
        if self.id_ is None:
            if isinstance(self.value, bool):
                # Use fixed ids for booleans for stable hashing and object reuse
                self.id_ = 1 if self.value else 0
                # ensure singleton registry populated on first construction
                if type(self)._BOOL_SINGLETONS.get(self.value) is None:
                    type(self)._BOOL_SINGLETONS[self.value] = self
                return
            if isinstance(self.value, HashedValue):
                # Handle the case where __new__ returned a boolean singleton and dataclass __init__
                # temporarily set value to self (self-referential); restore proper boolean payload.
                singletons = type(self)._BOOL_SINGLETONS
                if self is singletons.get(True) or self is singletons.get(False):
                    # Map back to the corresponding boolean
                    is_true = self is singletons.get(True)
                    self.value = True if is_true else False
                    self.id_ = 1 if is_true else 0
                    return
                # General nested HashedValue: unwrap
                self.id_ = self.value.id_
                self.value = self.value.value
                return
            if hasattr(self.value, "_id_"):
                self.id_ = self.value._id_
            else:
                self.id_ = id(self.value)

    def __hash__(self) -> int:
        """Hash of the identifier."""
        return hash(self.id_)

    def __eq__(self, other: object) -> bool:
        """
        Equality based on identifier, with ALL sentinel matching any value.
        """
        if isinstance(other, ALL):
            return True
        if not isinstance(other, HashedValue):
            return False
        return self.id_ == other.id_


# Initialize boolean singletons after class definition
# We create them by constructing HashedValue once for True and False; subsequent
# HashedValue(True/False) constructions will return these singletons via __new__.
HV_TRUE = HashedValue(True)
HV_FALSE = HashedValue(False)


@dataclass
class HashedIterable(Generic[T]):
    """
    A wrapper for an iterable that hashes its items.
    This is useful for ensuring that the items in the iterable are unique and can be used as keys in a dictionary.
    """

    iterable: Iterable[HashedValue[T]] = field(default_factory=list)
    values: Dict[int, HashedValue[T]] = field(default_factory=dict)

    def __post_init__(self):
        if self.iterable and not isinstance(self.iterable, HashedIterable):
            self.iterable = (
                HashedValue(v) if not isinstance(v, HashedValue) else v
                for v in self.iterable
            )

    def set_iterable(self, iterable):
        if iterable and not isinstance(iterable, HashedIterable):
            self.iterable = (
                HashedValue(v) if not isinstance(v, HashedValue) else v
                for v in iterable
            )

    def get(self, key: int, default: Any) -> HashedValue[T]:
        return self.values.get(key, default)

    def add(self, value: Any):
        if not isinstance(value, HashedValue):
            value = HashedValue(value)
        if value.id_ not in self.values:
            self.values[value.id_] = value
        return self

    def update(self, iterable: Iterable[Any]):
        for v in iterable:
            self.add(v)

    def map(
        self,
        func: Callable[[HashedValue], HashedValue],
        ids: Optional[List[int]] = None,
    ) -> HashedIterable[T]:
        if ids:
            func = lambda v: func(v) if v.id_ in ids else v
        return HashedIterable(map(func, self))

    def filter(self, func: Callable[[HashedValue], bool]) -> HashedIterable[T]:
        return HashedIterable(filter(func, self))

    @property
    def unwrapped_values(self) -> List[T]:
        return [v.value for v in self]

    @property
    def first_value(self) -> HashedValue:
        """
        Return the first value in the iterable.
        """
        for v in self:
            return v
        raise ValueError("Tried to get a value from empty iterable")

    def clear(self):
        self.values.clear()

    def __iter__(self):
        """
        Iterate over the hashed values.

        :return: An iterator over the hashed values.
        """
        yield from self.values.values()
        for v in self.iterable:
            self.values[v.id_] = v
            yield v

    def __or__(self, other) -> HashedIterable[T]:
        return self.union(other)

    def __and__(self, other) -> HashedIterable[T]:
        return self.intersection(other)

    def intersection(self, other):
        common_keys = self.values.keys() & other.values.keys()
        common_values = {k: self.values[k] for k in common_keys}
        return HashedIterable(values=common_values)

    def difference(self, other):
        left_keys = self.values.keys() - other.values.keys()
        values = {k: self.values[k] for k in left_keys}
        return HashedIterable(values=values)

    def union(self, other):
        if not isinstance(other, HashedIterable):
            other = HashedIterable(
                values={HashedValue(v).id_: HashedValue(v) for v in make_list(other)}
            )
        all_keys = self.values.keys() | other.values.keys()
        all_values = {k: self.values.get(k, other.values.get(k)) for k in all_keys}
        return HashedIterable(values=all_values)

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, id_: Any) -> HashedValue:
        """
        Get the HashedValue by its id.

        :param id_: The id of the HashedValue to get.
        :return: The HashedValue with the given id.
        :raises KeyError: If the given id is unknown.
        """
        if isinstance(id_, HashedValue):
            id_ = id_.id_
        elif not isinstance(id_, int):
            id_ = HashedValue(id_).id_
        try:
            return self.values[id_]
        except KeyError:
            for v in self.iterable:
                self.values[v.id_] = v
                if v.id_ == id_:
                    return v
            raise KeyError(id_)

    def __setitem__(self, id_: int, value: HashedValue[T]):
        """
        Set the HashedValue by its id.

        :param id_: The id of the HashedValue to set.
        :param value: The HashedValue to set.
        """
        self.values[id_] = value

    def __copy__(self):
        """
        Create a shallow copy of the HashedIterable.

        :return: A new HashedIterable instance with the same values.
        """
        return HashedIterable(values=self.values.copy())

    def __contains__(self, item):
        return item in self.values

    def __hash__(self):
        return hash(tuple(sorted(self.values.keys())))

    def __eq__(self, other):
        keys_are_equal = self.values.keys() == other.values.keys()
        if not keys_are_equal:
            return False
        values_are_equal = all(
            my_v == other_v
            for my_v, other_v in zip(self.values.values(), other.values.values())
        )
        return values_are_equal

    def __bool__(self):
        return bool(self.values) or bool(self.iterable)
