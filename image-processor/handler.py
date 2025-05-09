import json
import uuid
import traceback
from typing import Dict, Any
import base64
from urllib.parse import unquote
from image_processor import process_image
from error_handler import capture_error, error_handler

@capture_error
def handler(event: Dict[str, Any], context:Any) -> Dict[str, Any]:
    """Get and process image based on path parameter and operations"""
    print(f"Received event: {json.dumps(event)}")

    try:
        path_params = event.get('pathParameters', {})
        proxy_path = path_params.get('proxy', '')
        request_path = event.get('path', '')
        object_key = unquote(proxy_path)
        query_params = event.get('queryStringParameters', {}) or {}
        operations_str = query_params.get('operations', '')
        
        if not object_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Image key is required in path parameter'
                })
            }
        is_async = request_path.startswith('/async-image/')
        # Generate or get task ID for async processing
        task_id = event.get("TaskId", str(uuid.uuid4())) if is_async else str(uuid.uuid4())

        if is_async:
            # For async requests, return task information
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'TaskId': task_id,
                    'message': 'Image processing task received and started'
                })
            }
        # For sync requests, process and return the image
        processed_image = process_image(object_key, operations_str, task_id)

        # Get content type from headers
        content_type = processed_image.headers.get('Content-Type', 'image/jpeg')
        
        # Use standard base64 encoding for binary data
        base64_body = base64.b64encode(processed_image.body).decode('utf-8')
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': content_type
            },
            'body': base64_body,
            'isBase64Encoded': True
        }

    except Exception as e:
        # Get task ID from event or context
        task_id = event.get("TaskId", context.aws_request_id)
        
        # Extract error details
        error_message = str(e)
        error_details = {
            'traceback': traceback.format_exc(),
            'error_type': e.__class__.__name__,
            'event_path': event.get('path', ''),
            'operation': query_params.get('operations', '')
        }
        
        # Record error in DynamoDB and send notification
        error_handler.record_error(
            task_id=task_id,
            task_type="image/process",
            source_key=object_key if 'object_key' in locals() else "unknown",
            error_message=error_message,
            error_details=error_details
        )
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'task_id': task_id,
                'message': 'Error details have been recorded and will be investigated.'
            })
        }

# def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
#     """Lambda handler for image processing"""
#     print(f"Received event: {json.dumps(event)}")
    
#     # Handle both proxy and non-proxy integration events
#     if 'httpMethod' in event:
#         # API Gateway proxy integration
#         http_method = event.get('httpMethod')
#         request_path = event.get('path', '')
        
#         if http_method == 'GET':
#             is_async = request_path.startswith('/async-image/')
#             return get_image(event, is_async)
#         else:
#             return {
#                 'statusCode': 405,
#                 'body': json.dumps({
#                     'error': f'Method {http_method} not allowed'
#                 })
#             }
#     else:
#         # Direct Lambda invocation or non-proxy integration
#         is_async = event.get('path', '').startswith('/async-image/')
#         return get_image(event, is_async)
