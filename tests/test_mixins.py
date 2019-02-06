from random import randint
from pytest import mark


@mark.asyncio
async def test_degree_reduction(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.elliptic_curve import Subgroup
    from honeybadgermpc.mixins import DoubleSharing

    n, t = 9, 2

    x_expected = randint(0, Subgroup.BLS12_381-1)
    sid_x_2t = test_preprocessing.generate("share", n, 2*t, x_expected)
    test_preprocessing.generate("double_shares", n, t)

    async def _prog(context):
        sh_x_2t = test_preprocessing.elements.get_share(context, sid_x_2t, 2*t)
        x_actual = await (await DoubleSharing.reduce_degree(context, sh_x_2t)).open()
        assert x_expected == x_actual

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_multiplication_using_double_sharing(galois_field, test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mixins import DoubleSharing, MixinOpName

    n, t = 9, 2

    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("double_shares", n, t)

    async def _prog(context):
        sh_a = test_preprocessing.elements.get_rand(context)
        sh_b = test_preprocessing.elements.get_rand(context)
        ab_expected = await sh_a.open() * await sh_b.open()

        ab_actual = await(await (sh_a * sh_b)).open()
        assert ab_expected == ab_actual

    program_runner = TaskProgramRunner(
        n, t, {MixinOpName.Mul: DoubleSharing.multiply_shares})
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_beaver_mul_with_zeros(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mixins import BeaverTriple, MixinOpName

    n, t = 3, 1
    x_secret, y_secret = 10, 15
    test_preprocessing.generate("zeros", n, t)
    test_preprocessing.generate("triples", n, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x = test_preprocessing.elements.get_zero(context) + context.Share(x_secret)
        y = test_preprocessing.elements.get_zero(context) + context.Share(y_secret)

        xy = await (x*y)

        x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
        assert x_ * y_ == xy_

        print("[%d] Finished" % (context.myid,), x_, y_, xy_)
        return xy_

    program_runner = TaskProgramRunner(
        n, t, {MixinOpName.Mul: BeaverTriple.multiply_shares})
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
    assert all(res == x_secret * y_secret for res in results)


@mark.asyncio
async def test_beaver_mul(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mixins import BeaverTriple, MixinOpName

    n, t = 3, 1
    test_preprocessing.generate("triples", n, t)
    test_preprocessing.generate("rands", n, t)

    async def _prog(context):
        # Example of Beaver multiplication
        x = test_preprocessing.elements.get_rand(context)
        y = test_preprocessing.elements.get_rand(context)

        xy = await (x*y)

        x_, y_, xy_ = await x.open(), await y.open(), await xy.open()
        assert x_ * y_ == xy_

        print("[%d] Finished" % (context.myid,), x_, y_, xy_)
        return xy_

    program_runner = TaskProgramRunner(
        n, t, {MixinOpName.Mul: BeaverTriple.multiply_shares})
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
