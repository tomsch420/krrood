from typing import Union, Iterable


import numpy as np
import pytest
import scipy


import krrood.symbolic_math.symbolic_math as cas
from krrood.entity_query_language.symbol_graph import SymbolGraph
from krrood.symbolic_math.exceptions import (
    HasFreeSymbolsError,
    WrongDimensionsError,
)

TrinaryTrue = cas.TrinaryTrue.to_np()[0]
TrinaryFalse = cas.TrinaryFalse.to_np()[0]
TrinaryUnknown = cas.TrinaryUnknown.to_np()[0]

all_expressions_float_np = Union[
    cas.CasadiScalarWrapper,
    float,
    np.ndarray,
    Iterable[float],
    Iterable[Iterable[float]],
]


def to_float_or_np(x: all_expressions_float_np) -> Union[float, np.ndarray]:
    if isinstance(x, cas.CasadiScalarWrapper):
        return x.to_np()
    return x


def assert_allclose(
    a: all_expressions_float_np,
    b: all_expressions_float_np,
    atol: float = 1e-3,
    rtol: float = 1e-3,
    equal_nan: bool = False,
):
    a = to_float_or_np(a)
    b = to_float_or_np(b)
    assert np.allclose(a, b, atol=atol, rtol=rtol, equal_nan=equal_nan)


def logic_not(a):
    if a == TrinaryTrue:
        return TrinaryFalse
    elif a == TrinaryFalse:
        return TrinaryTrue
    elif a == TrinaryUnknown:
        return TrinaryUnknown
    else:
        raise ValueError(f"Invalid truth value: {a}")


def logic_and(a, b):
    if a == TrinaryFalse or b == TrinaryFalse:
        return TrinaryFalse
    elif a == TrinaryTrue and b == TrinaryTrue:
        return TrinaryTrue
    elif a == TrinaryUnknown or b == TrinaryUnknown:
        return TrinaryUnknown
    else:
        raise ValueError(f"Invalid truth values: {a}, {b}")


def logic_or(a, b):
    if a == TrinaryTrue or b == TrinaryTrue:
        return TrinaryTrue
    elif a == TrinaryFalse and b == TrinaryFalse:
        return TrinaryFalse
    elif a == TrinaryUnknown or b == TrinaryUnknown:
        return TrinaryUnknown
    else:
        raise ValueError(f"Invalid truth values: {a}, {b}")


class TestLogic3:
    values = [
        TrinaryTrue,
        TrinaryFalse,
        TrinaryUnknown,
    ]

    def test_and3(self):
        s = cas.MathSymbol(name="a")
        s2 = cas.MathSymbol(name="b")
        expr = cas.trinary_logic_and(s, s2)
        f = expr.compile()
        for i in self.values:
            for j in self.values:
                expected = logic_and(i, j)
                actual = f(np.array([i, j]))
                assert (
                    expected == actual
                ), f"a={i}, b={j}, expected {expected}, actual {actual}"

    def test_or3(self):
        s = cas.MathSymbol(name="a")
        s2 = cas.MathSymbol(name="b")
        expr = cas.trinary_logic_or(s, s2)
        f = expr.compile()
        for i in self.values:
            for j in self.values:
                expected = logic_or(i, j)
                actual = f(np.array([i, j]))
                assert (
                    expected == actual
                ), f"a={i}, b={j}, expected {expected}, actual {actual}"

    def test_not3(self):
        s = cas.MathSymbol(name="muh")
        expr = cas.trinary_logic_not(s)
        f = expr.compile()
        for i in self.values:
            expected = logic_not(i)
            actual = f(np.array([i]))
            assert expected == actual, f"a={i}, expected {expected}, actual {actual}"

    def test_sub_logic_operators(self):
        def reference_function(a, b, c):
            not_c = logic_not(c)
            or_result = logic_or(b, not_c)
            result = logic_and(a, or_result)
            return result

        a, b, c = cas.create_symbols(["a", "b", "c"])
        expr = cas.logic_and(a, cas.logic_or(b, cas.logic_not(c)))
        new_expr = cas.replace_with_trinary_logic(expr)
        f = new_expr.compile()
        for i in self.values:
            for j in self.values:
                for k in self.values:
                    computed_result = f(np.array([i, j, k]))
                    expected_result = reference_function(i, j, k)
                    assert (
                        computed_result == expected_result
                    ), f"Mismatch for inputs i={i}, j={j}, k={k}. Expected {expected_result}, got {computed_result}"


