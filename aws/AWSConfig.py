import json
import os
import sys


class RegionConfig(object):
    def __init__(self, vmCount, sgIds, imageId, keyName, keyFilePath):
        self.VM_COUNT = vmCount
        self.SECURITY_GROUP_IDS = sgIds
        self.IMAGE_ID = imageId
        self.KEY_FILE_PATH = keyFilePath
        self.KEY_NAME = keyName


class MPCConfig(object):
    def __init__(self, command, t, k, delta, port, numTriples, n):
        self.COMMAND = command
        self.T = t
        self.PORT = port
        self.NUM_TRIPLES = numTriples
        self.K = k
        self.DELTA = delta
        self.n = n


def read_environment_variable(key):
    try:
        value = os.environ[key]
    except KeyError:
        print(f">>> {key} environment variable not set.")
        sys.exit(1)
    return value


class AwsConfig:
    config = json.load(open('./aws/aws-config.json'))

    mpcConfig = config["mpc"]
    MPC_CONFIG = MPCConfig(
        mpcConfig["command"],
        mpcConfig["t"],
        mpcConfig["k"],
        mpcConfig["delta"],
        mpcConfig["port"],
        mpcConfig["num_triples"],
        mpcConfig["n"]
    )

    awsconfig = config["aws"]
    ACCESS_KEY_ID = read_environment_variable("ACCESS_KEY_ID")
    SECRET_ACCESS_KEY = read_environment_variable("SECRET_ACCESS_KEY")
    SETUP_FILE_PATH = awsconfig["setup_file_path"]

    REGION = {}
    TOTAL_VM_COUNT = 0
    for region, value in awsconfig["region"].items():
        REGION[region] = RegionConfig(
            value["vm_count"],
            value["security_group_ids"],
            value["image_id"],
            value["key_name"],
            value["key_file_path"]
        )
        TOTAL_VM_COUNT += value["vm_count"]
    VM_NAME = awsconfig["vm_name"]
    INSTANCE_TYPE = awsconfig["instance_type"]
    INSTANCE_USER_NAME = awsconfig["instance_user_name"]
    BUCKET_NAME = awsconfig["bucket_name"]

    DOCKER_IMAGE_PATH = config["docker"]["image_path"]
