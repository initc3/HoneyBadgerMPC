from pytest import mark
from honeybadgermpc.preprocessing import PreProcessedElements
import apps.asynchromix.butterfly_network as butterfly
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiplyArrays
from honeybadgermpc.progs.mixins.constants import MixinConstants
import apps.asynchromix.powermixing as pm
from uuid import uuid4


@mark.asyncio
async def test_butterfly_network():
    n, t, k, delta = 3, 1, 32, -9999
    pp_elements = PreProcessedElements()
    pp_elements.generate_rands(1000, n, t)
    pp_elements.generate_one_minus_ones(1000, n, t)
    pp_elements.generate_triples(1500, n, t)

    async def verify_output(ctx, **kwargs):
        k, delta = kwargs["k"], kwargs["delta"]
        inputs = [ctx.preproc.get_rand(ctx) for _ in range(k)]
        sorted_input = sorted(
            await ctx.ShareArray(inputs).open(), key=lambda x: x.value
        )

        share_arr = await butterfly.butterfly_network_helper(
            ctx, k=k, delta=delta, inputs=inputs
        )
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
async def test_phase1(galois_field):
    field = galois_field
    n, t, k = 5, 2, 1
    pp_elements = PreProcessedElements()
    pp_elements.generate_powers(k, n, t, 1)
    pp_elements.generate_rands(k, n, t)

    async def verify_phase1(ctx, **kwargs):
        k_ = kwargs["k"]
        b_ = await ctx.preproc.get_powers(ctx, 0)[0].open()
        file_prefixes = [uuid4().hex]
        await pm.all_secrets_phase1(ctx, k=k, file_prefixes=file_prefixes)
        file_name = f"{file_prefixes[0]}-{ctx.myid}.input"
        file_path = f"{pp_elements.data_directory}{file_name}"
        with open(file_path, "r") as f:
            assert int(f.readline()) == field.modulus
            # next line is a random share, which should open successfully
            a_ = await ctx.Share(int(f.readline())).open()
            assert int(f.readline()) == (a_ - b_).value
            assert int(f.readline()) == k_
            for i in range(1, k_ + 1):
                assert (await ctx.Share(int(f.readline())).open()).value == b_ ** (i)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(verify_phase1, k=k)
    await program_runner.join()


@mark.asyncio
async def test_phase2(galois_field):

    field = galois_field
    a = field.random()
    b = field.random()
    k = 8
    share_id, run_id, node_id = uuid4().hex, uuid4().hex, "1"

    for j in range(1, k):
        file_name = f"{share_id}-{node_id}.input"
        with open(f"{PreProcessedElements.DEFAULT_DIRECTORY}{file_name}", "w") as f:
            print(field.modulus, file=f)
            print(a.value, file=f)
            print((a - b).value, file=f)
            print(k, file=f)
            for i in range(1, k + 1):
                print(pow(b, i).value, file=f)

        await pm.phase2(node_id, run_id, share_id)

        file_name = f"power-{run_id}_{node_id}.sums"
        with open(f"{PreProcessedElements.DEFAULT_DIRECTORY}{file_name}", "r") as f:
            assert int(f.readline()) == field.modulus
            assert int(f.readline()) == k
            for i, p in enumerate(f.read().splitlines()[:k]):
                assert int(p) == (pow(a, i + 1) * j).value


@mark.asyncio
async def test_asynchronous_mixing():
    import asyncio
    import apps.asynchromix.powermixing as pm
    from honeybadgermpc.mpc import TaskProgramRunner

    n, t, k = 3, 1, 4
    pp_elements = PreProcessedElements()
    pp_elements.generate_powers(k, n, t, k)
    pp_elements.generate_rands(1000, n, t)

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