class TestSymbol:
    def test_from_name(self):
        s = cas.MathSymbol(name="muh")
        assert isinstance(s, cas.MathSymbol)
        assert str(s) == "muh"

    def test_to_np(self):
        s1 = cas.MathSymbol(name="s1")
        with pytest.raises(HasFreeSymbolsError):
            s1.to_np()

    def test_add(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s + 1, cas.Expression)
        assert isinstance(1 + s, cas.Expression)
        assert isinstance(s + 1.0, cas.Expression)
        assert isinstance(1.0 + s, cas.Expression)

        assert isinstance(s + s, cas.Expression)

        e = cas.Expression(data=1)
        assert isinstance(e + s, cas.Expression)
        assert isinstance(s + e, cas.Expression)

    def test_sub(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s - 1, cas.Expression)
        assert isinstance(1 - s, cas.Expression)
        assert isinstance(s - 1.0, cas.Expression)
        assert isinstance(1.0 - s, cas.Expression)

        assert isinstance(s - s, cas.Expression)

        e = cas.Expression(data=1)
        assert isinstance(e - s, cas.Expression)
        assert isinstance(s - e, cas.Expression)

    def test_mul(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s * 1, cas.Expression)
        assert isinstance(1 * s, cas.Expression)
        assert isinstance(s * 1.0, cas.Expression)
        assert isinstance(1.0 * s, cas.Expression)

        assert isinstance(s * s, cas.Expression)

        e = cas.Expression()
        assert isinstance(e * s, cas.Expression)
        assert isinstance(s * e, cas.Expression)

    def test_truediv(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s / 1, cas.Expression)
        assert isinstance(1 / s, cas.Expression)
        assert isinstance(s / 1.0, cas.Expression)
        assert isinstance(1.0 / s, cas.Expression)

        assert isinstance(s / s, cas.Expression)

        e = cas.Expression(data=1)
        assert isinstance(e / s, cas.Expression)
        assert isinstance(s / e, cas.Expression)

    def test_lt(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s < 1, cas.Expression)
        assert isinstance(1 < s, cas.Expression)
        assert isinstance(s < 1.0, cas.Expression)
        assert isinstance(1.0 < s, cas.Expression)

        assert isinstance(s < s, cas.Expression)

        e = cas.Expression(data=1)
        assert isinstance(e < s, cas.Expression)
        assert isinstance(s < e, cas.Expression)

    def test_pow(self):
        s = cas.MathSymbol(name="muh")
        # int float addition is fine
        assert isinstance(s**1, cas.Expression)
        assert isinstance(1**s, cas.Expression)
        assert isinstance(s**1.0, cas.Expression)
        assert isinstance(1.0**s, cas.Expression)

        assert isinstance(s**s, cas.Expression)

        e = cas.Expression()
        assert isinstance(e**s, cas.Expression)
        assert isinstance(s**e, cas.Expression)

    def test_simple_math(self):
        s = cas.MathSymbol(name="muh")
        e = s + s
        assert isinstance(e, cas.Expression)
        e = s - s
        assert isinstance(e, cas.Expression)
        e = s * s
        assert isinstance(e, cas.Expression)
        e = s / s
        assert isinstance(e, cas.Expression)
        e = s**s
        assert isinstance(e, cas.Expression)

    def test_comparisons(self):
        s = cas.MathSymbol(name="muh")
        e = s > s
        assert isinstance(e, cas.Expression)
        e = s >= s
        assert isinstance(e, cas.Expression)
        e = s < s
        assert isinstance(e, cas.Expression)
        e = s <= s
        assert isinstance(e, cas.Expression)
        e = s == s
        assert isinstance(e, cas.Expression)

    def test_logic(self):
        s1 = cas.MathSymbol(name="s1")
        s2 = cas.MathSymbol(name="s2")
        s3 = cas.MathSymbol(name="s3")
        e = s1 | s2
        assert isinstance(e, cas.Expression)
        e = s1 & s2
        assert isinstance(e, cas.Expression)
        e = ~s1
        assert isinstance(e, cas.Expression)
        e = s1 & (s2 | ~s3)
        assert isinstance(e, cas.Expression)

    def test_hash(self):
        s = cas.MathSymbol(name="muh")
        d = {s: 1}
        assert d[s] == 1


