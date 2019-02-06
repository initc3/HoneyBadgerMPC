import random
from pytest import mark


@mark.asyncio
async def test_phase1(test_preprocessing, galois_field):
    from honeybadgermpc.mpc import TaskProgramRunner
    from honeybadgermpc.preprocessing import PreProcessingConstants
    import apps.shuffle.powermixing as pm

    field = galois_field
    a = field(random.randint(0, field.modulus-1))
    n, t, k = 5, 2, 32
    power_id = test_preprocessing.generate("powers", n, t, k)
    share_id = test_preprocessing.generate("share", n, t, a)

    async def verify_phase1(context, **kwargs):
        a_, k_ = kwargs['a'], kwargs['k']
        b_ = await test_preprocessing.elements.get_powers(context, power_id)[0].open()
        await pm.single_secret_phase1(
            context,
            k=k,
            power_id=power_id,
            share_id=share_id)
        file_name = f"{share_id}-{context.myid}.input"
        file_path = f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}"
        with open(file_path, "r") as f:
            assert int(f.readline()) == field.modulus
            assert await context.Share(int(f.readline())).open() == a_.value
            assert int(f.readline()) == (a_ - b_).value
            assert int(f.readline()) == k_
            for i in range(1, k_+1):
                assert (await context.Share(int(f.readline())).open()).value == b_**(i)

    program_runner = TaskProgramRunner(n, t)
    program_runner.add(verify_phase1, a=a, k=k)
    await program_runner.join()


@mark.asyncio
async def test_phase2(galois_field):
    from honeybadgermpc.preprocessing import PreProcessingConstants
    import apps.shuffle.powermixing as pm
    import uuid

    field = galois_field
    a = field(random.randint(0, field.modulus-1))
    b = field(random.randint(0, field.modulus-1))
    k = 8
    share_id, run_id, node_id = uuid.uuid4().hex, uuid.uuid4().hex, "1"

    for j in range(1, k):
        file_name = f"{share_id}-{node_id}.input"
        with open(f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}", "w") as f:
            print(field.modulus, file=f)
            print(a.value, file=f)
            print((a-b).value, file=f)
            print(k, file=f)
            for i in range(1, k+1):
                print(pow(b, i).value, file=f)

        await pm.phase2(node_id, run_id, share_id)

        file_name = f"power-{run_id}_{node_id}.sums"
        with open(f"{PreProcessingConstants.SHARED_DATA_DIR}{file_name}", "r") as f:
            assert int(f.readline()) == field.modulus
            assert int(f.readline()) == k
            for i, p in enumerate(f.read().splitlines()[:k]):
                assert int(p) == (pow(a, i+1) * j).value


@mark.asyncio
async def test_asynchronous_mixing(galois_field):
    import apps.shuffle.powermixing as pm

    field = galois_field
    n, t, k = 3, 1, 2
    a_s = [field(random.randint(0, field.modulus-1)) for _ in range(k)]
    result = await pm.async_mixing(a_s, n, t, k)
    for a in a_s:
        assert a in result
