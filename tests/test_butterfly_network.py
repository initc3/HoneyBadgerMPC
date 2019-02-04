from pytest import mark


@mark.asyncio
@mark.usefixtures('test_preprocessing')
async def test_butterfly_network(test_preprocessing):
    import apps.shuffle.butterfly_network as butterfly
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t, k, delta = 3, 1, 32, -9999
    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("oneminusone", n, t)
    test_preprocessing.generate("triples", n, t)

    async def verify_output(ctx, **kwargs):
        k, delta = kwargs['k'], kwargs['delta']
        inputs = [test_preprocessing.elements.get_rand(ctx) for _ in range(k)]
        sorted_input = sorted(await ctx.ShareArray(inputs).open(), key=lambda x: x.value)

        share_arr = await butterfly.butterfly_network_helper(ctx, k=k, delta=delta)
        outputs = await share_arr.open()

        assert len(sorted_input) == len(outputs)
        sorted_output = sorted(outputs, key=lambda x: x.value)
        for i, j in zip(sorted_input, sorted_output):
            assert i == j

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(verify_output,  k=k, delta=delta)
    await program_runner.join()