class TestExpression:
    def test_kron(self):
        m1 = np.eye(4)
        r1 = cas.Expression(data=m1).kron(cas.Expression(data=m1))
        r2 = np.kron(m1, m1)
        assert_allclose(r1, r2)

    def test_jacobian(self):
        a = cas.MathSymbol(name="a")
        b = cas.MathSymbol(name="b")
        m = cas.Expression(data=[a + b, a**2, b**2])
        jac = m.jacobian([a, b])
        expected = cas.Expression(data=[[1, 1], [2 * a, 0], [0, 2 * b]])
        for i in range(expected.shape[0]):
            for j in range(expected.shape[1]):
                assert jac[i, j].equivalent(expected[i, j])

    def test_jacobian_dot(self, a=1, ad=2, b=3, bd=4):
        kwargs = {
            "a": a,
            "ad": ad,
            "b": b,
            "bd": bd,
        }
        a_s = cas.MathSymbol(name="a")
        ad_s = cas.MathSymbol(name="ad")
        b_s = cas.MathSymbol(name="b")
        bd_s = cas.MathSymbol(name="bd")
        m = cas.Expression(
            data=[
                a_s**3 * b_s**3,
                # b_s ** 2,
                -a_s * cas.cos(b_s),
                # a_s * b_s ** 4
            ]
        )
        jac = m.jacobian_dot([a_s, b_s], [ad_s, bd_s])
        expected_expr = cas.Expression(
            data=[
                [
                    6 * ad_s * a_s * b_s**3 + 9 * a_s**2 * bd_s * b_s**2,
                    9 * ad_s * a_s**2 * b_s**2 + 6 * a_s**3 * bd_s * b,
                ],
                # [0, 2 * bd_s],
                [bd_s * cas.sin(b_s), ad_s * cas.sin(b_s) + a_s * bd_s * cas.cos(b_s)],
                # [4 * bd * b ** 3, 4 * ad * b ** 3 + 12 * a * bd * b ** 2]
            ]
        )
        actual = jac.compile().call_with_kwargs(**kwargs)
        expected = expected_expr.compile().call_with_kwargs(**kwargs)
        assert_allclose(actual, expected)

    def test_jacobian_ddot(self, a=1, ad=2, add=3, b=4, bd=5, bdd=6):
        kwargs = {
            "a": a,
            "ad": ad,
            "add": add,
            "b": b,
            "bd": bd,
            "bdd": bdd,
        }
        a_s = cas.MathSymbol(name="a")
        ad_s = cas.MathSymbol(name="ad")
        add_s = cas.MathSymbol(name="add")
        b_s = cas.MathSymbol(name="b")
        bd_s = cas.MathSymbol(name="bd")
        bdd_s = cas.MathSymbol(name="bdd")
        m = cas.Expression(
            data=[
                a_s**3 * b_s**3,
                b_s**2,
                -a_s * cas.cos(b_s),
            ]
        )
        jac = m.jacobian_ddot([a_s, b_s], [ad_s, bd_s], [add_s, bdd_s])
        expected = np.array(
            [
                [
                    add * 6 * b**3 + bdd * 18 * a**2 * b + 2 * ad * bd * 18 * a * b**2,
                    bdd * 6 * a**3 + add * 18 * b**2 * a + 2 * ad * bd * 18 * b * a**2,
                ],
                [0, 0],
                [bdd * np.cos(b), bdd * -a * np.sin(b) + 2 * ad * bd * np.cos(b)],
            ]
        )
        actual = jac.compile().call_with_kwargs(**kwargs)
        assert_allclose(actual, expected)

    def test_total_derivative2(self, a=1, ad=2, add=3, b=4, bd=5, bdd=6):
        kwargs = {
            "a": a,
            "ad": ad,
            "add": add,
            "b": b,
            "bd": bd,
            "bdd": bdd,
        }
        a_s = cas.MathSymbol(name="a")
        ad_s = cas.MathSymbol(name="ad")
        add_s = cas.MathSymbol(name="add")
        b_s = cas.MathSymbol(name="b")
        bd_s = cas.MathSymbol(name="bd")
        bdd_s = cas.MathSymbol(name="bdd")
        m = cas.Expression(data=a_s * b_s**2)
        jac = m.second_order_total_derivative([a_s, b_s], [ad_s, bd_s], [add_s, bdd_s])
        actual = jac.compile().call_with_kwargs(**kwargs)
        expected = bdd * 2 * a + 2 * ad * bd * 2 * b
        assert_allclose(actual, expected)

    def test_total_derivative2_2(
        self, a=1, b=2, c=3, ad=4, bd=5, cd=6, add=7, bdd=8, cdd=9
    ):
        kwargs = {
            "a": a,
            "ad": ad,
            "add": add,
            "b": b,
            "bd": bd,
            "bdd": bdd,
            "c": c,
            "cd": cd,
            "cdd": cdd,
        }
        a_s = cas.MathSymbol(name="a")
        ad_s = cas.MathSymbol(name="ad")
        add_s = cas.MathSymbol(name="add")
        b_s = cas.MathSymbol(name="b")
        bd_s = cas.MathSymbol(name="bd")
        bdd_s = cas.MathSymbol(name="bdd")
        c_s = cas.MathSymbol(name="c")
        cd_s = cas.MathSymbol(name="cd")
        cdd_s = cas.MathSymbol(name="cdd")
        m = cas.Expression(data=a_s * b_s**2 * c_s**3)
        jac = m.second_order_total_derivative(
            [a_s, b_s, c_s], [ad_s, bd_s, cd_s], [add_s, bdd_s, cdd_s]
        )
        # expected_expr = cas.Expression(add_s + bdd_s*2*a*c**3 + 4*ad_s*)
        actual = jac.compile().call_with_kwargs(**kwargs)
        # expected = expected_expr.compile()(**kwargs)
        expected = (
            bdd * 2 * a * c**3
            + cdd * 6 * a * b**2 * c
            + 4 * ad * bd * b * c**3
            + 6 * ad * b**2 * cd * c**2
            + 12 * a * bd * b * cd * c**2
        )
        assert_allclose(actual, expected)

    def test_free_symbols(self):
        m = cas.Expression(data=cas.create_symbols(["a", "b", "c", "d"]))
        assert len(m.free_symbols()) == 4
        a = cas.MathSymbol(name="a")
        assert a.equivalent(a.free_symbols()[0])

    def test_diag(self):
        result = cas.Expression.diag([1, 2, 3])
        assert result[0, 0] == 1
        assert result[0, 1] == 0
        assert result[0, 2] == 0

        assert result[1, 0] == 0
        assert result[1, 1] == 2
        assert result[1, 2] == 0

        assert result[2, 0] == 0
        assert result[2, 1] == 0
        assert result[2, 2] == 3
        assert cas.diag(cas.Expression(data=[1, 2, 3])).equivalent(cas.diag([1, 2, 3]))

    def test_pretty_str(self):
        e = cas.Expression.eye(4)
        e.pretty_str()

    def test_create(self):
        cas.Expression(data=cas.MathSymbol(name="muh"))
        cas.Expression(data=[cas.ca.SX(1), cas.ca.SX.sym("muh")])
        m = cas.Expression(data=np.eye(4))
        m = cas.Expression(data=m)
        assert_allclose(m, np.eye(4))
        m = cas.Expression(cas.ca.SX(np.eye(4)))
        assert_allclose(m, np.eye(4))
        m = cas.Expression(data=[1, 1])
        assert_allclose(m, np.array([1, 1]))
        m = cas.Expression(data=[np.array([1, 1])])
        assert_allclose(m, np.array([1, 1]))
        m = cas.Expression(data=1)
        assert m.to_np() == 1
        m = cas.Expression(data=[[1, 1], [2, 2]])
        assert_allclose(m, np.array([[1, 1], [2, 2]]))
        m = cas.Expression(data=[])
        assert m.shape[0] == m.shape[1] == 0
        m = cas.Expression()
        assert m.shape[0] == m.shape[1] == 0

    def test_filter1(self):
        e_np = np.arange(16) * 2
        e = cas.Expression(data=e_np)
        filter_ = np.zeros(16, dtype=bool)
        filter_[3] = True
        filter_[5] = True
        actual = e[filter_].to_np()
        expected = e_np[filter_]
        assert np.all(actual == expected)

    def test_filter2(self):
        e_np = np.arange(16) * 2
        e_np = e_np.reshape((4, 4))
        e = cas.Expression(data=e_np)
        filter_ = np.zeros(4, dtype=bool)
        filter_[1] = True
        filter_[2] = True
        actual = e[filter_]
        expected = e_np[filter_]
        assert_allclose(actual, expected)

    def test_add(self, f1=1, f2=3):
        expected = f1 + f2
        r1 = cas.Expression(data=f2) + f1
        assert_allclose(r1, expected)
        r1 = f1 + cas.Expression(data=f2)
        assert_allclose(r1, expected)
        r1 = cas.Expression(data=f1) + cas.Expression(data=f2)
        assert_allclose(r1, expected)

    def test_sub(self, f1=1, f2=3):
        expected = f1 - f2
        r1 = cas.Expression(data=f1) - f2
        assert_allclose(r1, expected)
        r1 = f1 - cas.Expression(data=f2)
        assert_allclose(r1, expected)
        r1 = cas.Expression(data=f1) - cas.Expression(data=f2)
        assert_allclose(r1, expected)

    def test_len(self):
        m = cas.Expression(data=np.eye(4))
        assert len(m) == len(np.eye(4))

    def test_simple_math(self):
        m = cas.Expression(data=[1, 1])
        s = cas.MathSymbol(name="muh")
        e = m + s
        e = m + 1
        e = 1 + m
        assert isinstance(e, cas.Expression)
        e = m - s
        e = m - 1
        e = 1 - m
        assert isinstance(e, cas.Expression)
        e = m * s
        e = m * 1
        e = 1 * m
        assert isinstance(e, cas.Expression)
        e = m / s
        e = m / 1
        e = 1 / m
        assert isinstance(e, cas.Expression)
        e = m**s
        e = m**1
        e = 1**m
        assert isinstance(e, cas.Expression)

    def test_to_np(self):
        e = cas.Expression(data=1)
        assert_allclose(e.to_np(), np.array([1]))
        e = cas.Expression(data=[1, 2])
        assert_allclose(e.to_np(), np.array([1, 2]))
        e = cas.Expression(data=[[1, 2], [3, 4]])
        assert_allclose(e.to_np(), np.array([[1, 2], [3, 4]]))

    def test_to_np_fail(self):
        s1, s2 = cas.MathSymbol(name="s1"), cas.MathSymbol(name="s2")
        e = s1 + s2
        with pytest.raises(HasFreeSymbolsError):
            e.to_np()

    def test_get_attr(self):
        m = cas.Expression(data=np.eye(4))
        assert m[0, 0] == cas.Expression(data=1)
        assert m[1, 1] == cas.Expression(data=1)
        assert m[1, 0] == cas.Expression(data=0)
        assert isinstance(m[0, 0], cas.Expression)
        print(m.shape)

    def test_comparisons(self):
        logic_functions = [
            lambda a, b: a > b,
            lambda a, b: a >= b,
            lambda a, b: a < b,
            lambda a, b: a <= b,
            lambda a, b: a == b,
        ]
        e1_np = np.array([1, 2, 3, -1])
        e2_np = np.array([1, 1, -1, 3])
        e1_cas = cas.Expression(data=e1_np)
        e2_cas = cas.Expression(data=e2_np)
        for f in logic_functions:
            r_np = f(e1_np, e2_np)
            r_cas = f(e1_cas, e2_cas)
            assert isinstance(r_cas, cas.Expression)
            r_cas = r_cas.to_np()
            np.all(r_np == r_cas)

    def test_logic_and(self):
        s1 = cas.MathSymbol(name="s1")
        s2 = cas.MathSymbol(name="s2")
        expr = cas.logic_and(cas.BinaryTrue, s1)
        assert not cas.is_true_symbol(expr) and not cas.is_false_symbol(expr)
        expr = cas.logic_and(cas.BinaryFalse, s1)
        assert cas.is_false_symbol(expr)
        expr = cas.logic_and(cas.BinaryTrue, cas.BinaryTrue)
        assert cas.is_true_symbol(expr)
        expr = cas.logic_and(cas.BinaryFalse, cas.BinaryTrue)
        assert cas.is_false_symbol(expr)
        expr = cas.logic_and(cas.BinaryFalse, cas.BinaryFalse)
        assert cas.is_false_symbol(expr)
        expr = cas.logic_and(s1, s2)
        assert not cas.is_true_symbol(expr) and not cas.is_false_symbol(expr)

    def test_logic_or(self):
        s1 = cas.MathSymbol(name="s1")
        s2 = cas.MathSymbol(name="s2")
        s3 = cas.MathSymbol(name="s3")
        expr = cas.logic_or(cas.BinaryFalse, s1)
        assert not cas.is_true_symbol(expr) and not cas.is_false_symbol(expr)
        expr = cas.logic_or(cas.BinaryTrue, s1)
        assert cas.is_true_symbol(expr)
        expr = cas.logic_or(cas.BinaryTrue, cas.BinaryTrue)
        assert cas.is_true_symbol(expr)
        expr = cas.logic_or(cas.BinaryFalse, cas.BinaryTrue)
        assert cas.is_true_symbol(expr)
        expr = cas.logic_or(cas.BinaryFalse, cas.BinaryFalse)
        assert cas.is_false_symbol(expr)
        expr = cas.logic_or(s1, s2)
        assert not cas.is_true_symbol(expr) and not cas.is_false_symbol(expr)

        expr = cas.logic_or(s1, s2, s3)
        assert not cas.is_true_symbol(expr) and not cas.is_false_symbol(expr)

    def test_lt(self):
        e1 = cas.Expression(data=[1, 2, 3, -1])
        e2 = cas.Expression(data=[1, 1, -1, 3])
        gt_result = e1 < e2
        assert isinstance(gt_result, cas.Expression)
        assert cas.logic_all(gt_result == cas.Expression(data=[0, 0, 0, 1])).to_np()


