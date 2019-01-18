import random
import asyncio
import uuid
import os
import glob
from time import time
from honeybadgermpc.mpc import write_polys, TaskProgramRunner, Field, Poly
import logging


shufflebasedir = "apps/shuffle"
sharedatadir = "sharedata"
powersPrefix = f"{sharedatadir}/powers"
cppPrefix = f"{sharedatadir}/cpp-phase"


async def wait_for_preprocessing():
    while not os.path.exists(f"{sharedatadir}/READY"):
        logging.info(f"waiting for preprocessing {sharedatadir}/READY")
        await asyncio.sleep(1)


def generate_test_powers(prefix, a, b, k, n, t):
    # Generate k powers, store in files of form "prefix-%d.share"
    polys = [Poly.random(t, a)]
    for j in range(1, k+1):
        polys.append(Poly.random(t, pow(b, j)))
    write_polys(prefix, Field.modulus, n, t, polys)


async def single_secret_phase1(context, **kwargs):
    k, powers_prefix = kwargs['k'], kwargs['powers_prefix']
    cpp_prefix = kwargs['cpp_prefix']
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


async def all_secrets_phase1(context, **kwargs):
    k, runid = kwargs['k'], kwargs['runid']
    aS, aMinusBShares, allPowers = [], [], []

    stime = time()
    for i in range(k):
        batchid = f"{runid}_{i}"
        powers_prefix = f"{powersPrefix}_{batchid}"
        filename = f"{powers_prefix}-{context.myid}.share"
        shares = context.read_shares(open(filename))
        aMinusBShares.append(shares[0] - shares[1])
        aS.append(shares[0])
        allPowers.append(shares[1:])
    benchLogger.info(f"[Phase1] Read shares from file: {time() - stime}")

    stime = time()
    openedShares = await context.ShareArray(aMinusBShares).open()
    benchLogger.info(
        f"[Phase1] Open [{len(aMinusBShares)}] a-b shares: {time() - stime}")

    stime = time()
    for i in range(k):
        batchid = f"{runid}_{i}"
        cpp_prefix = f"{cppPrefix}_{batchid}"
        with open(f"{cpp_prefix}-{context.myid}.input", "w") as f:
            print(Field.modulus, file=f)
            print(aS[i].v.value, file=f)
            print(openedShares[i].value, file=f)
            print(k, file=f)
            for power in allPowers[i]:
                print(power.v.value, file=f)
    benchLogger.info(f"[Phase1] Write shares to file: {time() - stime}")


async def phase2(nodeid, batchid, runid, cpp_prefix):
    filename = f"{cpp_prefix}-{nodeid}.input"
    sumFileName = f"{sharedatadir}/power-{runid}_{nodeid}.sums"
    # NOTE The binary `compute-power-sums` is generated via the command
    # make -C apps/shuffle/cpp
    # and is stored under /usr/local/bin/
    runcmd = f"compute-power-sums {filename} {sumFileName}"
    await run_command_sync(runcmd)


async def run_command_sync(command):
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    logging.debug(f"Command:{command}")
    logging.debug(f"Output: {stdout}")
    logging.debug(f"Error: {stderr}")


async def prepare_one_input(context, **kwargs):
    k, batchid, runid = kwargs['k'], kwargs['batchid'], kwargs['runid']
    await single_secret_phase1(
        context,
        k=k,
        powers_prefix=f"{powersPrefix}_{batchid}",
        cpp_prefix=f"{cppPrefix}_{batchid}")
    logging.info(f"[{context.myid}] Input prepared for C++ phase.")
    await phase2(context.myid, batchid, runid, f"{cppPrefix}_{batchid}")
    logging.info(f"[{context.myid}] C++ phase completed.")


async def phase3(context, **kwargs):
    k, runid = kwargs['k'], kwargs['runid']
    sumFileName = f"{sharedatadir}/power-{runid}_{context.myid}.sums"
    sumShares = []

    benchLogger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": context.myid})

    stime = time()
    with open(sumFileName, "r") as f:
        assert Field.modulus == int(f.readline())
        assert k == int(f.readline())
        sumShares = [context.Share(int(s)) for s in f.read().splitlines()[:k]]
        assert len(sumShares) == k
    benchLogger.info(f"[Phase3] Read shares from file: {time() - stime}")

    stime = time()
    openedShares = await context.ShareArray(sumShares).open()
    benchLogger.info(f"[Phase3] Open [{len(sumShares)}] shares: {time() - stime}")
    return openedShares


