import threading
import uuid
import os
import argparse
import json
import logging
from time import time
from math import log

from aws.ec2Manager import EC2Manager
from aws.AWSConfig import AwsConfig
from aws.s3Manager import S3Manager


def get_instance_configs(instance_ips, extra={}):
    port = AwsConfig.MPC_CONFIG.PORT
    num_faulty_nodes = AwsConfig.MPC_CONFIG.NUM_FAULTY_NODES
    instance_configs = [None] * len(instance_ips)

    for my_id in range(len(instance_ips)):
        config = {
            "N": AwsConfig.MPC_CONFIG.N,
            "t": AwsConfig.MPC_CONFIG.T,
            "my_id": my_id,
            "peers": [f"{ip}:{port}" for ip in instance_ips],
            "reconstruction": {"induce_faults": False},
            "skip_preprocessing": True,
            "extra": extra,
        }

        if num_faulty_nodes > 0:
            num_faulty_nodes -= 1
            config["reconstruction"]["induce_faults"] = True
        instance_configs[my_id] = (my_id, json.dumps(config))

    return instance_configs


def run_commands_on_instances(
    ec2manager, commands_per_instance_list, verbose=True, output_file_prefix=None
):

    node_threads = [
        threading.Thread(
            target=ec2manager.execute_command_on_instance,
            args=[id, commands, verbose, output_file_prefix],
        )
        for id, commands in commands_per_instance_list
    ]

    for thread in node_threads:
        thread.start()
    for thread in node_threads:
        thread.join()


def get_ipc_setup_commands(s3manager, instance_ids):
    from honeybadgermpc.preprocessing import PreProcessedElements
    from honeybadgermpc.preprocessing import PreProcessingConstants as Constants

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T

    num_triples = AwsConfig.MPC_CONFIG.NUM_TRIPLES
    pp_elements = PreProcessedElements()

    pp_elements.generate_zeros(num_triples, n, t)
    pp_elements.generate_triples(num_triples, n, t)

    triple_urls = s3manager.upload_files(
        [
            pp_elements.mixins[Constants.TRIPLES]._build_file_name(n, t, i)
            for i in range(n)
        ]
    )
    zero_urls = s3manager.upload_files(
        [
            pp_elements.mixins[Constants.ZEROS]._build_file_name(n, t, i)
            for i in range(n)
        ]
    )

    setup_commands = [
        [
            instance_id,
            [
                "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
                "mkdir -p sharedata",
                "cd sharedata; curl -sSO %s" % (triple_urls[i]),
                "cd sharedata; curl -sSO %s" % (zero_urls[i]),
                "mkdir -p benchmark-logs",
            ],
        ]
        for i, instance_id in enumerate(instance_ids)
    ]

    return setup_commands


def get_hbavss_setup_commands(s3manager, instance_ids):
    setup_commands = [
        [
            instance_id,
            [
                "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
                "mkdir -p benchmark-logs",
            ],
        ]
        for i, instance_id in enumerate(instance_ids)
    ]

    return setup_commands


def get_butterfly_network_setup_commands(max_k, s3manager, instance_ids):
    from honeybadgermpc.preprocessing import PreProcessedElements
    from honeybadgermpc.preprocessing import PreProcessingConstants as Constants

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K

    logging.info("Starting to create preprocessing files.")
    stime = time()
    num_switches = k * int(log(k, 2)) ** 2
    pp_elements = PreProcessedElements()
    pp_elements.generate_triples(2 * num_switches, n, t)
    pp_elements.generate_one_minus_ones(num_switches, n, t)
    pp_elements.generate_rands(k, n, t)
    logging.info(f"Preprocessing files created in {time()-stime}")

    logging.info("Uploading inputs to AWS S3.")
    stime = time()
    triple_urls = s3manager.upload_files(
        [
            pp_elements.mixins[Constants.TRIPLES]._build_file_name(n, t, i)
            for i in range(n)
        ]
    )
    input_urls = s3manager.upload_files(
        [
            pp_elements.mixins[Constants.RANDS]._build_file_name(n, t, i)
            for i in range(n)
        ]
    )
    rand_share_urls = s3manager.upload_files(
        [
            pp_elements.mixins[Constants.ONE_MINUS_ONE]._build_file_name(n, t, i)
            for i in range(n)
        ]
    )
    logging.info(f"Inputs successfully uploaded in {time()-stime} seconds.")

    setup_commands = [
        [
            instance_id,
            [
                "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
                "mkdir -p sharedata",
                "cd sharedata; curl -sSO %s" % (triple_urls[i]),
                "cd sharedata; curl -sSO %s" % (rand_share_urls[i]),
                "cd sharedata; curl -sSO %s" % (input_urls[i]),
                "mkdir -p benchmark-logs",
            ],
        ]
        for i, instance_id in enumerate(instance_ids)
    ]

    return setup_commands


