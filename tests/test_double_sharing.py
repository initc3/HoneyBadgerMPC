from random import randint
from pytest import mark


@mark.asyncio
async def test_degree_reduction():
    from honeybadgermpc.field import GF
    from honeybadgermpc.mpc import TaskProgramRunner, write_polys
    from honeybadgermpc.polynomial import polynomials_over
    from honeybadgermpc.elliptic_curve import Subgroup

    n, t = 9, 2

    field = GF.get(Subgroup.BLS12_381)
    poly = polynomials_over(field)

    r = randint(0, field.modulus-1)
    x_expected = randint(0, field.modulus-1)

    polys = [poly.random(t, r), poly.random(2*t, r), poly.random(2*t, x_expected)]
    file_prefix = "sharedata/test_degree_reduction"
    write_polys(file_prefix, field.modulus, n, t, polys)

    async def _prog(context):
        file_name = f'{file_prefix}-{context.myid}.share'
        sh_r_t, sh_r_2t, sh_x_2t = context.read_shares(open(file_name))
        diff_2t = await context.Share((sh_x_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        x_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert x_expected == x_actual

    programRunner = TaskProgramRunner(n, t)
    programRunner.add(_prog)
    await programRunner.join()


@mark.asyncio
async def test_multiplication_using_double_sharing():
    from honeybadgermpc.field import GF
    from honeybadgermpc.mpc import TaskProgramRunner, write_polys
    from honeybadgermpc.polynomial import polynomials_over
    from honeybadgermpc.elliptic_curve import Subgroup

    n, t = 9, 2

    field = GF.get(Subgroup.BLS12_381)
    poly = polynomials_over(field)

    r = randint(0, field.modulus-1)
    a = randint(0, field.modulus-1)
    b = randint(0, field.modulus-1)
    ab_expected = field(a) * field(b)

    polys = [
        poly.random(t, r),
        poly.random(2*t, r),
        poly.random(t, a),
        poly.random(t, b),
        ]

    file_prefix = "sharedata/test_multiplication_using_double_sharing"
    write_polys(file_prefix, field.modulus, n, t, polys)

    async def _prog(context):
        file_name = f'{file_prefix}-{context.myid}.share'
        sh_r_t, sh_r_2t, sh_a, sh_b = context.read_shares(open(file_name))
        sh_ab_2t = context.Share(sh_a.v * sh_b.v)
        diff_2t = await context.Share((sh_ab_2t - sh_r_2t).v, 2*t).open()  # noqa: W606
        ab_actual = await (sh_r_t + context.Share(diff_2t)).open()  # noqa: W606
        assert ab_expected == ab_actual

    programRunner = TaskProgramRunner(n, t)
    programRunner.add(_prog)
    await programRunner.join()
