import threading
import uuid
import os
import argparse
import random
from queue import Queue
from aws.ec2Manager import EC2Manager
from aws.AWSConfig import AwsConfig
from aws.s3Manager import S3Manager
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

def getInstanceConfig(N, t, port, instanceIps, k=-1, delta=-1):
    instanceConfig = "[general]\n"
    instanceConfig += f"N: {N}\n"
    instanceConfig += f"t: {t}\n"
    instanceConfig += f"k: {k}\n"
    instanceConfig += f"delta: {delta}\n"
    instanceConfig += "skipPreprocessing: True\n"
    instanceConfig += "\n[peers]"
    for i, ip in enumerate(instanceIps):
        instanceConfig += "\n%d: %s:%d" % (i, ip, port)
    return instanceConfig


def runCommandsOnInstances(
        ec2Manager,
        commandsPerInstanceList,
        verbose=True,
        outputFilePrefix=None,
        ):

    nodeThreads = [threading.Thread(
            target=ec2Manager.executeCommandOnInstance,
            args=[id, commands, verbose, outputFilePrefix]
        ) for id, commands in commandsPerInstanceList]

    for thread in nodeThreads:
        thread.start()
    for thread in nodeThreads:
        thread.join()


def getHbAVSSCommands(s3Manager, instanceIds):
    setupCommands = [[id, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p benchmark",
        ]] for i, id in enumerate(instanceIds)]
    return setupCommands


def getHbAVSSInstanceConfig(instanceIps):
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    return getInstanceConfig(N, t, port, instanceIps)


def getIpcInstanceConfig(instanceIps):
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    return getInstanceConfig(N, t, port, instanceIps)


def getPowermixingInstanceConfig(max_k, instanceIps):
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    port = AwsConfig.MPC_CONFIG.PORT
    return getInstanceConfig(N, t, port, instanceIps, k)


def getButterflyNetworkInstanceConfig(max_k, instanceIps):
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    port = AwsConfig.MPC_CONFIG.PORT
    delta = AwsConfig.MPC_CONFIG.DELTA
    return getInstanceConfig(N, t, port, instanceIps, k, delta)


def getIpcCommands(s3Manager, instanceIds):
    from honeybadgermpc.mpc import generate_test_zeros, generate_test_triples

    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T

    numTriples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_zeros('sharedata/test_zeros', numTriples, N, t)
    generate_test_triples('sharedata/test_triples', numTriples, N, t)
    tripleUrls = [s3Manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(N)]
    zeroUrls = [s3Manager.uploadFile(
        "sharedata/test_zeros-%d.share" % (i)) for i in range(N)]
    setupCommands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (tripleUrls[i]),
            "cd sharedata; curl -sSO %s" % (zeroUrls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instanceIds)]

    return setupCommands


def getButterflyNetworkCommands(max_k, s3Manager, instanceIds):
    from honeybadgermpc.mpc import generate_test_triples
    from apps.shuffle.butterfly_network import generate_random_shares, oneminusoneprefix
    from math import log

    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K

    numTriples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_triples('sharedata/test_triples', numTriples, N, t)
    generate_random_shares(oneminusoneprefix, k * int(log(k, 2)), N, t)
    tripleUrls = [s3Manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(N)]
    randShareUrls = [s3Manager.uploadFile(
        f"{oneminusoneprefix}-{i}.share") for i in range(N)]
    setupCommands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (tripleUrls[i]),
            "cd sharedata; curl -sSO %s" % (randShareUrls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instanceIds)]

    return setupCommands


def getPowermixingSetupCommands(max_k, runid, s3Manager, instanceIds):
    from apps.shuffle.powermixing import powersPrefix, generate_test_powers
    from honeybadgermpc.mpc import Field

    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    q = Queue()

    def uploadFile(fname):
        url = s3Manager.uploadFile(fname)
        q.put(url)

    a_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    b_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]

    for i, a in enumerate(a_s):
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b_s[i], k, N, t)

    setupCommands = []
    for i, instanceId in enumerate(instanceIds):
        commands = [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p sharedata",
            "git clone https://github.com/lu562/upload-script.git",
            "cp upload-script/Download_input.sh sharedata/Download_input.sh ",
            "mkdir -p benchmark",
            "ulimit -n 10000",
        ]
        executor = ThreadPoolExecutor(max_workers=100)
        threads = []
        for j in range(k):
            threads.append(executor.submit(uploadFile, f"{powersPrefix}_{runid}_{j}-{i}.share"))
        wait(threads, return_when=ALL_COMPLETED)       
        
        with open('%s-%d-links' % (runid, i), 'w') as f:
            while not q.empty():
                print(q.get(), file=f)
        fname = f"{runid}-{i}-links"
        url = s3Manager.uploadFile(fname)
        commands.append(f"cd sharedata; curl -sSO {url}; sh Download_input.sh {fname}")
        setupCommands.append([instanceId, commands])

    return setupCommands