def get_powermixing_setup_commands(max_k, runid, s3manager, instance_ids):
    from honeybadgermpc.preprocessing import PreProcessedElements
    from honeybadgermpc.preprocessing import PreProcessingConstants as Constants

    n, t = AwsConfig.TOTAL_VM_COUNT, AwsConfig.MPC_CONFIG.T
    k = max_k if max_k else AwsConfig.MPC_CONFIG.K

    logging.info("Starting to create preprocessing files.")
    stime = time()
    pp_elements = PreProcessedElements()
    pp_elements.generate_powers(k, n, t, k)
    pp_elements.generate_rands(k, n, t)
    logging.info(f"Preprocessing files created in {time()-stime}")

    setup_commands = []
    total_time = 0
    logging.info(f"Uploading input files to AWS S3.")

    for i, instance_id in enumerate(instance_ids):
        url = s3manager.upload_file(f"aws/download_input.sh")
        commands = [
            "sudo docker pull %s" % (AwsConfig.DOCKER_IMAGE_PATH),
            f"curl -sSO {url}",
            "mkdir -p sharedata",
            "cp download_input.sh sharedata/download_input.sh ",
            "mkdir -p benchmark-logs",
            "ulimit -n 10000",
        ]
        file_names = []
        for j in range(k):
            prefix1 = f"{pp_elements.mixins[Constants.POWERS].file_prefix}_{j}"
            file_names.append(
                pp_elements.mixins[Constants.POWERS].build_filename(
                    n, t, i, prefix=prefix1
                )
            )

            file_names.append(
                pp_elements.mixins[Constants.RANDS].build_filename(n, t, i)
            )

        stime = time()
        urls = s3manager.upload_files(file_names)
        total_time += time() - stime
        with open("%s-%d-links" % (runid, i), "w") as f:
            for url in urls:
                print(url, file=f)
        fname = f"{runid}-{i}-links"
        url = s3manager.upload_file(fname)
        commands.append(
            f"cd sharedata; curl -sSO {url}; bash download_input.sh {fname}"
        )
        setup_commands.append([instance_id, commands])

    logging.info(f"Upload completed in {total_time} seconds.")

    return setup_commands


