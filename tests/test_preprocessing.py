from pytest import mark
from honeybadgermpc.mpc import TaskProgramRunner
import asyncio


@mark.asyncio
async def test_get_triple(test_preprocessing):
    n, t = 4, 1
    num_triples = 2
    test_preprocessing.generate("triples", n, t)

    async def _prog(ctx):
        for _ in range(num_triples):
            a_sh, b_sh, ab_sh = test_preprocessing.elements.get_triple(ctx)
            a, b, ab = await a_sh.open(), await b_sh.open(), await ab_sh.open()
            assert a * b == ab

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_cube(test_preprocessing):
    n, t = 4, 1
    num_cubes = 2
    test_preprocessing.generate("cubes", n, t)

    async def _prog(ctx):
        for _ in range(num_cubes):
            a1_sh, a2_sh, a3_sh = test_preprocessing.elements.get_cube(ctx)
            a1, a2, a3 = await a1_sh.open(), await a2_sh.open(), await a3_sh.open()
            assert a1 * a1 == a2
            assert a1 * a2 == a3

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_zero(test_preprocessing):
    n, t = 4, 1
    num_zeros = 2
    test_preprocessing.generate("zeros", n, t)

    async def _prog(ctx):
        for _ in range(num_zeros):
            x_sh = test_preprocessing.elements.get_zero(ctx)
            assert await x_sh.open() == 0

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_rand(test_preprocessing):
    n, t = 4, 1
    num_rands = 2
    test_preprocessing.generate("rands", n, t)

    async def _prog(ctx):
        for _ in range(num_rands):
            # Nothing to assert here, just check if the
            # required number of rands are generated
            test_preprocessing.elements.get_rand(ctx)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_bit(test_preprocessing):
    n, t = 4, 1
    num_bits = 20
    test_preprocessing.generate("bits", n, t)

    async def _prog(ctx):
        shares = [test_preprocessing.elements.get_bit(ctx) for _ in range(num_bits)]
        x = ctx.ShareArray(shares)
        x_ = await x.open()
        for i in x_:
            assert i == 0 or i == 1

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_powers(test_preprocessing):
    n, t = 4, 1
    nums, num_powers = 2, 3

    test_preprocessing.generate("powers", n, t, num_powers, nums)

    async def _prog(ctx):
        for i in range(nums):
            powers = test_preprocessing.elements.get_powers(ctx, i)
            x = await powers[0].open()
            for i, power in enumerate(powers[1:]):
                assert await power.open() == pow(x, i + 2)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_share(test_preprocessing):
    n, t = 4, 1
    x = 41
    sid = test_preprocessing.generate("share", n, t, x)

    async def _prog(ctx):
        x_sh = test_preprocessing.elements.get_share(ctx, sid)
        assert await x_sh.open() == x

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_double_share(test_preprocessing):
    n, t = 9, 2
    test_preprocessing.generate("double_shares", n, t)

    async def _prog(ctx):
        r_t_sh, r_2t_sh = test_preprocessing.elements.get_double_share(ctx)
        assert r_t_sh.t == ctx.t
        assert r_2t_sh.t == ctx.t * 2
        await r_t_sh.open()
        await r_2t_sh.open()
        assert await r_t_sh.open() == await r_2t_sh.open()

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_share_bits(test_preprocessing):
    n, t, = 4, 1
    test_preprocessing.generate("share_bits", n, t, k=1)

    async def _prog(ctx):
        share, bits = test_preprocessing.elements.get_share_bits(ctx)
        opened_share = await share.open()
        opened_bits = await asyncio.gather(*[b.open() for b in bits])
        bit_value = int("".join([str(b.value) for b in reversed(opened_bits)]), 2)
        assert bit_value == opened_share.value

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
