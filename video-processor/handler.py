import json
import traceback
from typing import Dict, Any
import base64
from urllib.parse import unquote
from video_processor import VideoProcessor
from error_handler import capture_error, error_handler

def get_video_frame(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get and process video frame based on path parameter and operations"""
    try:
        # Get path parameters and query parameters
        path_params = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters', {}) or {}
        
        object_key = unquote(path_params.get('proxy', ''))
        operations_str = query_params.get('operations', '')
        
        if not object_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Video key is required in path parameter'
                })
            }

        # Process video using video_processor module
        frame_data, headers = VideoProcessor.process_video(object_key, operations_str)
        
        # Use standard base64 encoding for binary data
        base64_body = base64.b64encode(frame_data).decode('utf-8')
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': base64_body,
            'isBase64Encoded': True
        }

    except ValueError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': str(e)
            })
        }
    except Exception as e:
        # Get task ID from context
        task_id = context.aws_request_id if 'context' in locals() else 'unknown'
        
        # Extract error details
        error_message = str(e)
        error_details = {
            'traceback': traceback.format_exc(),
            'error_type': e.__class__.__name__,
            'operations': operations_str if 'operations_str' in locals() else None
        }
        
        # Record error in DynamoDB and send notification
        error_handler.record_error(
            task_id=task_id,
            task_type="video/process",
            source_key=object_key if 'object_key' in locals() else "unknown",
            error_message=error_message,
            error_details=error_details
        )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'task_id': task_id,
                'message': 'Error details have been recorded and will be investigated.'
            })
        }

@capture_error
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for video processing"""
    print(f"Received event: {json.dumps(event)}")
    
    # Only handle GET requests
    http_method = event.get('httpMethod')
    
    if http_method == 'GET':
        return get_video_frame(event)
    else:
        return {
            'statusCode': 405,
            'body': json.dumps({
                'error': f'Method {http_method} not allowed'
            })
        }
