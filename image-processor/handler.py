import json
from typing import Dict, Any
import base64
from image_processor import process_image

def get_image(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get and process image based on path parameter and operations"""
    try:
        # Get path parameters and query parameters
        path_params = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters', {}) or {}
        
        object_key = path_params.get('key')
        operations_str = query_params.get('operations', '')
        
        if not object_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Image key is required in path parameter'
                })
            }

        # Process image using image_processor module
        processed_image = process_image(object_key, operations_str)

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
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for image processing"""
    print(f"Received event: {json.dumps(event)}")
    
    # Only handle GET requests
    http_method = event.get('httpMethod')
    
    if http_method == 'GET':
        return get_image(event)
    else:
        return {
            'statusCode': 405,
            'body': json.dumps({
                'error': f'Method {http_method} not allowed'
            })
        }
