import boto3
from botocore.exceptions import ClientError
import os

class S3Config:
    """S3 configuration class"""
    def __init__(self):
        self.region_name = os.getenv("AWS_REGION", "us-east-1")
        self.bucket_name = os.getenv("S3_BUCKET_NAME")
        self.object_prefix = os.getenv("S3_OBJECT_PREFIX", "")
        
        if not self.bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable must be set")

def get_s3_client():
    """Get S3 client with configured region"""
    config = S3Config()
    return boto3.client(
        's3',
        region_name=config.region_name
    )

def download_object_from_s3(client, bucket, key):
    """
    Download object from S3
    
    Args:
        client: boto3 S3 client
        bucket: S3 bucket name
        key: Object key in S3
        
    Returns:
        bytes: object data
        
    Raises:
        ProcessingError: If object not found or bucket not configured
    """
    if not bucket:
        raise ProcessingError(
            status_code=500,
            detail="S3 bucket not configured. Set S3_BUCKET_NAME environment variable."
        )
    
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            raise ProcessingError(status_code=404, detail=f"object not found: {key}")
        elif e.response['Error']['Code'] == 'NoSuchBucket':
            raise ProcessingError(status_code=500, detail=f"Bucket not found: {bucket}")
        else:
            raise ProcessingError(status_code=500, detail=f"S3 error: {str(e)}")

def upload_object_to_s3(client, bucket, key, object_data):
    """
    Upload object to S3
    
    Args:
        client: boto3 S3 client
        bucket: S3 bucket name
        key: Object key in S3
        object_data: object bytes to upload
        
    Raises:
        ProcessingError: If upload fails or bucket not configured
    """
    if not bucket:
        raise ProcessingError(
            status_code=500,
            detail="S3 bucket not configured. Set S3_BUCKET_NAME environment variable."
        )
    
    try:
        client.put_object(Bucket=bucket, Key=key, Body=object_data)
    except ClientError as e:
        raise ProcessingError(status_code=500, detail=f"Failed to upload object: {str(e)}")

def get_full_s3_key(object_key: str) -> str:
    """Get full S3 key including prefix if configured"""
    config = S3Config()
    return os.path.join(config.object_prefix, object_key)

def generate_presigned_url(client, bucket: str, key: str, expiration: int = 3600) -> str:
    """
    Generate a presigned URL for an S3 object
    
    Args:
        client: boto3 S3 client
        bucket: S3 bucket name
        key: Object key in S3
        expiration: URL expiration time in seconds (default 1 hour)
        
    Returns:
        str: Presigned URL for the object
        
    Raises:
        ProcessingError: If URL generation fails
    """
    try:
        response = client.generate_presigned_url('get_object',
                                               Params={'Bucket': bucket,
                                                      'Key': key},
                                               ExpiresIn=expiration)
        return response
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to generate presigned URL: {str(e)}"
        )

class ProcessingError(Exception):
    """Custom exception for processing errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
