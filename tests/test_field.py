import pytest
import operator
from pytest import raises


def test_multiple_fields():
    from honeybadgermpc.field import GF
    field1 = GF.get(17)
    field2 = GF.get(7)
    assert field1.modulus == 17
    assert field2.modulus == 7


def test_invalid_operations_on_fields():
    from honeybadgermpc.field import GF, FieldsNotIdentical
    field1, field2 = GF.get(17), GF.get(7)
    operators = [
        operator.add,
        operator.sub,
        operator.xor,
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
    for i in range(100):
        num = galois_field.random()
        if pow(num, (field.modulus-1)//2) == 1:
            root = num.sqrt()
            assert root * root == num
        else:
            with raises(AssertionError):
                root = num.sqrt()
