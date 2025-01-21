import os
import boto3
from botocore.exceptions import ClientError
from s3_operations import S3Config
from enum import Enum
from datetime import datetime, timezone

class TaskStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ProcessingError(Exception):
    """Custom exception for processing errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class DDBConfig:
    """DynamoDB configuration class"""
    def __init__(self):
        self.region_name = os.getenv("AWS_REGION", "us-east-1")
        self.bwm_table_name = os.getenv("DDB_BWM_TABLE_NAME")
        self.task_table_name = os.getenv("DDB_TASK_TABLE_NAME")
        
        if not self.bwm_table_name :
            raise ValueError("DDB_BWM_TABLE_NAME environment variable must be set")
        if not self.task_table_name:
            raise ValueError("DDB_TASK_TABLE_NAMEenvironment variable must be set")


def get_ddb_client():
    """Get DynamoDB client with configured region"""
    config = DDBConfig()
    return boto3.client(
        'dynamodb',
        region_name=config.region_name
    )

def create_task_record(task_id: str, source_key: str, target_key: str, task_type: str, conversion_params: dict):
    """
    Create a new task record in DynamoDB
    
    Args:
        task_id: Unique identifier for the task
        source_key: Source document S3 key
        target_key: Target document S3 key
        conversion_params: Parameters for document conversion
    """
    config = DDBConfig()
    client = get_ddb_client()
    s3_config = S3Config()
    
    try:
        client.put_item(
            TableName=config.task_table_name,
            Item={
                'TaskId': {'S': task_id},
                'SourceKey': {'S': source_key},
                'TargetKey': {'S': target_key},
                'SourceBucket': {'S': s3_config.bucket_name},
                'TargetBucket': {'S': s3_config.bucket_name},
                'Status': {'S': TaskStatus.PROCESSING.value},
                'TaskInfo':{'S': str(conversion_params)},
                'TaskType': {'S': task_type},
                'Created_at': {'S': datetime.now(timezone.utc).isoformat()},
                'Updated_at': {'S': datetime.now(timezone.utc).isoformat()}
            }
        )
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to create task record: {str(e)}"
        )

def update_task_status(task_id: str, task_type: str, status: TaskStatus, message: str = None):
    """
    Update task status in DynamoDB
    
    Args:
        task_id: Task identifier
        status: New status
        error_message: Optional error message for failed tasks
    """
    config = DDBConfig()
    client = get_ddb_client()
    
    update_expr = "SET #status = :status, #updated = :updated"
    expr_names = {
        "#status": "Status",
        "#updated": "Updated_at"
    }
    expr_values = {
        ":status": {"S": status.value},
        ":updated": {"S": datetime.now(timezone.utc).isoformat()}
    }
    
    if message:
        if status == TaskStatus.FAILED:
            update_expr += ", #error = :error"
            expr_names["#error"] = "ErrorMessage"
            expr_values[":error"] = {"S": message}
        elif status == TaskStatus.COMPLETED:
            update_expr += ", #result = :result"
            expr_names["#result"] = "Result"
            expr_values[":result"] = {"S": message}
    
    try:
        client.update_item(
            TableName=config.task_table_name,
            Key={'TaskId': {'S': task_id}},
                #  'TaskType':{'S': task_type}},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to update task status: {str(e)}"
        )

def get_task_status(task_id: str, task_type: str) -> dict:
    """
    Get task status from DynamoDB
    
    Args:
        task_id: Task identifier
        task_type: Task type        
    Returns:
        dict: Task record
    """
    config = DDBConfig()
    client = get_ddb_client()
    
    try:
        response = client.get_item(
            TableName=config.task_table_name,
            Key={'TaskId': {'S': task_id}}
                #  'TaskType':{'S': task_type}}
        )
        print(response)
        if 'Item' not in response:
            raise ProcessingError(
                status_code=404,
                detail=f"Task not found: {task_id}"
            )
        return response['Item']
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )

def create_watermark_record(text: str, password_wm: int, password_img: int, block_shape: tuple, 
                          d1: int, d2: int, wm_length: int):
    """
    Create a watermark record in DynamoDB with specific watermark parameters
    
    Args:
        text: Watermark text
        password_wm: Password for watermark
        password_img: Password for image
        block_shape: Block shape tuple
        d1: Watermark strength parameter
        d2: Watermark robustness parameter
        wm_length: Length of watermark bit array
    """
    config = DDBConfig()
    client = get_ddb_client()
    
    try:
        client.put_item(
            TableName=config.bwm_table_name,
            Item={
                'WaterMakerContent': {'S': text},
                'PasswordWM': {'N': str(password_wm)},
                'PasswordImg': {'N': str(password_img)},
                'BlockShape': {'S': f"{block_shape[0]},{block_shape[1]}"},
                'D1': {'N': str(d1)},
                'D2': {'N': str(d2)},
                'WmLength': {'N': str(wm_length)},
                'Timestamp': {'S': datetime.now(timezone.utc).isoformat()}
            }
        )
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to create watermark record: {str(e)}"
        )

def scan_watermark_records():
    """
    Scan all watermark records from DynamoDB
    
    Returns:
        List of watermark records with their parameters
    """
    config = DDBConfig()
    client = get_ddb_client()
    
    try:
        paginator = client.get_paginator('scan')
        watermark_records = []
        
        for page in paginator.paginate(TableName=config.bwm_table_name):
            for item in page['Items']:
                if 'WaterMakerContent' in item:  # Only process watermark records
                    watermark_records.append({
                        'text': item['WaterMakerContent']['S'],
                        'block_shape': [int(x) for x in item['BlockShape']['S'].split(',')],
                        'password_wm': int(item['PasswordWM']['N']),
                        'password_img': int(item['PasswordImg']['N']),
                        'wm_length': int(item['WmLength']['N'])
                    })
        
        return watermark_records
    except ClientError as e:
        raise ProcessingError(
            status_code=500,
            detail=f"Failed to scan watermark records: {str(e)}"
        )
