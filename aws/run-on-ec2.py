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


def get_instance_config(n, t, port, instance_ips, k=-1, delta=-1):
    instance_config = "[general]\n"
    instance_config += f"N: {n}\n"
    instance_config += f"t: {t}\n"
    instance_config += f"k: {k}\n"
    instance_config += f"delta: {delta}\n"
    instance_config += "skipPreprocessing: True\n"
    instance_config += "\n[peers]"
    for i, ip in enumerate(instance_ips):
        instance_config += "\n%d: %s:%d" % (i, ip, port)
    return instance_config


def run_commands_on_instances(
        ec2_manager,
        commands_per_instance_list,
        verbose=True,
        output_file_prefix=None,
        ):

    node_threads = [threading.Thread(
            target=ec2_manager.executeCommandOnInstance,
            args=[id, commands, verbose, output_file_prefix]
        ) for id, commands in commands_per_instance_list]

    for thread in node_threads:
        thread.start()
    for thread in node_threads:
        thread.join()


def get_hbavss_commands(s3manager, instance_ids):
    setup_commands = [[id, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p benchmark",
        ]] for i, id in enumerate(instance_ids)]
    return setup_commands


def get_hbavss_instance_config(instance_ips):
    n, t = AwsConfig.MPC_CONFIG.n, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    return get_instance_config(n, t, port, instance_ips)


def get_hbavss_multi_instance_config(instance_ips):
    n, t = AwsConfig.MPC_CONFIG.n, AwsConfig.MPC_CONFIG.T
    k = AwsConfig.MPC_CONFIG.K
    port = AwsConfig.MPC_CONFIG.PORT
    return get_instance_config(n, t, port, instance_ips, k)


def get_ipc_instance_config(instance_ips):
    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    port = AwsConfig.MPC_CONFIG.PORT
    return get_instance_config(n, t, port, instance_ips)


def get_powermixing_instance_config(max_k, instance_ips):
    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    port = AwsConfig.MPC_CONFIG.PORT
    return get_instance_config(n, t, port, instance_ips, k)


def get_butterfly_network_instance_config(max_k, instance_ips):
    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    port = AwsConfig.MPC_CONFIG.PORT
    delta = AwsConfig.MPC_CONFIG.DELTA
    return get_instance_config(n, t, port, instance_ips, k, delta)


def get_ipc_commands(s3manager, instance_ids):
    from honeybadgermpc.mpc import generate_test_zeros, generate_test_triples

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T

    num_triples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    generate_test_zeros('sharedata/test_zeros', num_triples, n, t)
    generate_test_triples('sharedata/test_triples', num_triples, n, t)
    triple_urls = [s3manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(n)]
    zero_urls = [s3manager.uploadFile(
        "sharedata/test_zeros-%d.share" % (i)) for i in range(n)]
    setup_commands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (triple_urls[i]),
            "cd sharedata; curl -sSO %s" % (zero_urls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instance_ids)]

    return setup_commands


def get_butterfly_network_commands(max_k, s3manager, instance_ids):
    from honeybadgermpc.mpc import (
        generate_test_triples, generate_test_randoms, random_files_prefix)
    from apps.shuffle.butterfly_network import generate_random_shares, oneminusoneprefix
    from math import log

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K

    num_switches = k * int(log(k, 2)) ** 2
    generate_test_triples('sharedata/test_triples', 2 * num_switches, n, t)
    generate_random_shares(oneminusoneprefix, num_switches, n, t)
    generate_test_randoms(random_files_prefix, k, n, t)
    triple_urls = [s3manager.uploadFile(
        "sharedata/test_triples-%d.share" % (i)) for i in range(n)]
    input_urls = [s3manager.uploadFile(
        f"{random_files_prefix}-%d.share" % (i)) for i in range(n)]
    rand_share_urls = [s3manager.uploadFile(
        f"{oneminusoneprefix}-{i}.share") for i in range(n)]
    setup_commands = [[instanceId, [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            "mkdir -p sharedata",
            "cd sharedata; curl -sSO %s" % (triple_urls[i]),
            "cd sharedata; curl -sSO %s" % (rand_share_urls[i]),
            "cd sharedata; curl -sSO %s" % (input_urls[i]),
            "mkdir -p benchmark",
        ]] for i, instanceId in enumerate(instance_ids)]

    return setup_commands


