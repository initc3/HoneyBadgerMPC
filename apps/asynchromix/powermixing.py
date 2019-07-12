import asyncio
import uuid
from time import time
from honeybadgermpc.mpc import TaskProgramRunner
from honeybadgermpc.field import GF
from honeybadgermpc.elliptic_curve import Subgroup
from honeybadgermpc.preprocessing import PreProcessedElements
import logging


async def all_secrets_phase1(context, **kwargs):
    k, file_prefixes = kwargs["k"], kwargs["file_prefixes"]
    as_, a_minus_b_shares, all_powers = [], [], []

    stime = time()
    for i in range(k):
        a = context.preproc.get_rand(context)
        powers = context.preproc.get_powers(context, i)
        a_minus_b_shares.append(a - powers[0])
        as_.append(a)
        all_powers.append(powers)
    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": context.myid}
    )
    bench_logger.info(f"[Phase1] Read shares from file: {time() - stime}")

    stime = time()
    opened_shares = await context.ShareArray(a_minus_b_shares).open()
    bench_logger.info(
        f"[Phase1] Open [{len(a_minus_b_shares)}] a-b shares: {time() - stime}"
    )

    stime = time()
    for i in range(k):
        file_name = f"{file_prefixes[i]}-{context.myid}.input"
        file_path = f"{context.preproc.data_directory}{file_name}"
        with open(file_path, "w") as f:
            print(context.field.modulus, file=f)
            print(as_[i].v.value, file=f)
            print(opened_shares[i].value, file=f)
            print(k, file=f)
            for power in all_powers[i]:
                print(power.v.value, file=f)
    bench_logger.info(f"[Phase1] Write shares to file: {time() - stime}")
    return as_


async def phase2(node_id, run_id, file_prefix):
    input_file_name = f"{file_prefix}-{node_id}.input"
    input_file_path = f"{PreProcessedElements.DEFAULT_DIRECTORY}{input_file_name}"
    sum_file_name = f"power-{run_id}_{node_id}.sums"
    sum_file_path = f"{PreProcessedElements.DEFAULT_DIRECTORY}{sum_file_name}"

    # NOTE The binary `compute-power-sums` is generated via the command
    # make -C apps/shuffle/cpp
    # and is stored under /usr/local/bin/
    runcmd = f"compute-power-sums {input_file_path} {sum_file_path}"
    await run_command_sync(runcmd)


async def run_command_sync(command):
    proc = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    logging.debug(f"Command:{command}")
    logging.debug(f"Output: {stdout}")
    if len(stderr):
        logging.info(f"Error: {stderr}")


async def phase3(context, **kwargs):
    k, run_id = kwargs["k"], kwargs["run_id"]
    sum_file_name = f"power-{run_id}_{context.myid}.sums"
    sum_file_path = f"{context.preproc.data_directory}{sum_file_name}"
    sum_shares = []

    bench_logger = logging.LoggerAdapter(
        logging.getLogger("benchmark_logger"), {"node_id": context.myid}
    )

    stime = time()
    with open(sum_file_path, "r") as f:
        assert context.field.modulus == int(f.readline())
        assert k == int(f.readline())
        sum_shares = [context.Share(int(s)) for s in f.read().splitlines()[:k]]
        assert len(sum_shares) == k
    bench_logger.info(f"[Phase3] Read shares from file: {time() - stime}")

    stime = time()
    opened_shares = await context.ShareArray(sum_shares).open()
    bench_logger.info(f"[Phase3] Open [{len(sum_shares)}] shares: {time() - stime}")
    return opened_shares


async def async_mixing(n, t, k):
    from .solver.solver import solve
    from honeybadgermpc.utils.task_pool import TaskPool

    pr1 = TaskProgramRunner(n, t)
    file_prefixes = [uuid.uuid4().hex for _ in range(k)]
    run_id = uuid.uuid4().hex

    pr1.add(all_secrets_phase1, k=k, file_prefixes=file_prefixes)
    rands = await pr1.join()

    pool = TaskPool(256)
    for node_id in range(n):
        for i in range(k):
            pool.submit(phase2(node_id, run_id, file_prefixes[i]))
    await pool.close()

    pr2 = TaskProgramRunner(n, t)
    pr2.add(phase3, k=k, run_id=run_id)
    power_sums = (await pr2.join())[0]
    logging.info("Shares from C++ phase opened.")
    result = solve([s.value for s in power_sums])
    logging.info("Equation solver completed.")
    return result, rands


async def build_newton_solver():
    await run_command_sync(f"python apps/shuffle/solver/solver_build.py")


async def build_powermixing_cpp_code():
    await run_command_sync(f"make -C apps/shuffle/cpp")


async def async_mixing_in_processes(network_info, n, t, k, run_id, node_id):
    from .solver.solver import solve
    from honeybadgermpc.ipc import ProcessProgramRunner
    from honeybadgermpc.utils.task_pool import TaskPool

    file_prefixes = [uuid.uuid4().hex for _ in range(k)]
    async with ProcessProgramRunner(network_info, n, t, node_id) as runner:
        await runner.execute("0", all_secrets_phase1, k=k, file_prefixes=file_prefixes)
        logging.info("Phase 1 completed.")

        pool = TaskPool(256)
        stime = time()
        for i in range(k):
            pool.submit(phase2(node_id, run_id, file_prefixes[i]))
        await pool.close()

        bench_logger = logging.LoggerAdapter(
            logging.getLogger("benchmark_logger"), {"node_id": HbmpcConfig.my_id}
        )

        bench_logger.info(
            f"[Phase2] Execute CPP code for all secrets: {time() - stime}"
        )
        logging.info("Phase 2 completed.")

        power_sums = await runner.execute("1", phase3, k=k, run_id=run_id)

        logging.info("Shares from C++ phase opened.")
        stime = time()
        result = solve([s.value for s in power_sums])
        bench_logger.info(f"[SolverPhase] Run Newton Solver: {time() - stime}")
        logging.info("Equation solver completed.")
        logging.debug(result)
        return result


if __name__ == "__main__":
    from honeybadgermpc.config import HbmpcConfig

    HbmpcConfig.load_config()

    run_id = HbmpcConfig.extras["run_id"]
    k = int(HbmpcConfig.extras["k"])

    pp_elements = PreProcessedElements()
    pp_elements.clear_preprocessing()

    asyncio.set_event_loop(asyncio.new_event_loop())
    loop = asyncio.get_event_loop()

    try:
        if not HbmpcConfig.skip_preprocessing:
            # Need to keep these fixed when running on processes.
            field = GF(Subgroup.BLS12_381)
            a_s = [field(i) for i in range(1000 + k, 1000, -1)]

            if HbmpcConfig.my_id == 0:
                pp_elements.generate_rands(k, HbmpcConfig.N, HbmpcConfig.t)
                pp_elements.generate_powers(k, HbmpcConfig.N, HbmpcConfig.t, k)
                pp_elements.preprocessing_done()
            else:
                loop.run_until_complete(pp_elements.wait_for_preprocessing())

        loop.run_until_complete(
            async_mixing_in_processes(
                HbmpcConfig.peers,
                HbmpcConfig.N,
                HbmpcConfig.t,
                k,
                run_id,
                HbmpcConfig.my_id,
            )
        )
    finally:
        loop.close()
