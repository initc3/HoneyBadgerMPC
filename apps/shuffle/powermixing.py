import random
import asyncio
import uuid
import os
from honeybadgermpc.passive import write_polys, TaskProgramRunner, Field, Poly


shufflebasedir = "apps/shuffle"
sharedatadir = "sharedata"
powersPrefix = f"{sharedatadir}/powers"
cppPrefix = f"{sharedatadir}/cpp-phase"


async def wait_for_preprocessing():
    while not os.path.exists(f"{sharedatadir}/READY"):
        print(f"waiting for preprocessing {sharedatadir}/READY")
        await asyncio.sleep(1)


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
    # NOTE The binary `compute-power-sums` is generated via the command
    # make -C apps/shuffle/cpp
    # and is stored under /usr/local/bin/
    runcmd = f"compute-power-sums {filename} {sumFileName}"
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
    from .solver.solver import solve

    pr1 = TaskProgramRunner(N, t)
    runid = uuid.uuid4().hex
    for i, a in enumerate(a_s):
        b = Field(random.randint(0, Field.modulus-1))
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b, k, N, t)
        pr1.add(prepareOneInput, k=k, batchid=batchid, runid=runid)
    await pr1.join()
    pr2 = TaskProgramRunner(N, t)
    pr2.add(phase3, k=k, runid=runid)
    powerSums = (await pr2.join())[0]
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
    from .solver.solver import solve
    from honeybadgermpc.ipc import ProcessProgramRunner

    programRunner = ProcessProgramRunner(network_info, N, t, nodeid)
    await programRunner.start()
    sid = 0
    for i in range(k):
        batchid = f"{runid}_{i}"
        programRunner.add(sid, prepareOneInput, k=k, batchid=batchid, runid=runid)
        sid += 1

    await programRunner.join()
    programRunner.add(sid, phase3, k=k, runid=runid)
    powerSums = (await programRunner.join())[0]
    await programRunner.close()
    print(f"Shares from C++ phase opened.")
    result = solve([s.value for s in powerSums])
    print(f"Equation solver completed.")
    print(result)
    return result


if __name__ == "__main__":
    import sys
    from honeybadgermpc.config import load_config
    from honeybadgermpc.ipc import NodeDetails
    from honeybadgermpc.exceptions import ConfigurationError

    configfile = os.environ.get('HBMPC_CONFIG')
    nodeid = os.environ.get('HBMPC_NODE_ID')
    runid = os.environ.get('HBMPC_RUN_ID')

    # override configfile if passed to command
    try:
        nodeid = sys.argv[1]
        configfile = sys.argv[2]
        runid = sys.argv[3]
    except IndexError:
        pass

    if not nodeid:
        raise ConfigurationError('Environment variable `HBMPC_NODE_ID` must be set'
                                 ' or a node id must be given as first argument.')

    if not configfile:
        raise ConfigurationError('Environment variable `HBMPC_CONFIG` must be set'
                                 ' or a config file must be given as second argument.')

    if not runid:
        raise ConfigurationError('Environment variable `HBMPC_RUN_ID` must be set'
                                 ' or a config file must be given as third argument.')

    config_dict = load_config(configfile)
    nodeid = int(nodeid)
    N = config_dict['N']
    t = config_dict['t']
    k = config_dict['k']

    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    def handle_async_exception(loop, ctx):
        print('handle_async_exception:')
        if 'exception' in ctx:
            print('exc:', repr(ctx['exception']))
        else:
            print('ctx:', ctx)
        print('msg:', ctx['message'])

    loop.set_exception_handler(handle_async_exception)
    loop.set_debug(True)
    try:
        if not config_dict['skipPreprocessing']:
            # Need to keep these fixed when running on processes.
            k = config_dict['k']
            assert k < 1000
            a_s = [Field(i) for i in range(1000+k, 1000, -1)]
            b_s = [Field(i) for i in range(10, 10+k)]

            if nodeid == 0:
                os.makedirs("sharedata/", exist_ok=True)
                loop.run_until_complete(
                    runCommandSync(f"rm -f {sharedatadir}/**"))
                for i, a in enumerate(a_s):
                    batchid = f"{runid}_{i}"
                    generate_test_powers(
                        f"{powersPrefix}_{batchid}", a, b_s[i], k, N, t)
                os.mknod(f"{sharedatadir}/READY")
            else:
                loop.run_until_complete(wait_for_preprocessing())

        loop.run_until_complete(
            asynchronusMixingInProcesses(network_info, N, t, k, runid, nodeid)
        )
    finally:
        loop.close()

    # asynchronusMixingInTasks()
