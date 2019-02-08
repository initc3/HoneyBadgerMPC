# How to run?
1. `cd /path/to/HoneyBadgerMPC`
2. Update the config with appropriate parameters. Run `python -m aws.run-on-ec2` to start the AWS instances and run the honeybadgermc command specified in the config. This command creates a `current.vms` file which consists of instance ids of the VMs created during this run. Subsequent runs of this command will reuse the same VMs.
3. After you are done testing you can delete the VMs using `python -m aws.delete_vms`.
4. The value of `N` for the MPC applications is equal to the total number of VMs created in all the regions.

# Configuration
1. This code pulls the docker image with tag:`latest` from [here](https://hub.docker.com/r/smkuls/honeybadgermpc/tags/). In order to replace the docker image, update `image_path` in `aws-config.json` with the appropriate image.
2. Make sure you have the following two environment variables set to appropriate values. Please use the export command if you are setting them within the container. Eg: `export <key>=<value>`.
    1. `ACCESS_KEY_ID` - Set this to your AWS access key id.
    2. `SECRET_ACCESS_KEY` - Set this to your AWS secret acces key.
3. The description of the config is as follows. Update keys accordingly.
    1. `mpc`: This contains configuration for the MPC application.
        1. `command`: The command to run to trigger the MPC application.
        2. `t`: Number of corrupt nodes.
        3. `port`: Port on which the node is listening.
        4. `num_triples`: Number of triples which need to be generated in the preprocessing phase.
    2. `aws`: AWS related configuration.
        1. `setup_file_path`: Path to a shell script which contains all commands required to be run when starting up the instance.
        2. `region`: Contains AWS region specific information.
            1. `vm_count`: Number of VMs to be created in this region.
            2. `security_group_ids`: Security groups to be associated with instances of this region. These security groups must pre-exist and should allow all traffic.
            3. `image_id`: AMI of an image for Ubuntu 18.04 LTS for this region.
            4. `key_file_path`: Path to the private key in order to SSH into the instances of this region. Make sure that the permissions of the key pair are `400`.
            5. `key_name`: Name of the key pair present in this region in order to SSH into the instances.
        3. `vm_name`: Name of the VM to allow to distinguish them on the AWS console. All VMs will have the same name.
        4. `instance_type`: Size of the instances.
        5. `instance_user_name`: For an Ubuntu AMI, this is `ubuntu`. Make sure to update this if a different OS is used for the instances.
        6. `bucket_name`: Name of the bucket in S3 where the config files will be stored. If the bucket doesn't exist, it will be created. AWS requires bucket names to be unique across all users so if the bucket creation fails specify another unique name.
    3. `docker`:
        1. `image_path`: Path to the docker image along with the tag on DockerHub.


# Benchmarking and collection
There is a `BenchmarkLogger` which must be used when logging any benchmak data. This logger spits logs on to a separate file per node. After the MPC program finishes, the benchmark logs from all nodes are collected on to the machine from where the run was triggered. Each AWS run has a `Run Id` associated with it. The file names of the collected logs are of the format `benchmark_{node_id}.log` and are placed in a folder with the same name as the `Run Id`.

# Building the docker image for AWS
Use the following commands to push the image to dockerhub. Avoid building the image using `docker-compose` since it doesn't the ignore files specified in `.dockerignore`.
```
cd /path/to/HoneyBadgerMPC
docker build -t honeybadger . --build-arg BUILD=dev
docker tag honeybadger:latest smkuls/honeybadgermpc:latest # Replace with appropriate DockerHub location
docker push smkuls/honeybadgermpc:latest # Replace with appropriate DockerHub location

```