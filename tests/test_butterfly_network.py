from pytest import mark
from math import log


@mark.asyncio
async def test_butterfly_network(sharedatadir):
    import apps.shuffle.butterfly_network as butterfly
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessedElements

    N, t, k, delta = 3, 1, 32, -9999
    num_switches = k*int(log(k, 2))**2
    pp_elements = PreProcessedElements()
    pp_elements.generate_rands(1000, N, t)
    pp_elements.generate_one_minus_one_rands(num_switches, N, t)
    pp_elements.generate_triples(2*num_switches, N, t)

    async def verify_output(ctx, **kwargs):
        k, delta = kwargs['k'], kwargs['delta']
        inputs = [pp_elements.get_rand(ctx) for _ in range(k)]
        sorted_input = sorted(await ctx.ShareArray(inputs).open(), key=lambda x: x.value)

        share_arr = await butterfly.butterfly_network_helper(ctx, k=k, delta=delta)
        outputs = await share_arr.open()

        assert len(sorted_input) == len(outputs)
        sorted_output = sorted(outputs, key=lambda x: x.value)
        for i, j in zip(sorted_input, sorted_output):
            assert i == j

    program_runner = TaskProgramRunner(N, t)
    program_runner.add(verify_output,  k=k, delta=delta)
    await program_runner.join()
