import pytest
import operator
from pytest import raises
from honeybadgermpc.field import GF, FieldsNotIdentical


def test_bool():
    from honeybadgermpc.field import GF

    field1 = GF(17)
    assert bool(field1(23))
    assert not bool(field1(0))


def test_multiple_fields():
    field1 = GF(17)
    field2 = GF(7)
    assert field1.modulus == 17
    assert field2.modulus == 7


def test_invalid_operations_on_fields():
    field1, field2 = GF(17), GF(7)
    operators = [
        operator.add,
        operator.sub,
        operator.mul,
        operator.truediv,
        operator.floordiv,
        operator.eq,
    ]
    for op in operators:
        with pytest.raises(FieldsNotIdentical):
            op(field1(2), field2(3))


def test_sqrt(galois_field):
    field = galois_field
    for _ in range(100):
        num = galois_field.random()
        if pow(num, (field.modulus - 1) // 2) == 1:
            root = num.sqrt()
            assert root * root == num
        else:
            with raises(AssertionError):
                root = num.sqrt()


def test_singleton_pattern():
    gf_1 = GF(19)
    gf_2 = GF(19)
    assert gf_1 is gf_2
    assert gf_1.modulus == 19
    assert gf_2.modulus == 19
    assert gf_1 is GF(19)
    assert GF(19).modulus == 19