def get_powermixing_setup_commands(max_k, runid, s3manager, instance_ids):
    from apps.shuffle.powermixing import powersPrefix, generate_test_powers
    from honeybadgermpc.mpc import Field

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K
    q = Queue()

    def upload_file(fname):
        url = s3manager.uploadFile(fname)
        q.put(url)

    a_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]
    b_s = [Field(random.randint(0, Field.modulus-1)) for _ in range(k)]

    for i, a in enumerate(a_s):
        batchid = f"{runid}_{i}"
        generate_test_powers(f"{powersPrefix}_{batchid}", a, b_s[i], k, n, t)

    setup_commands = []
    for i, instanceId in enumerate(instance_ids):
        url = s3manager.uploadFile(f"scripts/aws/download_input.sh")
        commands = [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            f"curl -sSO {url}",
            "mkdir -p sharedata",
            "cp download_input.sh sharedata/download_input.sh ",
            "mkdir -p benchmark",
            "ulimit -n 10000",
        ]
        executor = ThreadPoolExecutor(max_workers=200)
        threads = []
        for j in range(k):
            threads.append(executor.submit(
                upload_file,
                f"{powersPrefix}_{runid}_{j}-{i}.share"))
        wait(threads, return_when=ALL_COMPLETED)
        with open('%s-%d-links' % (runid, i), 'w') as f:
            while not q.empty():
                print(q.get(), file=f)
        fname = f"{runid}-{i}-links"
        url = s3manager.uploadFile(fname)
        commands.append(f"cd sharedata; curl -sSO {url}; bash download_input.sh {fname}")
        setup_commands.append([instanceId, commands])

    return setup_commands


def trigger_run(run_id, skip_setup, max_k, only_setup):
    os.makedirs("sharedata/", exist_ok=True)
    print(f">>> Run Id: {run_id} <<<")
    ec2manager, s3manager = EC2Manager(), S3Manager(run_id)
    instance_ids, instance_ips = ec2manager.create_instances()
    port = AwsConfig.MPC_CONFIG.PORT

    if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
        instance_config = get_ipc_instance_config(instance_ips)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
        instance_config = get_powermixing_instance_config(max_k, instance_ips)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
        instance_config = get_butterfly_network_instance_config(max_k, instance_ips)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("secretshare_hbavsslight"):
        instance_config = get_hbavss_instance_config(instance_ips)
    else:
        print("Application not supported to run on AWS.")
        raise SystemError

    print(f">>> Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket. <<<")
    instance_config_url = s3manager.upload_config(instance_config)
    print(">>> Config file upload complete. <<<")

    print(">>> Triggering config update on instances.")
    config_update_commands = [[instanceId, [
            "mkdir -p config",
            "cd config; curl -sSO %s" % (instance_config_url),
        ]] for i, instanceId in enumerate(instance_ids)]
    run_commands_on_instances(ec2manager, config_update_commands, False)
    print(">>> Config update completed successfully")

    if not skip_setup:
        print(">>> Uploading inputs.")
        if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
            setup_commands = get_ipc_commands(s3manager, instance_ids)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
            setup_commands = get_powermixing_setup_commands(
                max_k, run_id, s3manager, instance_ids
            )
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
            setup_commands = get_butterfly_network_commands(
                max_k, s3manager, instance_ids)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("secretshare_hbavsslight"):
            setup_commands = get_hbavss_commands(s3manager, instance_ids)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("hbavss_multi"):
            setup_commands = get_hbavss_commands(s3manager, instance_ids)
        print(">>> Inputs successfully uploaded.")

        print(">>> Triggering setup commands. <<<")
        run_commands_on_instances(ec2manager, setup_commands, False)

    if not only_setup:
        print(">>> Setup commands executed successfully. <<<")
        instance_commands = [[instance_id, [
                f"sudo docker run\
                -p {port}:{port} \
                -v /home/ubuntu/config:/usr/src/HoneyBadgerMPC/config/ \
                -v /home/ubuntu/sharedata:/usr/src/HoneyBadgerMPC/sharedata/ \
                -v /home/ubuntu/benchmark:/usr/src/HoneyBadgerMPC/benchmark/ \
                -e HBMPC_NODE_ID={i} \
                -e HBMPC_CONFIG=config/config.ini \
                -e HBMPC_RUN_ID={run_id} \
                {AwsConfig.DOCKER_IMAGE_PATH} \
                {AwsConfig.MPC_CONFIG.COMMAND}"
            ]] for i, instance_id in enumerate(instance_ids)]
        print(">>> Triggering MPC commands. <<<")
        run_commands_on_instances(ec2manager, instance_commands)
        print(">>> Collecting logs. <<<")
        log_collection_cmds = [[id, ["cat benchmark/*.log"]] for id in instance_ids]
        os.makedirs(run_id, exist_ok=True)
        run_commands_on_instances(
            ec2manager, log_collection_cmds, True, f"{run_id}/benchmark")

    s3manager.cleanup()


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
