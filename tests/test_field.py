import pytest
import operator


def test_multiple_fields():
    from honeybadgermpc.field import GF
    Field1 = GF(17)
    Field2 = GF(7)
    assert Field1.modulus == 17
    assert Field2.modulus == 7


def test_invalid_operations_on_fields():
    from honeybadgermpc.field import GF, FieldsNotIdentical
    Field1, Field2 = GF(17), GF(7)
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
        with pytest.raises((TypeError, FieldsNotIdentical)):
            op(Field1(2), Field2(3))
