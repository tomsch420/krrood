from __future__ import annotations

import pytest

from krrood.entity_query_language.hashed_data import HashedValue


class TestHashedValueBooleanInterning:
    def test_true_singleton_identity(self):
        hv1 = HashedValue(True)
        hv2 = HashedValue(True)
        assert hv1 is hv2
        assert hv1.value is True

    def test_false_singleton_identity(self):
        hv1 = HashedValue(False)
        hv2 = HashedValue(False)
        assert hv1 is hv2
        assert hv1.value is False

    def test_wrapping_hashed_value_bool_returns_singleton(self):
        inner = HashedValue(True)
        wrapped = HashedValue(inner)
        assert wrapped is inner
        assert wrapped.value is True
