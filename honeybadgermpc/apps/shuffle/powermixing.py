import random
import asyncio
import uuid
from honeybadgermpc.passive import write_polys, runProgramAsTasks, Field, Poly


shufflebasedir = "honeybadgermpc/apps/shuffle"
sharedatadir = "sharedata"
powersPrefix = f"{sharedatadir}/powers"
cppPrefix = f"{sharedatadir}/cpp-phase"


def generate_test_powers(prefix, a, b, k, N, t):
    # Generate k powers, store in files of form "prefix-%d.share"
    polys = [Poly.random(t, a)]
    for j in range(1, k+1):
        polys.append(Poly.random(t, pow(b, j)))
    write_polys(prefix, Field.modulus, N, t, polys)


async def phase1(context, k, powers_prefix, cpp_prefix):
    filename = f"{powers_prefix}-{context.myid}.share"
    shares = context.read_shares(open(filename))
    a, powers = shares[0], shares[1:]
    b = powers[0]
    assert k == len(powers)
    aMinusB = await (a - b).open()  # noqa: W606
    with open(f"{cpp_prefix}-{context.myid}.input", "w") as f:
        print(Field.modulus, file=f)
        print(a.v.value, file=f)
        print(aMinusB.value, file=f)
        print(k, file=f)
        for power in powers:
            print(power.v.value, file=f)


async def phase2(nodeid, batchid, runid, cpp_prefix):
    filename = f"{cpp_prefix}-{nodeid}.input"
    sumFileName = f"{sharedatadir}/power-{runid}_{nodeid}.sums"
    runcmd = f"{shufflebasedir}/cpp/compute-power-sums {filename} {sumFileName}"
    await runCommandSync(runcmd)


async def runCommandSync(command, verbose=False):
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if verbose:
        print(f"{'#' * 10} OUTPUT {'#' * 10}")
        print(stdout)
        print("#" * 30)

    if len(stderr) != 0:
        print(f"{'#' * 10} ERROR {'#' * 10}")
        print(stderr)
        print("#" * 30)


async def prepareOneInput(context, **kwargs):
    k, batchid, runid = kwargs['k'], kwargs['batchid'], kwargs['runid']
    await phase1(context, k, f"{powersPrefix}_{batchid}", f"{cppPrefix}_{batchid}")
    print(f"[{context.myid}] Input prepared for C++ phase.")
    await phase2(context.myid, batchid, runid, f"{cppPrefix}_{batchid}")
    print(f"[{context.myid}] C++ phase completed.")


async def phase3(context, **kwargs):
    k, runid = kwargs['k'], kwargs['runid']
    sumFileName = f"{sharedatadir}/power-{runid}_{context.myid}.sums"
    sumShares = []
    with open(sumFileName, "r") as f:
        assert Field.modulus == int(f.readline())
        assert k == int(f.readline())
        sumShares = [context.Share(int(s)) for s in f.read().splitlines()[:k]]
        assert len(sumShares) == k
    tasks = [share.open() for share in sumShares]
    openedShares = await asyncio.gather(*tasks)
    return openedShares


async def asynchronusMixing(a_s, N, t, k):
    from honeybadgermpc.apps.shuffle.solver.solver import solve

    tasks = []
    runid = uuid.uuid4().hex
    for i, a in enumerate(a_s):
        b = Field(random.randint(0, Field.modulus-1))
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b, k, N, t)
        tasks.append(
            runProgramAsTasks(prepareOneInput, N, t, k=k, batchid=batchid, runid=runid)
        )
    await asyncio.gather(*tasks)
    powerSums = (await runProgramAsTasks(phase3, N, t, k=k, runid=runid))[0]
    print(f"Shares from C++ phase opened.")
    result = solve([s.value for s in powerSums])
    print(f"Equation solver completed.")
    return result


async def buildNewtonSolver():
    await runCommandSync(f"python {shufflebasedir}/solver/solver_build.py")


async def buildPowerMixingCppCode():
    await runCommandSync(f"make -C {shufflebasedir}/cpp")


def asynchronusMixingInTasks():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    N, t, k = 3, 1, 2
    a_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    try:
        loop.run_until_complete(buildNewtonSolver())
        print("Solver built.")
        loop.run_until_complete(buildPowerMixingCppCode())
        print("C++ code built.")
        loop.run_until_complete(asynchronusMixing(a_s, N, t, k))
    finally:
        loop.close()


async def asynchronusMixingInProcesses(network_info, N, t, k, runid, nodeid):
    from honeybadgermpc.apps.shuffle.solver.solver import solve
    from honeybadgermpc.ipc import runProgramAsProcesses

    for i in range(k):
        batchid = f"{runid}_{i}"
        await runProgramAsProcesses(
            prepareOneInput,
            network_info,
            N,
            t,
            nodeid,
            k=k,
            batchid=batchid,
            runid=runid
        )

    powerSums = await runProgramAsProcesses(
        phase3, network_info, N, t, nodeid, k=k, runid=runid
    )
    print(f"Shares from C++ phase opened.")
    result = solve([s.value for s in powerSums])
    print(f"Equation solver completed.")
    print(result)
    return result


if __name__ == "__main__":
    import os
    import sys
    from honeybadgermpc.config import load_config
    from honeybadgermpc.ipc import NodeDetails

    nodeid = int(sys.argv[1])
    configfile = sys.argv[2]
    config_dict = load_config(configfile)

    N = config_dict['N']
    t = config_dict['t']

    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    # Need to keep these fixed when running on processes.
    k = 4
    a_s = [Field(i) for i in range(100+k, 100, -1)]
    b_s = [Field(i) for i in range(10, 10+k)]
    runid = "82d7c0b8040f4ca1b3ff6b9d27888fef"

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    try:
        if nodeid == 0:
            os.makedirs("sharedata/", exist_ok=True)
            loop.run_until_complete(runCommandSync("rm -f sharedata/**"))
            for i, a in enumerate(a_s):
                batchid = f"{runid}_{i}"
                generate_test_powers(f"{powersPrefix}_{batchid}", a, b_s[i], k, N, t)
        else:
            loop.run_until_complete(asyncio.sleep(1))
        loop.run_until_complete(
            asynchronusMixingInProcesses(network_info, N, t, k, runid, nodeid)
        )
    finally:
        loop.close()

    # asynchronusMixingInTasks()
