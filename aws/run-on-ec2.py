import threading
import uuid
import os
from aws.ec2Manager import EC2Manager
from aws.AWSConfig import AwsConfig
from aws.s3Manager import S3Manager


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


def getHbAVSSCommands(s3Manager, instanceIps, instanceIds):
    N, t = AwsConfig.MPC_CONFIG.n, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    instanceConfig = getInstanceConfig(N, t, port, instanceIps)
    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}'<<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")
    setupCommands = [[id, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
            "mkdir -p benchmark",
        ]] for i, id in enumerate(instanceIds)]
    return AwsConfig.MPC_CONFIG.COMMAND, setupCommands


def getIpcCommands(s3Manager, instanceIps, instanceIds):
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT

    instanceConfig = getInstanceConfig(N, t, port, instanceIps)
    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")

    numTriples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_zeros('sharedata/test_zeros', numTriples, N, t)
    generate_test_triples('sharedata/test_triples', numTriples, N, t)
    tripleUrls = [s3Manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(N)]
    zeroUrls = [s3Manager.uploadFile(
        "sharedata/test_zeros-%d.share" % (i)) for i in range(N)]
    setupCommands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (tripleUrls[i]),
            "cd sharedata; curl -sSO %s" % (zeroUrls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instanceIds)]

    return AwsConfig.MPC_CONFIG.COMMAND, setupCommands


def getButterflyNetworkCommands(s3Manager, instanceIps, instanceIds):
    from apps.shuffle.butterfly_network import generate_random_shares, oneminusoneprefix
    from math import log

    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port, k = AwsConfig.MPC_CONFIG.PORT, AwsConfig.MPC_CONFIG.K
    delta = AwsConfig.MPC_CONFIG.DELTA

    instanceConfig = getInstanceConfig(N, t, port, instanceIps, k, delta)
    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")

    numTriples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_triples('sharedata/test_triples', numTriples, N, t)
    generate_random_shares(oneminusoneprefix, k * int(log(k, 2)), N, t)
    tripleUrls = [s3Manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(N)]
    randShareUrls = [s3Manager.uploadFile(
        f"{oneminusoneprefix}-{i}.share") for i in range(N)]
    setupCommands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (tripleUrls[i]),
            "cd sharedata; curl -sSO %s" % (randShareUrls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instanceIds)]

    return AwsConfig.MPC_CONFIG.COMMAND, setupCommands


def getPowermixingCommands(runid, s3Manager, instanceIds, instanceIps):
    from apps.shuffle.powermixing import powersPrefix, generate_test_powers
    from honeybadgermpc.mpc import Field

    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port, k = AwsConfig.MPC_CONFIG.PORT, AwsConfig.MPC_CONFIG.K

    instanceConfig = getInstanceConfig(N, t, port, instanceIps, k)
    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")

    a_s = [Field(i) for i in range(100+k, 100, -1)]
    b_s = [Field(i) for i in range(10, 10+k)]

    for i, a in enumerate(a_s):
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b_s[i], k, N, t)

    setupCommands = []
    for i, instanceId in enumerate(instanceIds):
        commands = [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
            "mkdir -p sharedata",
            "mkdir -p benchmark",
        ]
        for j in range(k):
            fname = f"{powersPrefix}_{runid}_{j}-{i}.share"
            url = s3Manager.uploadFile(fname)
            commands.append(f"cd sharedata; curl -sSO {url}")
        setupCommands.append([instanceId, commands])
    mpcCommand = f"{AwsConfig.MPC_CONFIG.COMMAND}"
    return mpcCommand, setupCommands


if __name__ == "__main__":
    from honeybadgermpc.mpc import generate_test_triples, generate_test_zeros

    os.makedirs("sharedata/", exist_ok=True)
    runId = uuid.uuid4().hex
    print(f">>> Run Id: {runId} <<<")
    ec2Manager, s3Manager = EC2Manager(), S3Manager(runId)
    instanceIds, instanceIps = ec2Manager.createInstances()
    port = AwsConfig.MPC_CONFIG.PORT

    if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
        mpcCommand, setupCommands = getIpcCommands(s3Manager, instanceIps, instanceIds)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
        mpcCommand, setupCommands = getPowermixingCommands(
            runId, s3Manager, instanceIds, instanceIps
        )
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
        mpcCommand, setupCommands = getButterflyNetworkCommands(
            s3Manager, instanceIps, instanceIds
        )
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("secretshare_hbavsslight"):
        mpcCommand, setupCommands = getHbAVSSCommands(
            s3Manager, instanceIps, instanceIds
        )
    else:
        print("Application not supported to run on AWS.")
        raise SystemExit

    print(">>> Triggering setup commands. <<<")
    runCommandsOnInstances(ec2Manager, setupCommands, False)

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
            {mpcCommand}"
        ]] for i, instanceId in enumerate(instanceIds)]
    print(">>> Triggering MPC commands. <<<")
    runCommandsOnInstances(ec2Manager, instanceCommands)
    print(">>> Collecting logs. <<<")
    logCollectionCommands = [[id, ["cat benchmark/*.log"]] for id in instanceIds]
    os.makedirs(runId, exist_ok=True)
    runCommandsOnInstances(ec2Manager, logCollectionCommands, True, f"{runId}/benchmark")
    s3Manager.cleanup()
