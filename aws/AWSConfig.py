import json
import os
import sys


class RegionConfig(object):
    def __init__(self, vm_count, sg_ids, image_id, key_name, key_file_path):
        self.VM_COUNT = vm_count
        self.SECURITY_GROUP_IDS = sg_ids
        self.IMAGE_ID = image_id
        self.KEY_FILE_PATH = key_file_path
        self.KEY_NAME = key_name


class MPCConfig(object):
    def __init__(self, command, t, k, port, num_triples, n, num_faulty_nodes):
        self.COMMAND = command
        self.T = t
        self.PORT = port
        self.NUM_TRIPLES = num_triples
        self.K = k
        self.N = n
        self.NUM_FAULTY_NODES = num_faulty_nodes


def read_environment_variable(key):
    try:
        value = os.environ[key]
    except KeyError:
        print(f">>> {key} environment variable not set.")
        sys.exit(1)
    return value


class AwsConfig:
    config = json.load(open("./aws/aws-config.json"))

    mpc_config = config["mpc"]

    assert (
        mpc_config["num_faulty_nodes"] <= mpc_config["t"]
    ), "`num_faulty_nodes` \
        cannot be greater than `t`"

    MPC_CONFIG = MPCConfig(
        mpc_config["command"],
        mpc_config["t"],
        mpc_config["k"],
        mpc_config["port"],
        mpc_config["num_triples"],
        mpc_config["n"],
        mpc_config["num_faulty_nodes"],
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
            value["key_file_path"],
        )
        TOTAL_VM_COUNT += value["vm_count"]
    VM_NAME = awsconfig["vm_name"]
    INSTANCE_TYPE = awsconfig["instance_type"]
    INSTANCE_USER_NAME = awsconfig["instance_user_name"]
    BUCKET_NAME = awsconfig["bucket_name"]

    DOCKER_IMAGE_PATH = config["docker"]["image_path"]
