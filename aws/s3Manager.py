import boto3
from concurrent.futures import ThreadPoolExecutor
from aws.AWSConfig import AwsConfig


class S3Manager(object):
    def __init__(self, run_id):
        # Always create bucket in 'us-east-1'
        self.s3Client = boto3.client(
            "s3",
            aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
            aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
            region_name="us-east-1",
        )
        self.bucket = AwsConfig.BUCKET_NAME
        self.prefix = run_id
        self.s3Client.create_bucket(Bucket=self.bucket)

    def upload_config(self, instance_id, instance_config):
        key = "%s/config-%d.json" % (self.prefix, instance_id)
        self.s3Client.put_object(
            Body=instance_config.encode(),
            Bucket=self.bucket,
            Key=key,
            ACL="public-read",
        )
        return "https://s3.amazonaws.com/{0}/{1}".format(self.bucket, key)

    def upload_file(self, file_name):
        key = "%s/%s" % (self.prefix, file_name)
        self.s3Client.upload_file(
            file_name, Bucket=self.bucket, Key=key, ExtraArgs={"ACL": "public-read"}
        )
        return "https://s3.amazonaws.com/{0}/{1}".format(self.bucket, key)

    def upload_configs(self, instance_configs):
        with ThreadPoolExecutor(max_workers=100) as executor:
            urls = executor.map(self.upload_config, *zip(*instance_configs))
            return list(urls)

    def upload_files(self, file_names):
        with ThreadPoolExecutor(max_workers=100) as executor:
            urls = executor.map(self.upload_file, file_names)
            return list(urls)

    def cleanup(self):
        response = self.s3Client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        keys_to_delete = []
        if "Contents" in response:
            for obj in response["Contents"]:
                keys_to_delete.append({"Key": obj["Key"]})
            self.s3Client.delete_objects(
                Bucket=self.bucket, Delete={"Objects": keys_to_delete}
            )
