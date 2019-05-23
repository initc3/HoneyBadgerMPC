from pytest import raises, mark
from honeybadgermpc.utils.typecheck import static_type_check
from honeybadgermpc.utils.misc import wrap_send
from random import randint
import asyncio


def test_type_check_callable():
    @static_type_check(str, 'callable(send)')
    def incorrect_func_with_callable(str, func):
        pass

    @static_type_check(str, 'callable(func)', 'True')
    def func_with_callable(str, func, c):
        pass

    with raises(ValueError):
        incorrect_func_with_callable('hello', lambda w: 'world')

    func_with_callable('hello', lambda w: 'world', func_with_callable)


def test_type_check_arrays():
    @static_type_check(str, ['str', 'callable(b)'])
    def func_with_arr_types(a, b):
        pass

    func_with_arr_types('hello', lambda w: 'world')
    func_with_arr_types('hello', 'world')
    with raises(TypeError):
        func_with_arr_types('hello', 5)


def test_type_check_incorrect_types():
    @static_type_check('{}')
    def func_1(a):
        pass

    @static_type_check({})
    def func_2(a):
        pass

    @static_type_check([{}])
    def func_3(a):
        pass

    @static_type_check(['{}'])
    def func_4(a):
        pass

    for func in [func_1, func_2, func_3, func_4]:
        with raises(ValueError):
            func({})


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


def test_wrap_send():
    test_dest, test_message = None, None

    def _send(dest, message):
        nonlocal test_dest, test_message
        test_dest = dest
        test_message = message

    wrapped = wrap_send('hello', _send)
    wrapped(1, 'world')
    assert (test_dest, test_message) == (1, ('hello', 'world'))


@mark.asyncio
async def test_pool():
    from honeybadgermpc.utils.task_pool import TaskPool

    max_tasks = 4

    async def work(q, max_tasks):
        assert q.qsize() <= max_tasks
        q.put_nowait(None)
        await asyncio.sleep(randint(0, 3)*0.2)
        await q.get()

    pool = TaskPool(max_tasks)
    q = asyncio.Queue()
    for _ in range(10):
        pool.submit(work(q, max_tasks))
    await pool.close()