def trigger_run(runId, skip_setup, max_k, only_setup):
    os.makedirs("sharedata/", exist_ok=True)
    print(f">>> Run Id: {runId} <<<")
    ec2Manager, s3Manager = EC2Manager(), S3Manager(runId)
    instanceIds, instanceIps = ec2Manager.createInstances()
    port = AwsConfig.MPC_CONFIG.PORT

    if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
        instanceConfig = getIpcInstanceConfig(instanceIps)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
        instanceConfig = getPowermixingInstanceConfig(max_k, instanceIps)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
        instanceConfig = getButterflyNetworkInstanceConfig(max_k, instanceIps)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("secretshare_hbavsslight"):
        instanceConfig = getHbAVSSInstanceConfig(instanceIps)
    else:
        print("Application not supported to run on AWS.")
        raise SystemError

    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")

    print(">>> Triggering config update on instances.")
    configUpdateCommands = [[instanceId, [
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
        ]] for i, instanceId in enumerate(instanceIds)]
    runCommandsOnInstances(ec2Manager, configUpdateCommands, False)
    print(">>> Config update completed successfully")

    if not skip_setup:
        print(">>> Uploading inputs.")
        if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
            setupCommands = getIpcCommands(s3Manager, instanceIds)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
            setupCommands = getPowermixingSetupCommands(
                max_k, runId, s3Manager, instanceIds
            )
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
            setupCommands = getButterflyNetworkCommands(max_k, s3Manager, instanceIds)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("secretshare_hbavsslight"):
            setupCommands = getHbAVSSCommands(s3Manager, instanceIds)
        print(">>> Inputs successfully uploaded.")

        print(">>> Triggering setup commands. <<<")
        runCommandsOnInstances(ec2Manager, setupCommands, False)

    if not only_setup:
        print(">>> Setup commands executed successfully. <<<")
        instanceCommands = [[instanceId, [
                f"sudo docker run\
                -p {port}:{port} \
                -v /home/ubuntu/config:/usr/src/HoneyBadgerMPC/config/ \
                -v /home/ubuntu/sharedata:/usr/src/HoneyBadgerMPC/sharedata/ \
                -v /home/ubuntu/benchmark:/usr/src/HoneyBadgerMPC/benchmark/ \
                -e HBMPC_NODE_ID={i} \
                -e HBMPC_CONFIG=config/config.ini \
                -e HBMPC_RUN_ID={runId} \
                {AwsConfig.DOCKER_IMAGE_PATH} \
                {AwsConfig.MPC_CONFIG.COMMAND}"
            ]] for i, instanceId in enumerate(instanceIds)]
        print(">>> Triggering MPC commands. <<<")
        runCommandsOnInstances(ec2Manager, instanceCommands)
        print(">>> Collecting logs. <<<")
        logCollectionCommands = [[id, ["cat benchmark/*.log"]] for id in instanceIds]
        os.makedirs(runId, exist_ok=True)
        runCommandsOnInstances(
            ec2Manager, logCollectionCommands, True, f"{runId}/benchmark")

    s3Manager.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Runs HBMPC code on AWS.')
    parser.add_argument(
        '-s',
        '--skip-setup',
        dest='skip_setup',
        action="store_true",
        help='If this is passed, then the setup commands are skipped.')
    parser.add_argument(
        '-k',
        '--max-k',
        default=AwsConfig.MPC_CONFIG.K,
        type=int,
        dest='max_k',
        help='Maximum value of k for which the inputs need to be \
        created and uploaded during the setup phase. This value is \
        ignored if --skip-setup is passed. (default: `k` in aws_config.json)')
    parser.add_argument(
        '--only-setup',
        dest='only_setup',
        action='store_true',
        help='If this value is passed, then only the setup phase is run,\
         otherwise both phases are run.')
    parser.add_argument(
        '--run-id',
        dest='run_id',
        nargs='?',
        help='If skip setup is passed, then a previous run_id for the same\
        MPC application needs to be specified to pickup the correct input files.'
    )
    args = parser.parse_args()
    if args.skip_setup and args.only_setup:
        parser.error("--only-setup and --skip-setup are mutually exclusive.")
    if args.skip_setup and not args.run_id:
        parser.error("--run-id needs to be passed with --skip-setup.")
    args.run_id = uuid.uuid4().hex if args.run_id is None else args.run_id
    trigger_run(args.run_id, args.skip_setup, args.max_k, args.only_setup)
