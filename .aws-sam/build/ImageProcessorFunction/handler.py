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

def process_image(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process image based on requested operations"""
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        source_key = body.get('source_key')
        target_key = body.get('target_key')
        operations = body.get('operations', {})

        if not source_key or not target_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'source_key and target_key are required'
                })
            }

        # Initialize S3 client
        s3_client = s3_operations.get_s3_client()
        config = s3_operations.S3Config()

        # Download source image
        image_data = s3_operations.download_object_from_s3(
            s3_client, 
            config.bucket_name, 
            source_key
        )

        # Process image based on requested operations
        processed_image = image_data

        # Format conversion
        if 'format' in operations:
            processed_image = image_format_converter.convert_format(
                processed_image, 
                operations['format']
            )

        # Auto orientation
        if operations.get('auto_orient', False):
            processed_image = image_auto_orient.auto_orient_image(processed_image)

        # Cropping
        if 'crop' in operations:
            processed_image = image_cropper.crop_image(
                processed_image, 
                operations['crop']
            )

        # Quality adjustment
        if 'quality' in operations:
            processed_image = image_quality.adjust_quality(
                processed_image, 
                operations['quality']
            )

        # Resizing
        if 'resize' in operations:
            processed_image = image_resizer.resize_image(
                processed_image, 
                operations['resize']
            )

        # Watermark
        if 'watermark' in operations:
            processed_image = image_watermark.add_watermark(
                processed_image, 
                operations['watermark']
            )

        # Upload processed image
        s3_operations.upload_object_to_s3(
            s3_client, 
            config.bucket_name, 
            target_key, 
            processed_image
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Image processed successfully',
                'source_key': source_key,
                'target_key': target_key,
                'operations': list(operations.keys())
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
    
    # Handle different HTTP methods
    http_method = event.get('httpMethod', 'POST')
    
    if http_method == 'POST':
        return process_image(event)
    else:
        return {
            'statusCode': 405,
            'body': json.dumps({
                'error': f'Method {http_method} not allowed'
            })
        }
