import os
import json
import boto3
import logging
import traceback
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ErrorHandler:
    """
    Error handling utility for Lambda functions
    
    This class provides methods to:
    1. Record errors in DynamoDB
    2. Send error notifications via SNS
    3. Handle initialization errors that occur before DynamoDB is available
    """
    
    def __init__(self):
        """Initialize the error handler"""
        self.ddb_table_name = os.environ.get('DDB_TASK_TABLE_NAME')
        self.sns_topic_arn = os.environ.get('ERROR_SNS_TOPIC')
        
        # Initialize clients lazily to avoid initialization errors
        self._dynamodb_client = None
        self._sns_client = None
    
    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB client"""
        if self._dynamodb_client is None:
            self._dynamodb_client = boto3.client('dynamodb')
        return self._dynamodb_client
    
    @property
    def sns(self):
        """Lazy initialization of SNS client"""
        if self._sns_client is None:
            self._sns_client = boto3.client('sns')
        return self._sns_client
    
    def record_error(self, task_id, task_type, source_key, error_message, error_details=None):
        """
        Record error information in DynamoDB and send notification
        
        Args:
            task_id: Unique task identifier
            task_type: Type of task (e.g., 'doc/convert')
            source_key: Source object key
            error_message: Human-readable error message
            error_details: Optional detailed error information (stack trace, etc.)
        """
        try:
            # Record in DynamoDB if table name is available
            if self.ddb_table_name:
                self._record_in_dynamodb(task_id, task_type, source_key, error_message, error_details)
            
            # Send SNS notification if topic ARN is available
            if self.sns_topic_arn:
                self._send_sns_notification(task_id, task_type, source_key, error_message, error_details)
                
        except Exception as e:
            # Log but don't raise to avoid breaking the main error handling flow
            logger.error(f"Error in error handler: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _record_in_dynamodb(self, task_id, task_type, source_key, error_message, error_details=None):
        """Record error in DynamoDB"""
        try:
            # Check if task already exists
            try:
                response = self.dynamodb.get_item(
                    TableName=self.ddb_table_name,
                    Key={'TaskId': {'S': task_id}}
                )
                
                # If task exists, update it
                if 'Item' in response:
                    update_expr = "SET #status = :status, #error = :error, #updated = :updated"
                    expr_names = {
                        "#status": "Status",
                        "#error": "ErrorMessage",
                        "#updated": "Updated_at"
                    }
                    expr_values = {
                        ":status": {"S": "failed"},
                        ":error": {"S": error_message},
                        ":updated": {"S": datetime.now(timezone.utc).isoformat()}
                    }
                    
                    if error_details:
                        update_expr += ", #details = :details"
                        expr_names["#details"] = "ErrorDetails"
                        expr_values[":details"] = {"S": json.dumps(error_details)}
                    
                    self.dynamodb.update_item(
                        TableName=self.ddb_table_name,
                        Key={'TaskId': {'S': task_id}},
                        UpdateExpression=update_expr,
                        ExpressionAttributeNames=expr_names,
                        ExpressionAttributeValues=expr_values
                    )
                    logger.info(f"Updated existing task {task_id} with error information")
                    return
            except Exception:
                # Task doesn't exist or error occurred, continue to create it
                pass
            
            # Create new task record with error information
            item = {
                'TaskId': {'S': task_id},
                'TaskType': {'S': task_type},
                'SourceKey': {'S': source_key},
                'Status': {'S': 'failed'},
                'ErrorMessage': {'S': error_message},
                'Created_at': {'S': datetime.now(timezone.utc).isoformat()},
                'Updated_at': {'S': datetime.now(timezone.utc).isoformat()}
            }
            
            if error_details:
                item['ErrorDetails'] = {'S': json.dumps(error_details)}
            
            self.dynamodb.put_item(
                TableName=self.ddb_table_name,
                Item=item
            )
            logger.info(f"Created new task record for failed task {task_id}")
            
        except Exception as e:
            logger.error(f"Error recording failure in DynamoDB: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _send_sns_notification(self, task_id, task_type, source_key, error_message, error_details=None):
        """Send error notification via SNS"""
        try:
            message = {
                'task_id': task_id,
                'task_type': task_type,
                'source_key': source_key,
                'error_message': error_message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            if error_details:
                message['error_details'] = error_details
            
            self.sns.publish(
                TopicArn=self.sns_topic_arn,
                Subject=f"Media Processing Error: {task_id}",
                Message=json.dumps(message, indent=2)
            )
            logger.info(f"Sent error notification for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error sending SNS notification: {str(e)}")
            logger.error(traceback.format_exc())

# Global instance for reuse across Lambda invocations
error_handler = ErrorHandler()

def capture_error(func):
    """
    Decorator to capture and handle errors in Lambda functions
    
    Usage:
    @capture_error
    def my_handler(event, context):
        # Your handler code
    """
    def wrapper(event, context):
        task_id = None
        source_key = "unknown"
        task_type = "unknown"
        
        try:
            # Extract task ID from event
            if 'TaskId' in event:
                task_id = event['TaskId']
            elif 'requestContext' in event and 'requestId' in event['requestContext']:
                task_id = event['requestContext']['requestId']
            else:
                task_id = context.aws_request_id
            
            # Extract source key from event
            if 'pathParameters' in event and event['pathParameters'] and 'proxy' in event['pathParameters']:
                source_key = event['pathParameters']['proxy']
            
            # Extract task type from path
            if 'path' in event:
                path = event['path']
                if 'doc' in path:
                    task_type = 'doc/convert'
                elif 'image' in path:
                    task_type = 'image/process'
                elif 'video' in path:
                    task_type = 'video/process'
                elif 'audio' in path:
                    task_type = 'audio/process'
            
            # Call the original function
            return func(event, context)
            
        except Exception as e:
            # Get detailed error information
            error_message = str(e)
            error_details = {
                'traceback': traceback.format_exc(),
                'error_type': e.__class__.__name__
            }
            
            # Log the error
            logger.error(f"Error in Lambda function: {error_message}")
            logger.error(traceback.format_exc())
            
            # Record the error
            error_handler.record_error(task_id, task_type, source_key, error_message, error_details)
            
            # Re-raise the exception for Lambda's built-in error handling
            raise
    
    return wrapper