import boto3
import paramiko
import os.path
from threading import Semaphore
from aws.AWSConfig import AwsConfig


class EC2Manager:
    currentVMsFileName = "current.vms"

    def __init__(self):
        self.ec2Resources = {
            region: boto3.resource(
                'ec2',
                aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
                aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
                region_name=region
            ) for region in AwsConfig.REGION.keys()
        }
        self.screenLock = Semaphore(value=1)
        self.instanceIdRegion = {}
        for region in AwsConfig.REGION.keys():
            ec2Resource = self.ec2Resources[region]
            for instance in ec2Resource.instances.all():
                self.instanceIdRegion[instance.id] = region
        self.instanceIdToNodeIdMap = None

    def getSetupCommands(self):
        with open(AwsConfig.SETUP_FILE_PATH, "r") as setupFile:
            return setupFile.read()

    def getCurrentVMInstanceIds(self):
        with open(EC2Manager.currentVMsFileName, "r") as fileHandle:
            data = fileHandle.readlines()
        instanceIds = data[0].strip().split(",")
        return instanceIds

    def createInstances(self):
        if os.path.isfile(EC2Manager.currentVMsFileName):
            print(">>> Picking up VMs from current.vms file. <<<")
            allInstanceIds = self.getCurrentVMInstanceIds()
        else:
            print(">>> VM creation started. <<<")
            allInstanceIds = []
            regionInstanceIdMap = {}
            for region, regionConfig in AwsConfig.REGION.items():
                ec2Resource = self.ec2Resources[region]
                instances = ec2Resource.create_instances(
                    ImageId=regionConfig.IMAGE_ID,
                    MinCount=regionConfig.VM_COUNT,
                    MaxCount=regionConfig.VM_COUNT,
                    SecurityGroupIds=regionConfig.SECURITY_GROUP_IDS,
                    KeyName=regionConfig.KEY_NAME,
                    InstanceType=AwsConfig.INSTANCE_TYPE,
                    TagSpecifications=[
                        {
                            'ResourceType': 'instance',
                            'Tags': [
                                {
                                    'Key': 'Name',
                                    'Value': AwsConfig.VM_NAME
                                },
                            ]
                        },
                    ],
                    UserData=self.getSetupCommands()
                )

                regionInstanceIds = []
                for instance in instances:
                    self.instanceIdRegion[instance.id] = region
                    allInstanceIds.append(instance.id)
                    regionInstanceIds.append(instance.id)

                regionInstanceIdMap[region] = regionInstanceIds

            for region, ids in regionInstanceIdMap.items():
                ec2Resource = self.ec2Resources[region]
                for instanceId in ids:
                    ec2Resource.Instance(id=instanceId).wait_until_running()

                ec2Client = boto3.client(
                    'ec2',
                    aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
                    aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
                    region_name=region
                )
                ec2Client.get_waiter('instance_status_ok').wait(
                    InstanceIds=ids
                )

            with open(EC2Manager.currentVMsFileName, "w") as file_handle:
                file_handle.write(",".join(allInstanceIds))
            print(">>> VMs successfully booted up. <<<")
        allInstanceIps = [self.getInstancePublicIp(id) for id in allInstanceIds]
        self.instanceIdToNodeIdMap = {id: i for i, id in enumerate(allInstanceIds)}
        return allInstanceIds, allInstanceIps

    def terminateInstancesById(self):
        instanceIds = self.getCurrentVMInstanceIds()
        for instanceId in instanceIds:
            ec2Resource = self.ec2Resources[self.instanceIdRegion[instanceId]]
            ec2Resource.Instance(id=instanceId).terminate()
        if os.path.isfile(EC2Manager.currentVMsFileName):
            os.remove(EC2Manager.currentVMsFileName)

    def getInstancePublicIp(self, instanceId):
        ec2Resource = self.ec2Resources[self.instanceIdRegion[instanceId]]
        return ec2Resource.Instance(id=instanceId).public_ip_address

    def executeCommandOnInstance(
        self,
        instanceId,
        commands,
        verbose=False,
        outputFilePrefix=None
    ):

        regionConfig = AwsConfig.REGION[self.instanceIdRegion[instanceId]]
        key = paramiko.RSAKey.from_private_key_file(regionConfig.KEY_FILE_PATH)
        sshClient = paramiko.SSHClient()
        sshClient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ip = self.getInstancePublicIp(instanceId)

        try:
            sshClient.connect(
                    hostname=ip,
                    username=AwsConfig.INSTANCE_USER_NAME,
                    pkey=key)
            for command in commands:
                _, stdout, stderr = sshClient.exec_command(command)
                self.screenLock.acquire()
                output = stdout.read()
                if len(output) != 0:
                    output = output.decode('utf-8')
                    if verbose:
                        print()
                        print(
                            f"{'#'*10} OUTPUT FROM {ip} | Command: {command} {'#'*10}"
                        )
                        print(output)
                        print("#" * 30)
                    if outputFilePrefix:
                        with open(
                                    f"{outputFilePrefix}_" +
                                    f"{self.instanceIdToNodeIdMap[instanceId]}.log",
                                    "w"
                                ) as outputFile:
                            outputFile.write(output)

                err = stderr.read()
                if len(err) != 0:
                    print()
                    print(
                            f"{'#'*10} ERROR FROM {ip} | Command: {command} {'#'*10}"
                        )
                    print(err.decode('utf-8'))
                    print("~" * 30)
                self.screenLock.release()
            sshClient.close()
        except Exception as ex:
            print(ex)
