import pytest
import operator


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
