import asyncio
from pytest import mark
from math import log
import random


@mark.asyncio
async def test_butterfly_network(sharedatadir):
    import apps.shuffle.butterfly_network as butterfly
    from honeybadgermpc.passive import generate_test_triples, Field, TaskProgramRunner

    async def verify_output(ctx, **kwargs):
        print(kwargs)
        k, delta, inputs = kwargs['k'], kwargs['delta'], kwargs['inputs']
        shares = await butterfly.butterflyNetwork(ctx, k=k, delta=delta, inputs=inputs)
        outputs = await asyncio.gather(*[s.open() for s in shares])
        assert len(inputs) == len(outputs)
        sortedinput = sorted(inputs, key=lambda x: x.value)
        sortedoutput = sorted(outputs, key=lambda x: x.value)
        for i, j in zip(sortedinput, sortedoutput):
            assert i == j

    N, t, k, delta = 3, 1, 32, -9999
    butterfly.generate_random_shares(butterfly.oneminusoneprefix, k*int(log(k, 2)), N, t)
    generate_test_triples(butterfly.triplesprefix, 1000, N, t)
    inputs = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    programRunner = TaskProgramRunner(N, t)
    programRunner.add(verify_output,  k=k, delta=delta, inputs=inputs)
    await programRunner.join()
