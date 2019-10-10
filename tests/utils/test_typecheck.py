from honeybadgermpc.utils.typecheck import TypeCheck
from pytest import raises
from typing import Callable


def test_type_check_callable():
    @TypeCheck()
    def incorrect_func_with_callable(str: str, func: "callable(send)"):  # noqa: F821
        """ The argument is named `func` but the constraint specifies
        `callable(send)` rather than `callable(func)`
        """
        pass

    with raises(AssertionError):
        incorrect_func_with_callable("hello", lambda w: "world")

    @TypeCheck()
    def func_with_callable(str: str, func: "callable(func)", c: "True"):  # noqa: F821
        pass

    func_with_callable("hello", lambda w: "world", func_with_callable)

    @TypeCheck()
    def func_with_callable_2(func: Callable):
        pass

    func_with_callable_2(lambda a: a)


def test_type_check_multiple_constraints():
    @TypeCheck()
    def func_with_tuple_types(a: str, b: ("str", Callable)):
        pass

    func_with_tuple_types("hello", lambda w: "world")
    func_with_tuple_types("hello", "world")
    with raises(AssertionError):
        func_with_tuple_types("hello", 5)


def test_type_check_invalid_constraints():
    @TypeCheck()
    def func_1(a: "{}"):
        pass

    with raises(AssertionError):
        func_1({})

    @TypeCheck()
    def func2(a: {}):
        pass

    with raises(AssertionError):
        func2({})

    @TypeCheck()
    def func3(a: ({},)):
        pass

    with raises(AssertionError):
        func3({})

    @TypeCheck()
    def func_4(a: ("[]")):
        pass

    with raises(AssertionError):
        func_4({})

    @TypeCheck()
    def func_5(a: [int]):
        pass

    with raises(AssertionError):
        func_5(45)


def test_type_check_simple():
    @TypeCheck()
    def simple_func(a: int, b: int):
        pass

    simple_func(1, 2)

    with raises(AssertionError):
        simple_func("hello", 2)

    with raises(AssertionError):
        simple_func(3, None)


def test_type_check_named_arguments():
    @TypeCheck()
    def named_func(c, a: int = 4, b: float = 3.1):
        pass

    named_func(None, a=5)
    named_func(None, a=5, b=4.0)
    named_func("Hello, World", a=5, b=4.0)

    with raises(AssertionError):
        named_func(None, a="hello", b=4.0)


def test_type_check_complex_arguments():
    @TypeCheck()
    def func(flag: bool, warn, a: int = 5, b: (str, int) = "cool", c=18):
        pass

    func(True, False, a=4, b="wow")
    func(True, False, a=4, b=6)
    func(True, False, 6, 4, 5)

    with raises(AssertionError):
        func(True, False, "cat", "hello", 5)

    with raises(AssertionError):
        func(True, False, a=4, b=5.0)


def test_type_check_incorrect_defaults():
    @TypeCheck()
    def func(a: int = 5, b: str = 7):
        pass

    with raises(AssertionError):
        func(a=4, b="str")

    with raises(AssertionError):
        func()


def test_type_check_arithmetic():
    @TypeCheck(arithmetic=True)
    def func(a: int = 0, b: int = 0):
        return a + b

    # Following will raise assertions if code is broken
    assert func() == 0
    assert func(4) == 4
    assert func(4, 5) == 9
    assert func(3.0, 5.0) == NotImplemented

    @TypeCheck(arithmetic=True)
    def incorrect_func(a: int = 0, b: int = 0.0):
        return a + b

    with raises(AssertionError):
        incorrect_func()

    with raises(AssertionError):
        incorrect_func(3)

    with raises(AssertionError):
        incorrect_func(4, 5)


class TypeA:
    def __init__(self, v):
        self.v = v

    @TypeCheck(arithmetic=True)
    def __add__(self, other: "TypeA"):
        return TypeA(self.v + other.v)

    @TypeCheck(arithmetic=True)
    def __radd__(self, other: "TypeB"):
        return TypeA(self.v + other.v)


class TypeB:
    def __init__(self, v):
        self.v = v

    @TypeCheck(arithmetic=True)
    def __add__(self, other: "TypeB"):
        return TypeB(self.v + other.v)

    @TypeCheck(arithmetic=True)
    def __radd__(self, other: "TypeA"):
        return TypeB(self.v + other.v)


def test_type_check_arithmetic_lookup():
    a = TypeA(5)
    b = TypeB(4)

    assert isinstance(a + a, TypeA)
    assert isinstance(a + b, TypeB)
    assert isinstance(b + b, TypeB)
    assert isinstance(b + a, TypeA)