def trigger_run(run_id, skip_setup, max_k, only_setup, cleanup):
    os.makedirs("sharedata/", exist_ok=True)
    logging.info(f"Run Id: {run_id}")
    ec2manager, s3manager = EC2Manager(), S3Manager(run_id)
    instance_ids, instance_ips = ec2manager.create_instances()

    if cleanup:
        instance_commands = [
            [instance_id, ["sudo docker kill $(sudo docker ps -q); rm -rf *"]]
            for i, instance_id in enumerate(instance_ids)
        ]
        run_commands_on_instances(ec2manager, instance_commands)
        return

    port = AwsConfig.MPC_CONFIG.PORT

    if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
        instance_configs = get_instance_configs(instance_ips)
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
        instance_configs = get_instance_configs(
            instance_ips, {"k": AwsConfig.MPC_CONFIG.K, "run_id": run_id}
        )
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
        instance_configs = get_instance_configs(
            instance_ips, {"k": AwsConfig.MPC_CONFIG.K, "run_id": run_id}
        )
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("hbavss_batch"):
        instance_configs = get_instance_configs(
            instance_ips, {"k": AwsConfig.MPC_CONFIG.K, "run_id": run_id}
        )
    elif AwsConfig.MPC_CONFIG.COMMAND.endswith("hbavss_light"):
        instance_configs = get_instance_configs(
            instance_ips, {"k": AwsConfig.MPC_CONFIG.K, "run_id": run_id}
        )
    else:
        logging.error("Application not supported to run on AWS.")
        raise SystemError

    logging.info(f"Uploading config file to S3 in '{AwsConfig.BUCKET_NAME}' bucket.")

    config_urls = s3manager.upload_configs(instance_configs)
    logging.info("Config file upload complete.")

    logging.info("Triggering config update on instances.")
    config_update_commands = [
        [instance_id, ["mkdir -p config", "cd config; curl -sSO %s" % (config_url)]]
        for config_url, instance_id in zip(config_urls, instance_ids)
    ]
    run_commands_on_instances(ec2manager, config_update_commands, False)
    logging.info("Config update completed successfully.")

    if not skip_setup:
        if AwsConfig.MPC_CONFIG.COMMAND.endswith("ipc"):
            setup_commands = get_ipc_setup_commands(s3manager, instance_ids)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("powermixing"):
            setup_commands = get_powermixing_setup_commands(
                max_k, run_id, s3manager, instance_ids
            )
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("butterfly_network"):
            setup_commands = get_butterfly_network_setup_commands(
                max_k, s3manager, instance_ids
            )
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("hbavss_batch"):
            setup_commands = get_hbavss_setup_commands(s3manager, instance_ids)
        elif AwsConfig.MPC_CONFIG.COMMAND.endswith("hbavss_light"):
            setup_commands = get_hbavss_setup_commands(s3manager, instance_ids)
        logging.info("Triggering setup commands.")
        run_commands_on_instances(ec2manager, setup_commands, False)

    if not only_setup:
        logging.info("Setup commands executed successfully.")
        instance_commands = [
            [
                instance_id,
                [
                    f"sudo docker run\
                -p {port}:{port} \
                -v /home/ubuntu/config:/usr/src/HoneyBadgerMPC/config/ \
                -v /home/ubuntu/sharedata:/usr/src/HoneyBadgerMPC/sharedata/ \
                -v /home/ubuntu/benchmark-logs:/usr/src/HoneyBadgerMPC/benchmark-logs/ \
                {AwsConfig.DOCKER_IMAGE_PATH} \
                {AwsConfig.MPC_CONFIG.COMMAND} -d -f config/config-{i}.json"
                ],
            ]
            for i, instance_id in enumerate(instance_ids)
        ]
        logging.info("Triggering MPC commands.")
        run_commands_on_instances(ec2manager, instance_commands)
        logging.info("Collecting logs.")
        log_collection_cmds = [
            [id, ["cat benchmark-logs/*.log"]] for id in instance_ids
        ]
        os.makedirs(run_id, exist_ok=True)
        run_commands_on_instances(
            ec2manager, log_collection_cmds, True, f"{run_id}/benchmark-logs"
        )

    s3manager.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runs HBMPC code on AWS.")
    parser.add_argument(
        "-s",
        "--skip-setup",
        dest="skip_setup",
        action="store_true",
        help="If this is passed, then the setup commands are skipped.",
    )
    parser.add_argument(
        "-c",
        "--cleanup",
        dest="cleanup",
        action="store_true",
        help="This kills all running containers and deletes all stored files.",
    )
    parser.add_argument(
        "-k",
        "--max-k",
        default=AwsConfig.MPC_CONFIG.K,
        type=int,
        dest="max_k",
        help="Maximum value of k for which the inputs need to be \
        created and uploaded during the setup phase. This value is \
        ignored if --skip-setup is passed. (default: `k` in aws_config.json)",
    )
    parser.add_argument(
        "--only-setup",
        dest="only_setup",
        action="store_true",
        help="If this value is passed, then only the setup phase is run,\
         otherwise both phases are run.",
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        nargs="?",
        help="If skip setup is passed, then a previous run_id for the same\
        MPC application needs to be specified to pickup the correct input files.",
    )
    args = parser.parse_args()
    if args.skip_setup and args.only_setup:
        parser.error("--only-setup and --skip-setup are mutually exclusive.")
    if args.skip_setup and not args.run_id:
        parser.error("--run-id needs to be passed with --skip-setup.")
    args.run_id = uuid.uuid4().hex if args.run_id is None else args.run_id
    trigger_run(args.run_id, args.skip_setup, args.max_k, args.only_setup, args.cleanup)
