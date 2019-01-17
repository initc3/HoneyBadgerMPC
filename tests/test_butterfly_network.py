from pytest import mark
from math import log


@mark.asyncio
async def test_butterfly_network(sharedatadir):
    import apps.shuffle.butterfly_network as butterfly
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.mpc import (
        generate_test_triples, generate_test_randoms, random_files_prefix)

    async def verify_output(ctx, **kwargs):
        k, delta = kwargs['k'], kwargs['delta']
        inputs = ctx.read_shares(open(f"{random_files_prefix}-{ctx.myid}.share"))[:k]
        sortedinput = sorted(await ctx.ShareArray(inputs).open(), key=lambda x: x.value)

        shareArr = await butterfly.butterfly_network_helper(ctx, k=k, delta=delta)
        outputs = await shareArr.open()

        assert len(sortedinput) == len(outputs)
        sortedoutput = sorted(outputs, key=lambda x: x.value)
        for i, j in zip(sortedinput, sortedoutput):
            assert i == j

    N, t, k, delta = 3, 1, 32, -9999
    generate_test_randoms(random_files_prefix, 1000, N, t)
    NUM_SWITCHES = k*int(log(k, 2))**2
    butterfly.generate_random_shares(butterfly.oneminusoneprefix, NUM_SWITCHES, N, t)
    generate_test_triples(butterfly.triplesprefix, 2*NUM_SWITCHES, N, t)
    programRunner = TaskProgramRunner(N, t)
    programRunner.add(verify_output,  k=k, delta=delta)
    await programRunner.join()
