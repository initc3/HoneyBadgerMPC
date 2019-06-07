from pytest import mark
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiply
from honeybadgermpc.progs.mixins.constants import MixinConstants
from honeybadgermpc.preprocessing import PreProcessedElements
import asyncio


@mark.asyncio
async def test_open_shares():
    n, t = 3, 1
    number_of_secrets = 100
    pp_elements = PreProcessedElements()
    pp_elements.generate_zeros(1000, n, t)

    async def _prog(context):
        secrets = []
        for _ in range(number_of_secrets):
            s = await context.preproc.get_zero(context).open()
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
async def test_open_future_shares():
    n, t = 4, 1
    pp_elements = PreProcessedElements()
    pp_elements.generate_rands(1000, n, t)
    pp_elements.generate_triples(1000, n, t)

    async def _prog(context):
        e1_, e2_ = [context.preproc.get_rand(context) for _ in range(2)]
        e1, e2 = await asyncio.gather(*[e1_.open(), e2_.open()], return_exceptions=True)

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