class TestIfElse:

    @pytest.mark.parametrize("condition", [True, False])
    def test_if_greater_zero(self, condition):
        if_result, else_result = 1, -1
        assert_allclose(
            cas.if_greater_zero(
                cas.Expression(condition),
                cas.Expression(if_result),
                cas.Expression(else_result),
            ),
            float(if_result if condition > 0 else else_result),
        )

    def test_if_one_arg(self):
        types = [
            cas.Expression,
        ]
        if_functions = [
            cas.if_else,
            cas.if_eq_zero,
            cas.if_greater_eq_zero,
            cas.if_greater_zero,
        ]
        c = cas.MathSymbol(name="c")
        for type_ in types:
            for if_function in if_functions:
                if_result = type_()
                else_result = type_()
                result = if_function(c, if_result, else_result)
                assert isinstance(
                    result, type_
                ), f"{type(result)} != {type_} for {if_function}"

    def test_if_two_arg(self):
        types = [
            cas.Expression,
        ]
        if_functions = [
            cas.if_eq,
            cas.if_greater,
            cas.if_greater_eq,
            cas.if_less,
            cas.if_less_eq,
        ]
        a = cas.MathSymbol(name="a")
        b = cas.MathSymbol(name="b")
        for type_ in types:
            for if_function in if_functions:
                if_result = type_()
                else_result = type_()
                assert isinstance(if_function(a, b, if_result, else_result), type_)

    @pytest.mark.parametrize("condition", [True, False])
    def test_if_greater_eq_zero(self, condition, if_result=0, else_result=1):
        assert_allclose(
            cas.if_greater_eq_zero(condition, if_result, else_result),
            float(if_result if condition >= 0 else else_result),
        )

    @pytest.mark.parametrize("a,b", [[1, 0], [2, -1]])
    def test_if_greater_eq(self, a, b, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_greater_eq(a, b, if_result, else_result),
            float(if_result if a >= b else else_result),
        )

    @pytest.mark.parametrize("a,b", [[1, 0], [2, -1]])
    def test_if_less_eq(self, a, b, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_less_eq(a, b, if_result, else_result),
            float(if_result if a <= b else else_result),
        )

    @pytest.mark.parametrize("condition", [True, False])
    def test_if_eq_zero(self, condition, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_eq_zero(condition, if_result, else_result),
            float(if_result if condition == 0 else else_result),
        )

    @pytest.mark.parametrize("a,b", [[1, 0], [2, -1]])
    def test_if_eq(self, a, b, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_eq(a, b, if_result, else_result),
            float(if_result if a == b else else_result),
        )

    @pytest.mark.parametrize("a,", [2, -1])
    def test_if_eq_cases(self, a):
        b_result_cases = [
            (1, cas.Expression(data=1)),
            (3, cas.Expression(data=3)),
            (4, cas.Expression(data=4)),
            (-1, cas.Expression(data=-1)),
            (0.5, cas.Expression(data=0.5)),
            (-0.5, cas.Expression(data=-0.5)),
        ]

        def reference(a_, b_result_cases_, else_result):
            for b, if_result in b_result_cases_:
                if a_ == b:
                    return if_result.to_np()[0]
            return else_result

        actual = cas.if_eq_cases(a, b_result_cases, cas.Expression(data=0))
        expected = float(reference(a, b_result_cases, 0))
        assert_allclose(actual, expected)

    @pytest.mark.parametrize("a,", [2, -1])
    def test_if_eq_cases_set(self, a):
        b_result_cases = {
            (1, cas.Expression(data=1)),
            (3, cas.Expression(data=3)),
            (4, cas.Expression(data=4)),
            (-1, cas.Expression(data=-1)),
            (0.5, cas.Expression(data=0.5)),
            (-0.5, cas.Expression(data=-0.5)),
        }

        def reference(a_, b_result_cases_, else_result):
            for b, if_result in b_result_cases_:
                if a_ == b:
                    return if_result.to_np()[0]
            return else_result

        actual = cas.if_eq_cases(a, b_result_cases, cas.Expression(data=0))
        expected = float(reference(a, b_result_cases, 0))
        assert_allclose(actual, expected)

    @pytest.mark.parametrize("a,", [2, -1])
    def test_if_less_eq_cases(self, a):
        b_result_cases = [
            (-1, cas.Expression(data=-1)),
            (-0.5, cas.Expression(data=-0.5)),
            (0.5, cas.Expression(data=0.5)),
            (1, cas.Expression(data=1)),
            (3, cas.Expression(data=3)),
            (4, cas.Expression(data=4)),
        ]

        def reference(a_, b_result_cases_, else_result):
            for b, if_result in b_result_cases_:
                if a_ <= b:
                    return if_result.to_np()[0]
            return else_result

        assert_allclose(
            cas.if_less_eq_cases(a, b_result_cases, cas.Expression(data=0)),
            float(reference(a, b_result_cases, 0)),
        )

    @pytest.mark.parametrize("a,b", [[1, 0], [2, -1]])
    def test_if_greater(self, a, b, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_greater(a, b, if_result, else_result),
            float(if_result if a > b else else_result),
        )

    @pytest.mark.parametrize("a,b", [[1, 0], [2, -1]])
    def test_if_less(self, a, b, if_result=0.0, else_result=1.0):
        assert_allclose(
            cas.if_less(a, b, if_result, else_result),
            float(if_result if a < b else else_result),
        )


