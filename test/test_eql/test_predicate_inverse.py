from dataclasses import dataclass
from typing import Any, ClassVar, Type

import pytest

from krrood.entity_query_language.predicate import BinaryPredicate


def test_inverse_of_sets_back_reference():
    @dataclass()
    class ParentOf(BinaryPredicate):
        def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
            return True

        @property
        def domain_value(self):
            return None

        @property
        def range_value(self):
            return None

    @dataclass()
    class ChildOf(BinaryPredicate):
        inverse_of: ClassVar[Type[BinaryPredicate]] = ParentOf

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

        @dataclass()
        class InvalidInverse(BinaryPredicate):
            inverse_of = object  # not a Predicate subclass

            def _holds_direct(self, domain_value: Any, range_value: Any) -> bool:
                return True

            @property
            def domain_value(self):
                return None

            @property
            def range_value(self):
                return None
