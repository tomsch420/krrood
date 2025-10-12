from dataclasses import dataclass
from typing import Any, ClassVar, Type

import pytest

from krrood.entity_query_language import Predicate


def test_inverse_of_sets_back_reference():
    @dataclass(frozen=True)
    class ParentOf(Predicate):
        def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
            return True

        @property
        def domain_value(self):
            return None

        @property
        def range_value(self):
            return None

    @dataclass(frozen=True)
    class ChildOf(Predicate):
        inverse_of: ClassVar[Type[Predicate]] = ParentOf

        def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
            return True

        @property
        def domain_value(self):
            return None

        @property
        def range_value(self):
            return None

    assert ParentOf.inverse_of is ChildOf
    assert ChildOf.inverse_of is ParentOf


def test_inverse_of_type_validation():
    # inverse_of must be a Predicate subclass
    with pytest.raises(TypeError):

        @dataclass(frozen=True)
        class InvalidInverse(Predicate):
            inverse_of = object  # not a Predicate subclass

            def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
                return True

            @property
            def domain_value(self):
                return None

            @property
            def range_value(self):
                return None