class TestCASWrapper:

    @pytest.mark.parametrize("sparse", [True, False])
    def test_empty_compiled_function(self, sparse):
        if sparse:
            expected = np.array([1, 2, 3], ndmin=2)
        else:
            expected = np.array([1, 2, 3])
        e = cas.Expression(data=expected)
        f = e.compile(sparse=sparse)
        if sparse:
            assert_allclose(f().toarray(), expected)
            assert_allclose(f(np.array([], dtype=float)).toarray(), expected)
        else:
            assert_allclose(f(), expected)
            assert_allclose(f(np.array([], dtype=float)), expected)

    def test_create_symbols(self):
        result = cas.create_symbols(["a", "b", "c"])
        assert str(result[0]) == "a"
        assert str(result[1]) == "b"
        assert str(result[2]) == "c"

    def test_create_symbols2(self):
        result = cas.create_symbols(3)
        assert str(result[0]) == "s_0"
        assert str(result[1]) == "s_1"
        assert str(result[2]) == "s_2"

    def test_vstack(self):
        m = np.eye(4)
        m1 = cas.Expression(data=m)
        e = cas.Expression.vstack([m1, m1])
        r1 = e
        r2 = np.vstack([m, m])
        assert_allclose(r1, r2)

    def test_vstack_empty(self):
        m = np.eye(0)
        m1 = cas.Expression(data=m)
        e = cas.Expression.vstack([m1, m1])
        r1 = e
        r2 = np.vstack([m, m])
        assert_allclose(r1, r2)

    def test_hstack(self):
        m = np.eye(4)
        m1 = cas.Expression(data=m)
        e = cas.Expression.hstack([m1, m1])
        r1 = e
        r2 = np.hstack([m, m])
        assert_allclose(r1, r2)

    def test_hstack_empty(self):
        m = np.eye(0)
        m1 = cas.Expression(data=m)
        e = cas.Expression.hstack([m1, m1])
        r1 = e
        r2 = np.hstack([m, m])
        assert_allclose(r1, r2)

    def test_diag_stack(self):
        m1_np = np.eye(4)
        m2_np = np.ones((2, 5))
        m3_np = np.ones((5, 3))
        m1_e = cas.Expression(data=m1_np)
        m2_e = cas.Expression(data=m2_np)
        m3_e = cas.Expression(data=m3_np)
        e = cas.Expression.diag_stack([m1_e, m2_e, m3_e])
        r1 = e
        combined_matrix = np.zeros((4 + 2 + 5, 4 + 5 + 3))
        row_counter = 0
        column_counter = 0
        for matrix in [m1_np, m2_np, m3_np]:
            combined_matrix[
                row_counter : row_counter + matrix.shape[0],
                column_counter : column_counter + matrix.shape[1],
            ] = matrix
            row_counter += matrix.shape[0]
            column_counter += matrix.shape[1]
        assert_allclose(r1, combined_matrix)

    def test_save_division(self, f1=1, f2=2):
        assert_allclose(
            cas.Expression(data=f1).safe_division(f2), f1 / f2 if f2 != 0 else 0
        )

    def test_limit(self, x=1, lower_limit=0, upper_limit=2):
        r1 = cas.limit(x, lower_limit, upper_limit)
        r2 = max(lower_limit, min(upper_limit, x))
        assert_allclose(r1, r2)

    def test_to_str2(self):
        a, b = cas.create_symbols(["a", "b"])
        e = cas.if_eq(a, 0, a, b)
        assert e.pretty_str() == [["(((a==0)?a:0)+((!(a==0))?b:0))"]]

    def test_leq_on_array(self):
        a = cas.Expression(data=np.array([1, 2, 3, 4]))
        b = cas.Expression(data=np.array([2, 2, 2, 2]))
        assert not cas.logic_all(a <= b).to_np()


