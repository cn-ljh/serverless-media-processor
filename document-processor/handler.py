import json
import boto3
from typing import Dict, Any
from urllib.parse import unquote
from doc_processor import process_document, get_task_status

lambda_client = boto3.client('lambda')

def invoke_async_processing(function_name: str, event: Dict[str, Any], task_id: str):
    """Invoke lambda function asynchronously"""
    # Add task_id to event for async processing
    event['taskId'] = task_id
    event['isAsync'] = False  # Mark as processing phase
    
    # Invoke lambda asynchronously
    lambda_client.invoke(
        FunctionName=function_name,
        InvocationType='Event',  # Async invocation
        Payload=json.dumps(event)
    )

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for document processing"""
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Handle different HTTP methods
        
        object_key = unquote(event.get('pathParameters', {}).get('proxy', ''))
        query_params = event.get('queryStringParameters', {}) or {}
        operations_str = query_params.get('operations', '')
        
        if not object_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'object_key is required in path parameters'
                })
            }
        
        if not operations_str:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'operations are required in query parameters'
                })
            }

        # Parse operations string
        parts = operations_str.split(',')
        if len(parts) < 3 or parts[0] != 'convert':
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid operations format. Expected: convert,target_format,source_format'
                })
            }

        # Check if this is an async processing request
        is_async = event.get('isAsync', True)
        task_id = event.get('taskId')
        
        # Process document
        response = process_document(object_key, operations_str)
        
        # If initial async request, trigger processing
        if is_async and not task_id:
            invoke_async_processing(
                context.invoked_function_arn,
                event,
                response.body['task_id']
            )
        return {
            'statusCode': response.status_code,
            'body': json.dumps(response.body)
        }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
