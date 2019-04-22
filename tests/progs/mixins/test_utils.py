from pytest import raises
from honeybadgermpc.progs.mixins.utils import static_type_check


def test_type_check_simple_func():
    @static_type_check(int, int)
    def simple_func(a, b):
        pass

    simple_func(1, 2)

    with raises(TypeError):
        simple_func('hello', 2)

    with raises(TypeError):
        simple_func(3, None)


def test_static_type_check_named_func():
    @static_type_check(a=int, b=float)
    def named_func(c, a=4, b=3.1):
        pass

    named_func(None, a=5)
    named_func(None, a=5, b=4.0)
    named_func('Hello, World', a=5, b=4.0)

    with raises(TypeError):
        named_func(None, a='hello', b=4.0)


def test_static_type_check_complex_func():
    @static_type_check(bool, a='int', b=(str, int))
    def complex_func(flag, warn, a=5, b='cool', c=18):
        pass

    complex_func(True, False, a=4, b='wow')
    complex_func(True, False, a=4, b=6)
    complex_func(True, False, 6, 4, 5)

    with raises(TypeError):
        complex_func(True, False, 'cat', 'hello', 5)

    with raises(TypeError):
        complex_func(True, False, a=4, b=5.0)


def test_static_type_check_incorrect_func():
    @static_type_check(a=int, b=str)
    def incorrect_func(a=5, b=7):
        pass

    with raises(TypeError):
        incorrect_func(a=4, b='str')

    with raises(TypeError):
        incorrect_func()


def test_static_type_check_too_many_checks():
    @static_type_check(int)
    def func():
        pass

    with raises(TypeError):
        func()


def test_static_type_check_overrun_unnamed():
    @static_type_check(int, int, b=int)
    def func(a, c=4, b=5):
        pass

    func(3)
    func(3, 3, 3)
    func(3, 3, b=3)
    func(3, c=3, b=3)
    func(3, b=3, c=3)
    with raises(TypeError):
        func(3, 'str', b=3)
