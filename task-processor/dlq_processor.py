import json
import os
import boto3
import logging
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize clients
dynamodb = boto3.client('dynamodb')
sns = boto3.client('sns')

# Get environment variables
DDB_TABLE_NAME = os.environ.get('DDB_TABLE_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

def handler(event, context):
    """
    Process messages from the Dead Letter Queue
    
    This function:
    1. Extracts failed task information from DLQ messages
    2. Records failures in DynamoDB if not already recorded
    3. Sends notifications via SNS
    """
    # Print the entire event for debugging
    print(f"### FULL EVENT STRUCTURE ###")
    print(json.dumps(event, indent=2))
    print(f"### END OF FULL EVENT STRUCTURE ###")
    
    # Log the entire event for debugging
    logger.info(f"Full event structure: {json.dumps(event)}")
    
    logger.info(f"Processing {len(event['Records'])} DLQ messages")
    
    for i, record in enumerate(event['Records']):
        try:
            # Print the full record for debugging
            print(f"### RECORD {i} STRUCTURE ###")
            print(json.dumps(record, indent=2))
            print(f"### END OF RECORD {i} STRUCTURE ###")
            
            # Log the full record for debugging
            logger.info(f"Full record structure: {json.dumps(record)}")
            
            # Extract task information
            task_id = None
            error_message = "Unknown error"
            task_type = "unknown"
            source_key = "unknown"
            
            # First check messageAttributes for error information - this is the most reliable source
            if 'messageAttributes' in record and record['messageAttributes']:
                # Extract error message from messageAttributes if available
                if 'ErrorMessage' in record['messageAttributes']:
                    error_attr = record['messageAttributes']['ErrorMessage']
                    if 'stringValue' in error_attr:
                        error_message = error_attr['stringValue']
                        print(f"Found error message in messageAttributes: {error_message}")
                
                # Extract request ID from messageAttributes if available
                if 'RequestID' in record['messageAttributes']:
                    req_id_attr = record['messageAttributes']['RequestID']
                    if 'stringValue' in req_id_attr:
                        # Use this as a fallback task ID
                        if not task_id:
                            task_id = req_id_attr['stringValue']
                            print(f"Found request ID in messageAttributes: {task_id}")
            
            # Parse the message body
            try:
                message_body = json.loads(record['body'].strip())
                print(f"Successfully parsed message body: {json.dumps(message_body)}")
                
                # Extract task ID from message body
                if 'TaskId' in message_body:
                    task_id = message_body['TaskId']
                    print(f"Found TaskId in message body: {task_id}")
                
                # Extract task type from path
                if 'path' in message_body:
                    path = message_body['path']
                    if 'doc' in path or 'async-doc' in path:
                        task_type = 'doc/convert'
                    elif 'image' in path or 'async-image' in path:
                        task_type = 'image/process'
                    elif 'video' in path:
                        task_type = 'video/process'
                    elif 'audio' in path:
                        task_type = 'audio/process'
                    print(f"Determined task type from path: {task_type}")
                
                # Extract source key from pathParameters
                if 'pathParameters' in message_body and message_body['pathParameters']:
                    if 'proxy' in message_body['pathParameters']:
                        source_key = message_body['pathParameters']['proxy']
                        print(f"Found source key in pathParameters: {source_key}")
                
                # Extract operations from queryStringParameters
                operations = None
                if 'queryStringParameters' in message_body and message_body['queryStringParameters']:
                    if 'operations' in message_body['queryStringParameters']:
                        operations = message_body['queryStringParameters']['operations']
                        print(f"Found operations in queryStringParameters: {operations}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message body as JSON: {str(e)}")
                print(f"### ERROR: Failed to parse message body as JSON: {str(e)} ###")
                # If we can't parse the body, we'll rely on messageAttributes
            
            # If we still don't have a task ID, generate one
            if not task_id:
                task_id = f"error-{context.aws_request_id}"
                print(f"Generated task ID: {task_id}")
            
            # Process the error message from messageAttributes
            if error_message == "Unknown error" and 'messageAttributes' in record:
                if 'ErrorMessage' in record['messageAttributes']:
                    error_value = record['messageAttributes']['ErrorMessage'].get('stringValue', '')
                    
                    # Check for specific error patterns
                    if "Runtime exited with error: signal: killed" in error_value:
                        error_message = "Lambda was terminated due to memory limit exceeded (signal: killed)"
                        print(f"Detected memory limit error: {error_message}")
                    elif "Task timed out after" in error_value:
                        error_message = f"Lambda function timed out: {error_value}"
                        print(f"Detected timeout error: {error_message}")
                    else:
                        # Use the raw error message
                        error_message = error_value
                        print(f"Using raw error message: {error_message}")
            
            # Enhance error message with operations information if available
            if operations and not operations in error_message:
                error_message = f"{error_message} (Operations: {operations})"
            
            # Record the error in DynamoDB
            record_error_in_ddb(task_id, task_type, source_key, error_message)
            
            # Send notification via SNS
            send_error_notification(task_id, task_type, source_key, error_message, operations)
            
        except Exception as e:
            logger.error(f"Error processing DLQ message: {str(e)}")
            print(f"### ERROR processing DLQ message: {str(e)} ###")
            # Continue processing other messages even if one fails

def record_error_in_ddb(task_id, task_type, source_key, error_message):
    """Record error information in DynamoDB"""
    try:
        # Check if task already exists
        try:
            response = dynamodb.get_item(
                TableName=DDB_TABLE_NAME,
                Key={'TaskId': {'S': task_id}}
            )
            
            # If task exists, update it
            if 'Item' in response:
                dynamodb.update_item(
                    TableName=DDB_TABLE_NAME,
                    Key={'TaskId': {'S': task_id}},
                    UpdateExpression="SET #status = :status, #error = :error, #updated = :updated",
                    ExpressionAttributeNames={
                        "#status": "Status",
                        "#error": "ErrorMessage",
                        "#updated": "Updated_at"
                    },
                    ExpressionAttributeValues={
                        ":status": {"S": "failed"},
                        ":error": {"S": error_message},
                        ":updated": {"S": datetime.now(timezone.utc).isoformat()}
                    }
                )
                logger.info(f"Updated existing task {task_id} with error information")
                return
        except ClientError:
            # Task doesn't exist, continue to create it
            pass
        
        # Create new task record with error information
        dynamodb.put_item(
            TableName=DDB_TABLE_NAME,
            Item={
                'TaskId': {'S': task_id},
                'TaskType': {'S': task_type},
                'SourceKey': {'S': source_key},
                'Status': {'S': 'failed'},
                'ErrorMessage': {'S': error_message},
                'Created_at': {'S': datetime.now(timezone.utc).isoformat()},
                'Updated_at': {'S': datetime.now(timezone.utc).isoformat()}
            }
        )
        logger.info(f"Created new task record for failed task {task_id}")
        
    except Exception as e:
        logger.error(f"Error recording failure in DynamoDB: {str(e)}")

def send_error_notification(task_id, task_type, source_key, error_message, operations=None):
    """Send error notification via SNS"""
    try:
        # Format the error message for better readability
        formatted_message = f"Media Processing Error in {task_type}\n\n"
        formatted_message += f"Task ID: {task_id}\n"
        formatted_message += f"Source File: {source_key}\n"
        
        # Add operations information if available
        if operations:
            formatted_message += f"Operations: {operations}\n"
            
        formatted_message += f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n"
        
        # Add error type classification
        if "memory" in error_message.lower() or "signal: killed" in error_message.lower():
            formatted_message += "ERROR TYPE: MEMORY LIMIT EXCEEDED\n\n"
        elif "timeout" in error_message.lower():
            formatted_message += "ERROR TYPE: FUNCTION TIMEOUT\n\n"
        else:
            formatted_message += "ERROR TYPE: PROCESSING ERROR\n\n"
            
        formatted_message += f"Error Details:\n{error_message}\n"
        
        # Create JSON message for structured data
        message_json = {
            'task_id': task_id,
            'task_type': task_type,
            'source_key': source_key,
            'error_message': error_message,
            'operations': operations,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Send notification with both formatted text and JSON structure
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"Media Processing Error: {task_id}",
            Message=formatted_message,
            MessageAttributes={
                'JSON_Data': {
                    'DataType': 'String',
                    'StringValue': json.dumps(message_json)
                }
            }
        )
        logger.info(f"Sent error notification for task {task_id}")
        
    except Exception as e:
        logger.error(f"Error sending SNS notification: {str(e)}")
