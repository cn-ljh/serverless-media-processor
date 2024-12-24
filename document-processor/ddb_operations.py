import os
import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from pydantic import BaseModel, Field
from s3_operations import S3Config
from enum import Enum
from datetime import datetime, timezone

class TaskStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DDBConfig(BaseModel):
    region_name: str = Field(default=os.getenv("AWS_REGION", "us-east-1"))
    table_name: str = Field(
        default=os.getenv("DDB_TABLE_NAME"),
        description="DynamoDB table name is required. Set DDB_TABLE_NAME environment variable."
    )

    def __init__(self, **data):
        super().__init__(**data)
        if not self.table_name:
            raise ValueError("DDB_TABLE_NAME environment variable must be set")

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
            TableName=config.table_name,
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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create task record: {str(e)}"
        )

def update_task_status(task_id: str, status: TaskStatus, error_message: str = None):
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
    
    if error_message and status == TaskStatus.FAILED:
        update_expr += ", #error = :error"
        expr_names["#error"] = "ErrorMessage"
        expr_values[":error"] = {"S": error_message}
    
    try:
        client.update_item(
            TableName=config.table_name,
            Key={'TaskId': {'S': task_id}},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update task status: {str(e)}"
        )

def get_task_status(task_id: str) -> dict:
    """
    Get task status from DynamoDB
    
    Args:
        task_id: Task identifier
        
    Returns:
        dict: Task record
    """
    config = DDBConfig()
    client = get_ddb_client()
    
    try:
        response = client.get_item(
            TableName=config.table_name,
            Key={'TaskId': {'S': task_id}}
        )
        if 'Item' not in response:
            raise HTTPException(
                status_code=404,
                detail=f"Task not found: {task_id}"
            )
        return response['Item']
    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get task status: {str(e)}"
        )
