import boto3
import paramiko
import os.path
import logging
from threading import Semaphore
from aws.AWSConfig import AwsConfig


class EC2Manager:
    current_vms_file_name = "current.vms"

    def __init__(self):
        self.ec2Resources = {
            region: boto3.resource(
                "ec2",
                aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
                aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
                region_name=region,
            )
            for region in AwsConfig.REGION.keys()
        }
        self.screenLock = Semaphore(value=1)
        self.instanceIdRegion = {}
        for region in AwsConfig.REGION.keys():
            ec2resource = self.ec2Resources[region]
            for instance in ec2resource.instances.all():
                self.instanceIdRegion[instance.id] = region
        self.instanceIdToNodeIdMap = None

    def get_setup_commands(self):
        with open(AwsConfig.SETUP_FILE_PATH, "r") as setup_file:
            return setup_file.read()

    def get_current_vm_instance_ids(self):
        with open(EC2Manager.current_vms_file_name, "r") as file_handle:
            data = file_handle.readlines()
        instance_ids = data[0].strip().split(",")
        return instance_ids

    def create_instances(self):
        if os.path.isfile(EC2Manager.current_vms_file_name):
            logging.info("Picking up VMs from current.vms file.")
            all_instance_ids = self.get_current_vm_instance_ids()
        else:
            logging.info("VM creation started.")
            all_instance_ids = []
            region_instance_id_map = {}
            for region, region_config in AwsConfig.REGION.items():
                ec2_resource = self.ec2Resources[region]
                instances = ec2_resource.create_instances(
                    ImageId=region_config.IMAGE_ID,
                    MinCount=region_config.VM_COUNT,
                    MaxCount=region_config.VM_COUNT,
                    SecurityGroupIds=region_config.SECURITY_GROUP_IDS,
                    KeyName=region_config.KEY_NAME,
                    InstanceType=AwsConfig.INSTANCE_TYPE,
                    TagSpecifications=[
                        {
                            "ResourceType": "instance",
                            "Tags": [{"Key": "Name", "Value": AwsConfig.VM_NAME}],
                        }
                    ],
                    UserData=self.get_setup_commands(),
                )

                region_instance_ids = []
                for instance in instances:
                    self.instanceIdRegion[instance.id] = region
                    all_instance_ids.append(instance.id)
                    region_instance_ids.append(instance.id)

                region_instance_id_map[region] = region_instance_ids

            for region, ids in region_instance_id_map.items():
                ec2_resource = self.ec2Resources[region]
                for instance_id in ids:
                    ec2_resource.Instance(id=instance_id).wait_until_running()

                ec2_client = boto3.client(
                    "ec2",
                    aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
                    aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
                    region_name=region,
                )
                ec2_client.get_waiter("instance_status_ok").wait(InstanceIds=ids)

            with open(EC2Manager.current_vms_file_name, "w") as file_handle:
                file_handle.write(",".join(all_instance_ids))
            logging.info("VMs successfully booted up.")
        all_instance_ips = [self.get_instance_public_ip(id) for id in all_instance_ids]
        self.instanceIdToNodeIdMap = {id: i for i, id in enumerate(all_instance_ids)}
        return all_instance_ids, all_instance_ips

    def terminate_instances_by_id(self):
        instance_ids = self.get_current_vm_instance_ids()
        for instance_id in instance_ids:
            ec2_resource = self.ec2Resources[self.instanceIdRegion[instance_id]]
            ec2_resource.Instance(id=instance_id).terminate()
        if os.path.isfile(EC2Manager.current_vms_file_name):
            os.remove(EC2Manager.current_vms_file_name)

    def get_instance_public_ip(self, instance_id):
        ec2_resource = self.ec2Resources[self.instanceIdRegion[instance_id]]
        return ec2_resource.Instance(id=instance_id).public_ip_address

    def execute_command_on_instance(
        self, instance_id, commands, verbose=False, output_file_prefix=None
    ):

        region_config = AwsConfig.REGION[self.instanceIdRegion[instance_id]]
        key = paramiko.RSAKey.from_private_key_file(region_config.KEY_FILE_PATH)
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ip = self.get_instance_public_ip(instance_id)

        try:
            ssh_client.connect(
                hostname=ip, username=AwsConfig.INSTANCE_USER_NAME, pkey=key
            )
            for command in commands:
                _, stdout, stderr = ssh_client.exec_command(command)
                self.screenLock.acquire()
                output = stdout.read()
                if len(output) != 0:
                    output = output.decode("utf-8")
                    if verbose:
                        print()
                        print(
                            f"{'#'*10} OUTPUT FROM {ip} | Command: {command} {'#'*10}"
                        )
                        logging.info(output)
                        print("#" * 30)
                    if output_file_prefix:
                        with open(
                            f"{output_file_prefix}_"
                            + f"{self.instanceIdToNodeIdMap[instance_id]}.log",
                            "w",
                        ) as output_file:
                            output_file.write(output)

                err = stderr.read()
                if len(err) != 0:
                    print()
                    print(f"{'#'*10} ERROR FROM {ip} | Command: {command} {'#'*10}")
                    print(err.decode("utf-8"))
                    print("~" * 30)
                self.screenLock.release()
            ssh_client.close()
        except Exception as ex:
            print(ex)
