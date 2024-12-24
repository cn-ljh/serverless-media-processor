import json
from typing import Dict, Any
import image_format_converter
import image_auto_orient
import image_cropper
import image_quality
import image_resizer
import image_watermark
import s3_operations
import b64encoder_decoder

def parse_operations(operations_str: str) -> Dict[str, Any]:
    """Parse operations string into a dictionary of operations and parameters"""
    if not operations_str:
        return {}
    
    operations = {}
    # Split chained operations
    operation_chains = operations_str.split('/')
    
    for chain in operation_chains:
        parts = chain.split(',')
        if not parts:
            continue
            
        # First part is always the operation name
        current_op = parts[0]
        operations[current_op] = {}
        
        # Remaining parts are parameters
        for part in parts[1:]:
            if '_' in part:
                param_key, param_value = part.split('_')
                operations[current_op][param_key] = param_value
    
    return operations

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

        # Initialize S3 client
        s3_client = s3_operations.get_s3_client()
        config = s3_operations.S3Config()

        # Download image
        image_data = s3_operations.download_object_from_s3(
            s3_client, 
            config.bucket_name, 
            object_key
        )

        # Process image based on operations
        processed_image = image_data
        operations = parse_operations(operations_str)

        # Apply operations
        for op_name, op_params in operations.items():
            if op_name == 'quality':
                processed_image = image_quality.adjust_quality(
                    processed_image,
                    int(op_params.get('q', 80))
                )
            elif op_name == 'format':
                processed_image = image_format_converter.convert_format(
                    processed_image,
                    op_params.get('f', 'jpeg')
                )
            elif op_name == 'auto_orient':
                processed_image = image_auto_orient.auto_orient_image(processed_image)
            elif op_name == 'crop':
                processed_image = image_cropper.crop_image(
                    processed_image,
                    op_params
                )
            elif op_name == 'resize':
                processed_image = image_resizer.resize_image(
                    processed_image,
                    op_params
                )
            elif op_name == 'watermark':
                processed_image = image_watermark.add_watermark(
                    processed_image,
                    op_params
                )

        # Convert processed image to base64
        base64_image = b64encoder_decoder.encode_to_base64(processed_image)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'image': base64_image,
                'original_key': object_key
            })
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
