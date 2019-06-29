from pytest import mark


@mark.asyncio
async def test_butterfly_network(test_preprocessing):
    import apps.asynchromix.butterfly_network as butterfly
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiplyArrays
    from honeybadgermpc.progs.mixins.constants import MixinConstants

    n, t, k, delta = 3, 1, 32, -9999
    test_preprocessing.generate("rands", n, t)
    test_preprocessing.generate("oneminusone", n, t)
    test_preprocessing.generate("triples", n, t)

    async def verify_output(ctx, **kwargs):
        k, delta = kwargs["k"], kwargs["delta"]
        inputs = [test_preprocessing.elements.get_rand(ctx) for _ in range(k)]
        sorted_input = sorted(
            await ctx.ShareArray(inputs).open(), key=lambda x: x.value
        )

        share_arr = await butterfly.butterfly_network_helper(ctx, k=k, delta=delta)
        outputs = await share_arr.open()

        assert len(sorted_input) == len(outputs)
        sorted_output = sorted(outputs, key=lambda x: x.value)
        for i, j in zip(sorted_input, sorted_output):
            assert i == j

    program_runner = TaskProgramRunner(
        n, t, {MixinConstants.MultiplyShareArray: BeaverMultiplyArrays()}
    )
    program_runner.add(verify_output, k=k, delta=delta)
    await program_runner.join()


@mark.asyncio
async def test_phase1(test_preprocessing, galois_field):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessingConstants
    import apps.asynchromix.powermixing as pm
    from uuid import uuid4

    field = galois_field
    n, t, k = 5, 2, 1
    test_preprocessing.generate("powers", n, t, k, 1)
    test_preprocessing.generate("rands", n, t)

    async def verify_phase1(context, **kwargs):
        k_ = kwargs["k"]
        b_ = await test_preprocessing.elements.get_powers(context, 0)[0].open()
        file_prefixes = [uuid4().hex]
        await pm.all_secrets_phase1(context, k=k, file_prefixes=file_prefixes)
        file_name = f"{file_prefixes[0]}-{context.myid}.input"
        file_path = f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}"
        with open(file_path, "r") as f:
            assert int(f.readline()) == field.modulus
            # next line is a random share, which should open successfully
            a_ = await context.Share(int(f.readline())).open()
            assert int(f.readline()) == (a_ - b_).value
            assert int(f.readline()) == k_
            for i in range(1, k_ + 1):
                assert (await context.Share(int(f.readline())).open()).value == b_ ** (
                    i
                )

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(verify_phase1, k=k)
    await program_runner.join()


@mark.asyncio
async def test_phase2(galois_field):
    from honeybadgermpc.preprocessing import PreProcessingConstants
    import apps.asynchromix.powermixing as pm
    import uuid

    field = galois_field
    a = field.random()
    b = field.random()
    k = 8
    share_id, run_id, node_id = uuid.uuid4().hex, uuid.uuid4().hex, "1"

    for j in range(1, k):
        file_name = f"{share_id}-{node_id}.input"
        with open(f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}", "w") as f:
            print(field.modulus, file=f)
            print(a.value, file=f)
            print((a - b).value, file=f)
            print(k, file=f)
            for i in range(1, k + 1):
                print(pow(b, i).value, file=f)

        await pm.phase2(node_id, run_id, share_id)

        file_name = f"power-{run_id}_{node_id}.sums"
        with open(f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}", "r") as f:
            assert int(f.readline()) == field.modulus
            assert int(f.readline()) == k
            for i, p in enumerate(f.read().splitlines()[:k]):
                assert int(p) == (pow(a, i + 1) * j).value


@mark.asyncio
async def test_asynchronous_mixing(test_preprocessing):
    import asyncio
    import apps.asynchromix.powermixing as pm
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t, k = 3, 1, 4
    test_preprocessing.generate("powers", n, t, k, k)
    test_preprocessing.generate("rands", n, t)

    async def verify_output(context, **kwargs):
        result, input_shares = kwargs["result"], kwargs["input_shares"]
        my_shares = input_shares[context.myid]
        assert len(result) == len(my_shares)

        inputs = await asyncio.gather(
            *[context.Share(sh.v, t).open() for sh in my_shares]
        )
        assert sorted(map(lambda x: x.value, inputs)) == sorted(result)

    result, input_shares = await pm.async_mixing(n, t, k)
    program_runner = TaskProgramRunner(n, t)
    program_runner.add(verify_output, result=result, input_shares=input_shares)
    await program_runner.join()
