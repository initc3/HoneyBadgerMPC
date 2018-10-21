import boto3
from aws.AWSConfig import AwsConfig


class S3Manager(object):
    def __init__(self, runId):
        # Always create bucket in 'us-east-1'
        self.s3Client = boto3.client(
            's3',
            aws_access_key_id=AwsConfig.ACCESS_KEY_ID,
            aws_secret_access_key=AwsConfig.SECRET_ACCESS_KEY,
            region_name="us-east-1",
        )
        self.bucket = AwsConfig.BUCKET_NAME
        self.prefix = runId
        self.s3Client.create_bucket(Bucket=self.bucket)

    def uploadConfig(self, instanceConfig):
        key = "%s/config.ini" % (self.prefix)
        self.s3Client.put_object(
            Body=instanceConfig.encode(),
            Bucket=self.bucket,
            Key=key,
            ACL="public-read"
        )
        return "https://s3.amazonaws.com/{0}/{1}".format(self.bucket, key)

    def uploadFile(self, fileName):
        key = "%s/%s" % (self.prefix, fileName)
        self.s3Client.upload_file(
            fileName,
            Bucket=self.bucket,
            Key=key,
            ExtraArgs={'ACL': 'public-read'}
        )
        return "https://s3.amazonaws.com/{0}/{1}".format(self.bucket, key)

    def cleanup(self):
        response = self.s3Client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=self.prefix
        )
        keysToDelete = []
        for obj in response['Contents']:
            keysToDelete.append({'Key': obj["Key"]})
        self.s3Client.delete_objects(
            Bucket=self.bucket,
            Delete={
                'Objects': keysToDelete
            }
        )
