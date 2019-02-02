from random import randint
from pytest import mark


@mark.asyncio
async def test_degree_reduction():
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessedElements
    from honeybadgermpc.elliptic_curve import Subgroup

    n, t = 9, 2

    r = randint(0, Subgroup.BLS12_381-1)
    x_expected = randint(0, Subgroup.BLS12_381-1)

    pp_elements = PreProcessedElements()
    sid_r_t = pp_elements.generate_share(r, n, t)
    sid_r_2t = pp_elements.generate_share(r, n, 2*t)
    sid_x_2t = pp_elements.generate_share(x_expected, n, 2*t)

    async def _prog(context):
        sh_r_t = pp_elements.get_share(context, sid_r_t)
        sh_r_2t = pp_elements.get_share(context, sid_r_2t)
        sh_x_2t = pp_elements.get_share(context, sid_x_2t)
        diff_2t = await context.Share((sh_x_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        x_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert x_expected == x_actual

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
async def test_multiplication_using_double_sharing():
    from honeybadgermpc.field import GF
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.elliptic_curve import Subgroup
    from honeybadgermpc.preprocessing import PreProcessedElements

    n, t = 9, 2

    field = GF.get(Subgroup.BLS12_381)
    r = randint(0, field.modulus-1)

    pp_elements = PreProcessedElements()
    sid_r_t = pp_elements.generate_share(r, n, t)
    sid_r_2t = pp_elements.generate_share(r, n, 2*t)
    pp_elements.generate_rands(2, n, t)

    async def _prog(context):
        sh_r_t = pp_elements.get_share(context, sid_r_t)
        sh_r_2t = pp_elements.get_share(context, sid_r_2t)

        sh_a = pp_elements.get_rand(context)
        sh_b = pp_elements.get_rand(context)
        ab_expected = await sh_a.open() * await sh_b.open()

        sh_ab_2t = context.Share(sh_a.v * sh_b.v)
        diff_2t = await context.Share((sh_ab_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        ab_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert ab_expected == ab_actual

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
