import threading
import uuid
import os
from aws.ec2Manager import EC2Manager
from aws.AWSConfig import AwsConfig
from aws.s3Manager import S3Manager


def getInstanceConfig(N, t, port, instanceIps):
    instanceConfig = "[general]\n"
    instanceConfig += "N: %d\n" % (N)
    instanceConfig += "t: %d\n" % (t)
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


if __name__ == "__main__":
    from honeybadgermpc.passive import generate_test_triples, generate_test_zeros

    runId = uuid.uuid4().hex
    print(f">>> Run Id: {runId} <<<")
    ec2Manager, s3Manager = EC2Manager(), S3Manager(runId)
    instanceIds, instanceIps = ec2Manager.createInstances()
    N, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    numTriples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_zeros('sharedata/test_zeros', numTriples, N, t)
    generate_test_triples('sharedata/test_triples', numTriples, N, t)
    tripleUrls = [s3Manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(N)]
    zeroUrls = [s3Manager.uploadFile(
        "sharedata/test_zeros-%d.share" % (i)) for i in range(N)]

    instanceConfig = getInstanceConfig(N, t, port, instanceIps)
    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instanceConfigUrl = s3Manager.uploadConfig(instanceConfig)
    print(">>> Config file upload complete. <<<")
    setupCommands = [[id, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instanceConfigUrl),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (tripleUrls[i]),
            "cd sharedata; curl -sSO %s" % (zeroUrls[i]),
            "mkdir -p benchmark",
        ]] for i, id in enumerate(instanceIds)]
    print(">>> Triggering setup commands. <<<")
    runCommandsOnInstances(ec2Manager, setupCommands, False)
    print(">>> Setup commands executed successfully. <<<")
    instanceCommands = [[id, [
            "sudo docker run\
            -p %d:%d \
            -v /home/ubuntu/config:/usr/src/HoneyBadgerMPC/config/ \
            -v /home/ubuntu/sharedata:/usr/src/HoneyBadgerMPC/sharedata/ \
            -v /home/ubuntu/benchmark:/usr/src/HoneyBadgerMPC/benchmark/ \
            -e HBMPC_NODE_ID=%d \
            -e HBMPC_CONFIG=config/config.ini \
            %s \
            %s" % (
                port,
                port,
                i,
                AwsConfig.DOCKER_IMAGE_PATH,
                AwsConfig.MPC_CONFIG.COMMAND,
            ),
        ]] for i, id in enumerate(instanceIds)]
    print(">>> Triggering MPC commands. <<<")
    runCommandsOnInstances(ec2Manager, instanceCommands)
    print(">>> Collecting logs. <<<")
    logCollectionCommands = [[id, ["cat benchmark/*.log"]] for id in instanceIds]
    os.makedirs(runId, exist_ok=True)
    runCommandsOnInstances(ec2Manager, logCollectionCommands, True, f"{runId}/benchmark")
    s3Manager.cleanup()
