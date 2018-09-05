import random
from pytest import mark


# TODO: Move to fixtures and don't build for each test.
basedir = "sharedata"


@mark.asyncio
async def test_powers(sharedatadir):
    from honeybadgermpc.passive import TaskProgramRunner, Field
    import apps.shuffle.powermixing as pm

    async def verify_powers(context, **kwargs):
        a_, b_, k_ = kwargs['a'], kwargs['b'], kwargs['k']
        filename = f'{basedir}/test-powers-{context.myid}.share'
        shares = context.read_shares(open(filename))
        a, powers = shares[0], shares[1:]
        assert len(powers) == k_
        assert a_ == await a.open()
        for i, power in enumerate(powers):
            assert pow(b_, i+1) == await power.open()

    a = Field(random.randint(0, Field.modulus-1))
    b = Field(random.randint(0, Field.modulus-1))
    N, t, k = 5, 2, 32
    pm.generate_test_powers(f"{basedir}/test-powers", a, b, k, N, t)
    programRunner = TaskProgramRunner(N, t)
    programRunner.add(verify_powers, a=a, b=b, k=k)
    await programRunner.join()


@mark.asyncio
async def test_phase1(sharedatadir):
    from honeybadgermpc.passive import TaskProgramRunner, Field
    import apps.shuffle.powermixing as pm

    async def verify_phase1(context, **kwargs):
        a_, b_, k_ = kwargs['a'], kwargs['b'], kwargs['k']
        await pm.phase1(context, k, f"{basedir}/test-phase1", f"{basedir}/test-cpp")
        with open(f"{basedir}/test-cpp-{context.myid}.input", "r") as f:
            assert int(f.readline()) == Field.modulus
            assert await context.Share(int(f.readline())).open() == a_.value
            assert int(f.readline()) == (a_ - b_).value
            assert int(f.readline()) == k_
            for i in range(1, k_+1):
                assert (await context.Share(int(f.readline())).open()).value == b_**(i)

    a = Field(random.randint(0, Field.modulus-1))
    b = Field(random.randint(0, Field.modulus-1))
    N, t, k = 5, 2, 32
    pm.generate_test_powers(f"{basedir}/test-phase1", a, b, k, N, t)
    programRunner = TaskProgramRunner(N, t)
    programRunner.add(verify_phase1, a=a, b=b, k=k)
    await programRunner.join()


@mark.asyncio
async def test_phase2(sharedatadir):
    from honeybadgermpc.passive import Field
    import apps.shuffle.powermixing as pm
    import uuid

    a = Field(random.randint(0, Field.modulus-1))
    b = Field(random.randint(0, Field.modulus-1))
    k = 8
    runid, nodeid = uuid.uuid4().hex, "1"
    batchid = f"{runid}_0"
    cppPrefix = f"{basedir}/cpp-phase_{batchid}"

    for j in range(1, k):
        with open(f"{cppPrefix}-{nodeid}.input", "w") as f:
            print(Field.modulus, file=f)
            print(a.value, file=f)
            print((a-b).value, file=f)
            print(k, file=f)
            for i in range(1, k+1):
                print(pow(b, i).value, file=f)
        print("#" * 10)
        await pm.phase2(nodeid, batchid, runid, cppPrefix)

        with open(f"{basedir}/power-{runid}_{nodeid}.sums", "r") as f:
            assert int(f.readline()) == Field.modulus
            assert int(f.readline()) == k
            for i, p in enumerate(f.read().splitlines()[:k]):
                assert int(p) == (pow(a, i+1) * j).value


@mark.asyncio
async def test_asynchronous_mixing(sharedatadir):
    from honeybadgermpc.passive import Field
    import apps.shuffle.powermixing as pm

    N, t, k = 3, 1, 2
    a_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    result = await pm.asynchronusMixing(a_s, N, t, k)
    for a in a_s:
        assert a in result