async def async_mixing(a_s, n, t, k):
    from .solver.solver import solve

    pr1 = TaskProgramRunner(n, t)
    runid = uuid.uuid4().hex
    for i, a in enumerate(a_s):
        b = Field(random.randint(0, Field.modulus-1))
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b, k, n, t)
        pr1.add(prepare_one_input, k=k, batchid=batchid, runid=runid)
    await pr1.join()
    pr2 = TaskProgramRunner(n, t)
    pr2.add(phase3, k=k, runid=runid)
    powerSums = (await pr2.join())[0]
    logging.info("Shares from C++ phase opened.")
    result = solve([s.value for s in powerSums])
    logging.info("Equation solver completed.")
    return result


async def build_newton_solver():
    await run_command_sync(f"python {shufflebasedir}/solver/solver_build.py")


async def build_powermixing_cpp_code():
    await run_command_sync(f"make -C {shufflebasedir}/cpp")


def async_mixing_in_tasks():
    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    n, t, k = 3, 1, 2
    a_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    try:
        loop.run_until_complete(build_newton_solver())
        logging.info("Solver built.")
        loop.run_until_complete(build_powermixing_cpp_code())
        logging.info("C++ code built.")
        loop.run_until_complete(async_mixing(a_s, n, t, k))
    finally:
        loop.close()


async def async_mixing_in_processes(network_info, n, t, k, runid, nodeid):
    from .solver.solver import solve
    from honeybadgermpc.ipc import ProcessProgramRunner
    from honeybadgermpc.task_pool import TaskPool

    programRunner = ProcessProgramRunner(network_info, n, t, nodeid)
    await programRunner.start()
    programRunner.add(0, all_secrets_phase1, k=k, runid=runid)
    await programRunner.join()

    pool = TaskPool(256)
    stime = time()
    for i in range(k):
        batchid = f"{runid}_{i}"
        pool.submit(phase2(nodeid, batchid, runid, f"{cppPrefix}_{batchid}"))
    await pool.close()
    benchLogger.info(f"[Phase2] Execute CPP code for all secrets: {time() - stime}")

    programRunner.add(1, phase3, k=k, runid=runid)
    powerSums = (await programRunner.join())[0]
    await programRunner.close()

    logging.info("Shares from C++ phase opened.")
    stime = time()
    result = solve([s.value for s in powerSums])
    benchLogger.info(f"[SolverPhase] Run Newton Solver: {time() - stime}")
    logging.info("Equation solver completed.")
    logging.debug(result)
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

    benchLogger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": nodeid})

    network_info = {
        int(peerid): NodeDetails(addrinfo.split(':')[0], int(addrinfo.split(':')[1]))
        for peerid, addrinfo in config_dict['peers'].items()
    }

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    def handle_async_exception(loop, ctx):
        logging.info('handle_async_exception:')
        if 'exception' in ctx:
            logging.info(f"exc: {repr(ctx['exception'])}")
        else:
            logging.info(f'ctx: {ctx}')
        logging.info(f"msg: {ctx['message']}")

    loop.set_exception_handler(handle_async_exception)
    loop.set_debug(True)

    # Cleanup pre existing sums file
    sums_file = glob.glob(f'{sharedatadir}/*.sums')
    for f in sums_file:
        os.remove(f)

    try:
        if not config_dict['skipPreprocessing']:
            # Need to keep these fixed when running on processes.
            k = config_dict['k']
            assert k < 1000
            a_s = [Field(i) for i in range(1000+k, 1000, -1)]
            b_s = [Field(i) for i in range(10, 10+k)]

            if nodeid == 0:
                os.makedirs("sharedata/", exist_ok=True)
                for i, a in enumerate(a_s):
                    batchid = f"{runid}_{i}"
                    generate_test_powers(
                        f"{powersPrefix}_{batchid}", a, b_s[i], k, N, t)
                os.mknod(f"{sharedatadir}/READY")
            else:
                loop.run_until_complete(wait_for_preprocessing())

        loop.run_until_complete(
            async_mixing_in_processes(network_info, N, t, k, runid, nodeid)
        )
    finally:
        loop.close()

    # asynchronusMixingInTasks()
