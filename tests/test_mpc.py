from pytest import mark
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply
from honeybadgermpc.progs.mixins.constants import MixinConstants
import asyncio


@mark.asyncio
async def test_empty_shares():
    n, t = 3, 1

    async def _prog(context):
        return await context.open_share_array(context.ShareArray([]))

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert results == [[] for _ in range(n)]


@mark.asyncio
async def test_open_shares(test_preprocessing):
    n, t = 3, 1
    number_of_secrets = 100
    test_preprocessing.generate("zeros", n, t)

    async def _prog(context):
        secrets = []
        for _ in range(number_of_secrets):
            s = await test_preprocessing.elements.get_zero(context).open()
            assert s == 0
            secrets.append(s)
        print("[%d] Finished" % (context.myid,))
        return secrets

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(_prog)
    results = await program_runner.join()
    assert len(results) == n
    assert all(len(secrets) == number_of_secrets for secrets in results)
    assert all(secret == 0 for secrets in results for secret in secrets)


@mark.asyncio
async def test_open_future_shares(test_preprocessing):
    n, t = 3, 1

    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("triples", n, t)

    async def _prog(context):
        e1_, e2_ = [test_preprocessing.elements.get_rand(context, t) for _ in range(2)]
        e1, e2 = await asyncio.gather(*[e1_.open(), e2_.open()])

        s_prod_f = e1_ * e2_
        s_prod_f2 = s_prod_f * e1_
        final_prod = s_prod_f2 + e1_ + e2_
        final_prod_2 = final_prod * e1_
        wrapped_final_prod_2 = context.Share(final_prod_2.open())

        assert await s_prod_f2.open() == e1 * e1 * e2
        assert await final_prod.open() == e1 * e1 * e2 + e1 + e2
        assert await final_prod_2.open() == (e1 * e1 * e2 + e1 + e2) * e1
        assert await wrapped_final_prod_2.open() == await final_prod_2.open()

    program_runner = TaskProgramRunner(
        n, t, {MixinConstants.MultiplyShare: BeaverMultiply()}
    )
    program_runner.add(_prog)
    await program_runner.join()
