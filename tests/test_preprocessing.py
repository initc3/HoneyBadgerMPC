from pytest import mark, raises
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.preprocessing import PreProcessedElements


@mark.asyncio
async def test_get_triple():
    pp_elements = PreProcessedElements()
    n, t = 4, 1
    num_triples = 2
    pp_elements.generate_triples(num_triples, n, t)

    async def _prog(ctx):
        for _ in range(num_triples):
            a_sh, b_sh, ab_sh = pp_elements.get_triple(ctx)
            a, b, ab = await a_sh.open(), await b_sh.open(), await ab_sh.open()
            assert a*b == ab

        # Get one more than the number of generated triples to test
        # that only the required number of triples are generated
        with raises(StopIteration):
            pp_elements.get_triple(ctx)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_zero():
    pp_elements = PreProcessedElements()
    n, t = 4, 1
    num_zeros = 2
    pp_elements.generate_zeros(num_zeros, n, t)

    async def _prog(ctx):
        for _ in range(num_zeros):
            x_sh = pp_elements.get_zero(ctx)
            assert await x_sh.open() == 0

        # Get one more than the number of generated zeros to test
        # that only the required number of zeros are generated
        with raises(StopIteration):
            pp_elements.get_zero(ctx)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_rand():
    pp_elements = PreProcessedElements()
    n, t = 4, 1
    num_rands = 2
    pp_elements.generate_rands(num_rands, n, t)

    async def _prog(ctx):
        for _ in range(num_rands):
            # Nothing to assert here, just check if the
            # required number of rands are generated
            pp_elements.get_rand(ctx)

        # Get one more than the number of generated rands to test
        # that only the required number of rands are generated
        with raises(StopIteration):
            pp_elements.get_rand(ctx)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_powers():
    pp_elements = PreProcessedElements()
    n, t = 4, 1
    num_powers = 3
    pid = pp_elements.generate_powers(num_powers, n, t)

    async def _prog(ctx):
        powers = pp_elements.get_powers(ctx, pid)
        x = await powers[0].open()
        for i, power in enumerate(powers[1:]):
            assert await power.open() == pow(x, i+2)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_get_share():
    pp_elements = PreProcessedElements()
    n, t = 4, 1
    x = 41
    sid = pp_elements.generate_share(x, n, t)

    async def _prog(ctx):
        x_sh = pp_elements.get_share(ctx, sid)
        assert await x_sh.open() == x

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