class TestCompiledFunction:
    def test_dense(self):
        s1_value = 420.0
        s2_value = 69.0
        s1, s2 = cas.create_symbols(["s1", "s2"])
        e = cas.sqrt(cas.cos(s1) + cas.sin(s2))
        e_f = e.compile()
        actual = e_f(np.array([s1_value, s2_value]))
        expected = np.sqrt(np.cos(s1_value) + np.sin(s2_value))
        assert_allclose(actual, expected)

    def test_dense_two_params(self):
        s1_value = 420.0
        s2_value = 69.0
        s1, s2 = cas.create_symbols(["s1", "s2"])
        e = cas.sqrt(cas.cos(s1) + cas.sin(s2))
        e_f = e.compile(parameters=[[s1], [s2]])
        actual = e_f(np.array([s1_value]), np.array([s2_value]))
        expected = np.sqrt(np.cos(s1_value) + np.sin(s2_value))
        assert_allclose(actual, expected)

    def test_sparse(self):
        s1_value = 420.0
        s2_value = 69.0
        s1, s2 = cas.create_symbols(["s1", "s2"])
        e = cas.sqrt(cas.cos(s1) + cas.sin(s2))
        e_f = e.compile(sparse=True)
        actual = e_f(np.array([s1_value, s2_value]))
        assert isinstance(actual, scipy.sparse.csc_matrix)
        expected = np.sqrt(np.cos(s1_value) + np.sin(s2_value))
        assert_allclose(actual.toarray(), expected)

    def test_stacked_compiled_function_dense(self):
        s1_value = 420.0
        s2_value = 69.0
        s1, s2 = cas.create_symbols(["s1", "s2"])
        e1 = cas.sqrt(cas.cos(s1) + cas.sin(s2))
        e2 = s1 + s2
        e_f = cas.CompiledFunctionWithViews(
            expressions=[e1, e2], symbol_parameters=[[s1, s2]]
        )
        actual_e1, actual_e2 = e_f(np.array([s1_value, s2_value]))
        expected_e1 = np.sqrt(np.cos(s1_value) + np.sin(s2_value))
        expected_e2 = s1_value + s2_value
        assert_allclose(actual_e1, expected_e1)
        assert_allclose(actual_e2, expected_e2)

    def test_missing_free_symbols(self):
        s1, s2 = cas.create_symbols(["s1", "s2"])
        e = cas.sqrt(cas.cos(s1) + cas.sin(s2))
        with pytest.raises(HasFreeSymbolsError):
            e.compile(parameters=[[s1]])
