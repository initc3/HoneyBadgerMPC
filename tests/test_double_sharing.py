from random import randint
from pytest import mark


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_degree_reduction(test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.elliptic_curve import Subgroup

    n, t = 9, 2

    r = randint(0, Subgroup.BLS12_381-1)
    x_expected = randint(0, Subgroup.BLS12_381-1)

    sid_r_t = test_preprocessing.generate("share", n, t, r)
    sid_r_2t = test_preprocessing.generate("share", n, 2*t, r)
    sid_x_2t = test_preprocessing.generate("share", n, 2*t, x_expected)

    async def _prog(context):
        sh_r_t = test_preprocessing.elements.get_share(context, sid_r_t)
        context.t = 2*t
        sh_r_2t = test_preprocessing.elements.get_share(context, sid_r_2t)
        sh_x_2t = test_preprocessing.elements.get_share(context, sid_x_2t)
        context.t = t
        diff_2t = await context.Share((sh_x_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        x_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert x_expected == x_actual

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_multiplication_using_double_sharing(galois_field, test_preprocessing):
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t = 9, 2
    r = randint(0, galois_field.modulus-1)

    sid_r_t = test_preprocessing.generate("share", n, t, r)
    sid_r_2t = test_preprocessing.generate("share", n, 2*t, r)
    test_preprocessing.generate("rands", n, t)

    async def _prog(context):
        sh_r_t = test_preprocessing.elements.get_share(context, sid_r_t)
        context.t = 2*t
        r_2t = test_preprocessing.elements.get_share(context, sid_r_2t).v
        sh_r_2t = context.Share(r_2t, 2*t)
        context.t = t
        sh_a = test_preprocessing.elements.get_rand(context)
        sh_b = test_preprocessing.elements.get_rand(context)
        ab_expected = await sh_a.open() * await sh_b.open()

        sh_ab_2t = context.Share(sh_a.v * sh_b.v, 2*t)
        diff_2t = await context.Share((sh_ab_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        ab_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert ab_expected == ab_actual

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    await program_runner.join()
